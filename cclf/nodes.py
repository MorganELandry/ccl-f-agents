"""
THE NODES
A Play in Eight Scenes (with a Prelude)
=======================================

PROLOGUE
--------
This file holds the eight workers of the CCL-F agent. Each one is a "node" in
a LangGraph graph: a plain function that takes the shared state object
(CCLFAgentState, defined in types.py), reads some of it, changes some of it,
and hands the same object back. The wiring that decides which node runs next
lives in graph.py; this file only says what each node does.

One trip through the graph handles one batch of evidence. The state object is
passed down the line like a baton, and each node leaves something on it for
the next one:

    evidence_intake        scores each new Evidence for novelty and independence
         |                 -> writes ev.novelty_score / ev.independence_score
         v
    acs_inference          reads the admissible evidence, guesses the hidden state
         |                 -> writes state.acs_estimate (a probability spread)
         v
    aco_detection          compares formal state, estimate and evidence
         |                 -> writes state.aco_detected / state.aco_reasoning
         v
    transition_evaluation  asks: advance, hold, or escalate?
         |                 -> writes state.proposed_transition (or None)
         v
    transition_guard       plain-Python safety check, no LLM
         |                 -> clears state.proposed_transition if it is illegal
         v
    human_review           (only if a move is proposed or ACO was detected;
         |                  graph.py decides) -> writes state.human_approval
         v                  and state.human_rationale
    apply_transition       commits the move if it survived guard and review
         |                 -> writes state.commitment_state, may set
         v                    state.should_terminate
    terminate              (only if should_terminate) writes the closing summary

Three things to keep in mind while reading:

  1. The first four nodes ask a language model for help, through one shared
     helper, _llm_json() (the Prelude). The model only ever *suggests*.
  2. The guard (Scene 5) never asks the model anything. Safety rules must give
     the same answer every time, and a model does not.
  3. Every node appends to state.messages (a human-readable running log) and
     most also append to the audit log with state.append_audit(), which adds a
     hash-chained AuditEntry (see types.py): each entry stores the hash of the
     one before it, so editing an old entry later breaks the chain.

THE PLAYBILL (what happens in this file)
    Prelude  _llm_json()              Ask the model; always get a dict back
    Scene 1  evidence_intake()        Is each new piece of evidence new and independent?
    Scene 2  acs_inference()          Which commitment state is the organization really in?
    Scene 3  aco_detection()          Is someone hiding the true state?
    Scene 4  transition_evaluation()  Should we propose moving forward?
    Scene 5  transition_guard()       Is the proposed move legal at all?
    Scene 6  human_review()           Does a human (or unattended mode) approve?
    Scene 7  apply_transition()       Make the approved move official
    Scene 8  terminate()              Write the closing audit entry

READER'S NOTE — LangGraph nodes
    LangGraph builds a "state graph": named nodes joined by edges. When the
    graph runs, it calls each node function with the current state and uses
    what the node returns as the new state. Here every node edits the state
    object in place and returns it. "Conditional edges" (in graph.py) are
    small functions that look at the state and pick the next node by name.

READER'S NOTE — JSON from a language model
    We ask the model to reply with JSON text, e.g. {"novelty": 0.8, ...}.
    json.loads() turns that text into a Python dict. The nodes then read it
    with dict.get(key, default), which returns the default instead of raising
    KeyError when the key is missing. That is what makes the "error dict"
    contract of _llm_json() safe: a dict like {"error": "..."} simply has none
    of the expected keys, so every node falls back to its cautious defaults.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# `from __future__ import annotations` stores type hints as text, so newer
#   hint syntax (dict[str, Any]) works on older Pythons. No runtime effect.
# os      — read the CCLF_AUTO_APPROVE environment variable in Scene 6.
# json    — turn the model's text reply into a dict in the Prelude.
# Any     — "any type at all", used for the values of the model's JSON dict.
# SystemMessage / HumanMessage — LangChain's two message kinds: the system
#   message sets the model's role and rules, the human message is the
#   actual question.
# get_llm — returns a chat model for the backend named by CCLF_LLM_BACKEND
#   (openai | anthropic | azure | bedrock). For hospital / HIPAA use, only
#   azure or bedrock; see COMPLIANCE.md.
# The .types and .guards imports are explained where they are used. Not all
#   of the names imported from .types are used in this file.
# ===========================================================================

from __future__ import annotations
import os
import json
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage
from .backends import get_llm

from .types import (
    CCLFAgentState, CommitmentState, ACSEstimate,
    AuditEntry, Evidence,
)
from .guards import check_transition, next_valid_state   # the LLM-free rules


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# None. This file defines no module-level variables: it has only imports and
# functions. Everything a node needs travels on the state object, and the
# model is fetched fresh from get_llm() on each call to _llm_json(), so that
# changing CCLF_LLM_BACKEND or swapping _llm_json in a test takes effect
# without any cached global getting in the way.
# ===========================================================================


# ===========================================================================
# PRELUDE — THE ORACLE
# _llm_json(): ask the language model a question, always get a dict back
# ===========================================================================

def _llm_json(system: str, user: str) -> dict[str, Any]:
    """
    Send one question to the language model and return its answer as a dict.

    Enter:   system   the role and rules for the model, including the exact
                      JSON shape we want back
             user     the facts for this particular question
    Exit:    the parsed JSON reply as a dict, or, if anything goes wrong,
             an error dict instead of an exception:
               {"error": "LLM call failed: <ExceptionType>: <message>"}
                   when the call itself fails (missing credentials, unknown
                   backend, network or provider error)
               {"error": "LLM returned non-JSON", "raw": <the reply text>}
                   when the model answered, but not with valid JSON

    The graceful-degradation contract: this function never raises for those
    cases. Callers read the result with .get(key, default), so an error dict
    quietly turns into each node's safe defaults (score 0.0, "hold", no ACO,
    and so on). The run keeps going, and the LLM-free guard in Scene 5 still
    decides on its own whether any move is legal.

    The leading underscore marks this as private to this file. Tests replace
    it (monkeypatch nodes._llm_json) with a scripted fake so the whole graph
    can run with no credentials and no network.
    """
    # PLAYERS IN THIS SCENE
    #   messages   the two-message conversation sent to the model
    #   result     the model's reply object; its .content is the reply text
    #   exc        the exception, if the call itself failed

    # --- Build the conversation ------------------------------------------
    # We add a firm instruction to every system prompt so the reply is bare
    # JSON. Models like to wrap JSON in ```json fences, which json.loads()
    # cannot read.
    messages = [
        SystemMessage(content=system + "\n\nRespond ONLY with valid JSON. No markdown fences."),
        HumanMessage(content=user),
    ]

    # --- Call the model ----------------------------------------------------
    # get_llm() is called here, every time, so it picks up the current
    # backend setting. Any failure, including get_llm() itself raising for a
    # bad backend name or missing credentials, lands in the except branch.
    try:
        result = get_llm().invoke(messages)
    except Exception as exc:  # missing credentials, network or provider error
        # Same graceful-degradation contract as a non-JSON reply: downstream
        # nodes see an error dict, and the LLM-free guard still decides alone.
        # type(exc).__name__ is the exception's class name, e.g. "KeyError".
        return {"error": f"LLM call failed: {type(exc).__name__}: {exc}"}

    # --- Parse the reply -----------------------------------------------------
    try:
        return json.loads(result.content)
    except json.JSONDecodeError:
        # Graceful degradation: the model answered, but not in JSON. Return an
        # error dict (with the raw text kept for debugging) instead of raising,
        # so downstream nodes fall back to their defaults.
        return {"error": "LLM returned non-JSON", "raw": result.content}


# ===========================================================================
# SCENE 1 — THE INTAKE
# evidence_intake(): is each new piece of evidence new, and independent?
# ===========================================================================

def evidence_intake(state: CCLFAgentState) -> CCLFAgentState:
    """
    Score each un-scored piece of evidence for novelty and independence.

    Enter:   state   the shared agent state; state.evidence_buffer holds every
                     Evidence presented so far, scored or not
    Exit:    the same state, with every previously un-scored Evidence now
             carrying novelty_score and independence_score, one message and
             one EVIDENCE_SCORED audit entry per item scored

    Novelty:      does this add genuinely new information?
    Independence: does this come from a source independent of prior signals?

    Both must reach 0.5 for the evidence to be admissible (see
    Evidence.is_admissible() in types.py). Later nodes only look at
    admissible evidence, so this scene is the gatekeeper for what counts.

    The prompt: the model is told it is an evidence evaluator, given the IDs
    of evidence already seen plus the new item's ID, source and text, and
    asked for {"novelty": float, "independence": float, "reasoning": str}.
    If the reply is an error dict, both scores default to 0.0, which makes
    the evidence inadmissible: unknown evidence is not trusted.
    """
    # PLAYERS IN THIS SCENE
    #   unscored    evidence items still missing at least one score
    #   prior_ids   IDs of evidence that was already scored before this call
    #   ev          the evidence item being scored in this loop pass
    #   result      the model's JSON reply (or an error dict) for that item
    #   reasoning   the model's explanation, or "" if it gave none

    # --- Find the newcomers ------------------------------------------------
    # A list comprehension: keep each e whose novelty or independence score
    # is still None (never scored).
    unscored = [e for e in state.evidence_buffer
                if e.novelty_score is None or e.independence_score is None]

    # Nothing new arrived: say so and hand the state straight on.
    if not unscored:
        state.messages.append("[evidence_intake] No new evidence to score.")
        return state

    # The model needs to know what it has already seen to judge "novelty".
    # We pass only IDs, not full text, to keep the prompt short.
    prior_ids = [e.evidence_id for e in state.evidence_buffer if e not in unscored]

    # --- Score each newcomer, one model call per item -----------------------
    for ev in unscored:
        result = _llm_json(
            system=(
                "You are an evidence evaluator for the CCL-F coordination framework. "
                "Score evidence on two dimensions:\n"
                "  novelty (0.0–1.0): how much new information does this add, "
                "given the prior evidence already seen?\n"
                "  independence (0.0–1.0): how independent is the source from "
                "prior evidence sources (corroborating vs. independent)?\n"
                "Return JSON: {\"novelty\": float, \"independence\": float, \"reasoning\": str}"
            ),
            user=(
                f"Prior evidence IDs already seen: {prior_ids}\n\n"
                f"New evidence [{ev.evidence_id}] from [{ev.source}]:\n{ev.content}"
            ),
        )

        # --- Write the scores onto the Evidence object ------------------------
        # Missing keys (including the error-dict case) default to 0.0, which
        # keeps the item inadmissible.
        ev.novelty_score     = result.get("novelty", 0.0)
        ev.independence_score = result.get("independence", 0.0)
        reasoning = result.get("reasoning", "")

        # --- Log it: a readable message, then a tamper-evident audit entry ---
        # `:.2f` formats a number with two decimal places.
        state.messages.append(
            f"[evidence_intake] {ev.evidence_id}: "
            f"novelty={ev.novelty_score:.2f}, independence={ev.independence_score:.2f}"
            f" — {reasoning}"
        )
        state.append_audit(
            "EVIDENCE_SCORED",
            {"evidence_id": ev.evidence_id, "novelty": ev.novelty_score,
             "independence": ev.independence_score, "reasoning": reasoning},
        )

    return state


# ===========================================================================
# SCENE 2 — THE READING OF SIGNS
# acs_inference(): which commitment state is the organization really in?
# ===========================================================================

def acs_inference(state: CCLFAgentState) -> CCLFAgentState:
    """
    Estimate, as probabilities, which commitment state the decision-making
    authority is truly in, from the behavioural signals in the evidence.

    Enter:   state   the shared agent state; uses state.evidence_buffer (only
                     admissible items) and state.commitment_state
    Exit:    the same state, with state.acs_estimate replaced by a new
             ACSEstimate, plus one message and one ACS_INFERENCE audit entry

    ACS stands for Authority Commitment Signal. The agent cannot observe it
    directly (it may be concealed or distorted; see the ACO failure mode in
    Scene 3), so this node produces a best-effort estimate.

    The prompt: the model is told the four states and what each means, given
    the current *formal* state and the admissible evidence, and asked for
    p_open, p_trajectory, p_authority, p_execution (meant to sum to 1.0),
    confidence (0–1) and reasoning. The code does not check that the four
    numbers sum to 1.0; it stores what it gets. If the reply is an error dict,
    the defaults say "certainly OPEN, zero confidence".
    """
    # PLAYERS IN THIS SCENE
    #   admissible         evidence items that passed Scene 1's 0.5 bar
    #   evidence_summary   those items as one indented text block for the prompt
    #   result             the model's JSON reply (or an error dict)

    # --- Gather the evidence the model is allowed to see --------------------
    admissible = [e for e in state.evidence_buffer if e.is_admissible()]

    # "\n".join(...) glues one line per item together. The `or` at the end is
    # a Python idiom: an empty string counts as False, so if there is no
    # admissible evidence the placeholder text is used instead.
    evidence_summary = "\n".join(
        f"  [{e.evidence_id}] {e.source}: {e.content}"
        for e in admissible
    ) or "  (no admissible evidence yet)"

    # --- Ask the model for a probability spread -----------------------------
    result = _llm_json(
        system=(
            "You are a CCL-F ACS inference engine. "
            "Given behavioural signals, estimate the probability that the "
            "decision-making authority is in each of the four CCL-F commitment states:\n"
            "  OPEN:       no trajectory committed; signals visible and being evaluated\n"
            "  TRAJECTORY: a direction is locked; alternatives deprioritised\n"
            "  AUTHORITY:  decision authority has formally closed\n"
            "  EXECUTION:  resources deployed; reversal is operationally costly\n\n"
            "Return JSON with keys: p_open, p_trajectory, p_authority, p_execution "
            "(must sum to 1.0), confidence (0–1), reasoning (str)."
        ),
        user=(
            f"Current formal commitment state: {state.commitment_state}\n\n"
            f"Admissible evidence:\n{evidence_summary}"
        ),
    )

    # --- Store the estimate on the state ------------------------------------
    # The defaults match ACSEstimate's own defaults in types.py.
    state.acs_estimate = ACSEstimate(
        p_open       = result.get("p_open", 1.0),
        p_trajectory = result.get("p_trajectory", 0.0),
        p_authority  = result.get("p_authority", 0.0),
        p_execution  = result.get("p_execution", 0.0),
        confidence   = result.get("confidence", 0.0),
        reasoning    = result.get("reasoning", ""),
    )

    # --- Log it ----------------------------------------------------------------
    state.messages.append(
        f"[acs_inference] ACS estimate: "
        f"OPEN={state.acs_estimate.p_open:.2f}, "
        f"TRAJ={state.acs_estimate.p_trajectory:.2f}, "
        f"AUTH={state.acs_estimate.p_authority:.2f}, "
        f"EXEC={state.acs_estimate.p_execution:.2f} "
        f"(confidence={state.acs_estimate.confidence:.2f})"
    )
    state.append_audit("ACS_INFERENCE", {
        "p_open":       state.acs_estimate.p_open,
        "p_trajectory": state.acs_estimate.p_trajectory,
        "p_authority":  state.acs_estimate.p_authority,
        "p_execution":  state.acs_estimate.p_execution,
        "confidence":   state.acs_estimate.confidence,
        "reasoning":    state.acs_estimate.reasoning,
    })
    return state


# ===========================================================================
# SCENE 3 — THE UNMASKING
# aco_detection(): is the true commitment state being hidden?
# ===========================================================================

def aco_detection(state: CCLFAgentState) -> CCLFAgentState:
    """
    Detect Adversarial Commitment Opacity (ACO): a failure mode in which
    the true commitment state is deliberately or structurally concealed from
    agents who need it to act safely.

    Enter:   state   the shared agent state; uses state.commitment_state,
                     state.acs_estimate (from Scene 2) and state.evidence_buffer
    Exit:    the same state, with state.aco_detected (True / False) and
             state.aco_reasoning set; one message, and an ACO_DETECTED audit
             entry only when ACO was found

    ACO conditions (any one sufficient):
      C1: Formal state differs from the ACS most-likely state, with high
          confidence (the design target is confidence > 0.7)
      C2: High-novelty, high-independence evidence is being ignored
      C3: Decision authority is inaccessible while trajectory is locked

    Who checks these? The model does. The code below does not compute C1,
    C2 or C3 itself, and does not apply the 0.7 threshold; it passes the
    facts to the model, describes the conditions in the prompt ("high
    confidence"), and trusts the model's verdict. The prompt asks for
    {"aco_detected": bool, "conditions_met": [str], "reasoning": str}.
    On an error dict, aco_detected defaults to False.

    Why it matters downstream: graph.py sends the run to human_review
    whenever ACO is detected, even if nothing was proposed.
    """
    # PLAYERS IN THIS SCENE
    #   admissible        evidence that passed Scene 1's bar
    #   ignored           evidence that did not (the prompt calls it
    #                     "potentially suppressed")
    #   acs_most_likely   the state with the highest probability in Scene 2's
    #                     estimate
    #   result            the model's JSON reply (or an error dict)

    # --- Prepare the facts for the model -------------------------------------
    admissible = [e for e in state.evidence_buffer if e.is_admissible()]
    ignored = [e for e in state.evidence_buffer if not e.is_admissible()]
    acs_most_likely = state.acs_estimate.most_likely()

    # --- Ask the model ------------------------------------------------------
    # Note the user text: the f-strings are joined with `+` to a "\n".join(...)
    # that lists *every* evidence item with its admissible flag, so the model
    # can see what was set aside, not just what was kept.
    result = _llm_json(
        system=(
            "You are a CCL-F ACO (Adversarial Commitment Opacity) detector. "
            "ACO occurs when the true commitment state is concealed from agents who need it.\n\n"
            "Check these conditions:\n"
            "  C1: Formal commitment state diverges from inferred ACS estimate (high confidence)\n"
            "  C2: Admissible evidence is being systematically ignored or suppressed\n"
            "  C3: Decision authority is inaccessible while a trajectory is locked\n\n"
            "Return JSON: {\"aco_detected\": bool, \"conditions_met\": [str], \"reasoning\": str}"
        ),
        user=(
            f"Formal state: {state.commitment_state}\n"
            f"ACS most-likely: {acs_most_likely} (confidence={state.acs_estimate.confidence:.2f})\n"
            f"ACS reasoning: {state.acs_estimate.reasoning}\n\n"
            f"Admissible evidence count: {len(admissible)}\n"
            f"Non-admissible (potentially suppressed) evidence count: {len(ignored)}\n\n"
            f"Evidence detail:\n" +
            "\n".join(f"  [{e.evidence_id}] admissible={e.is_admissible()}: {e.content}"
                      for e in state.evidence_buffer)
        ),
    )

    # --- Record the verdict on the state ---------------------------------------
    state.aco_detected  = result.get("aco_detected", False)
    state.aco_reasoning = result.get("reasoning", "")

    # --- Log it: only a positive finding goes into the audit log --------------
    if state.aco_detected:
        state.messages.append(
            f"[aco_detection] ⚠️  ACO DETECTED — conditions: "
            f"{result.get('conditions_met', [])} — {state.aco_reasoning}"
        )
        state.append_audit("ACO_DETECTED", {
            "conditions_met": result.get("conditions_met", []),
            "reasoning": state.aco_reasoning,
        })
    else:
        state.messages.append("[aco_detection] No ACO conditions met.")

    return state


# ===========================================================================
# SCENE 4 — THE PROPOSAL
# transition_evaluation(): should we propose moving to the next state?
# ===========================================================================

def transition_evaluation(state: CCLFAgentState) -> CCLFAgentState:
    """
    Ask the model whether to advance the commitment state, hold, or escalate.

    Enter:   state   the shared agent state; uses state.commitment_state,
                     state.aco_detected, state.acs_estimate and the
                     admissible evidence
    Exit:    the same state, with state.proposed_transition set to the next
             state (advance) or None (hold or escalate); one message and one
             TRANSITION_PROPOSED audit entry

    This node only *proposes*. It sets state.proposed_transition but does NOT
    apply it; that happens in Scene 7, and only after the guard (Scene 5)
    and the human review (Scene 6).

    The prompt: the model is shown the current state, the one next valid
    state, the ACO flag, the ACS most-likely state and confidence, and the
    admissible evidence, and asked for
    {"action": "advance"|"hold"|"escalate", "reasoning": str}.
    How the reply is used:
      "advance"  and a next state exists  -> propose that next state
      "escalate"                          -> propose nothing, clear any old
                                             human verdict
      anything else (including "hold", an unknown word, an error dict, or
      "advance" when already at EXECUTION) -> propose nothing (hold)
    The model can never name the target state itself: the only state it can
    cause to be proposed is `candidate`, chosen by next_valid_state().
    """
    # PLAYERS IN THIS SCENE
    #   admissible         evidence that passed Scene 1's bar
    #   evidence_summary   that evidence as one text block for the prompt
    #   candidate          the single legal next state, or None at EXECUTION
    #   candidate_str      candidate as text for the prompt
    #   result             the model's JSON reply (or an error dict)
    #   action             "advance", "hold", "escalate", or whatever came back
    #   reasoning          the model's explanation

    # --- Prepare the evidence (same pattern as Scene 2) --------------------
    admissible = [e for e in state.evidence_buffer if e.is_admissible()]
    evidence_summary = "\n".join(
        f"  [{e.evidence_id}] {e.source}: {e.content}"
        for e in admissible
    ) or "  (no admissible evidence)"

    # --- Work out the only move that could be proposed ----------------------
    # next_valid_state() comes from guards.py. `X if cond else Y` is Python's
    # one-line if/else; candidate.value is the enum's plain string, e.g.
    # "TRAJECTORY".
    candidate = next_valid_state(state.commitment_state)
    candidate_str = candidate.value if candidate else "NONE (already at EXECUTION)"

    # --- Ask the model --------------------------------------------------------
    result = _llm_json(
        system=(
            "You are a CCL-F transition evaluator. "
            "Given the current commitment state and admissible evidence, "
            "decide whether to propose advancing to the next commitment state, "
            "hold the current state, or flag for human escalation.\n\n"
            "CCL-F states in order: OPEN → TRAJECTORY → AUTHORITY → EXECUTION\n"
            "A transition should only be proposed if there is sufficient admissible "
            "evidence to justify moving the organisation's commitment forward.\n\n"
            "Return JSON: {\"action\": \"advance\"|\"hold\"|\"escalate\", \"reasoning\": str}"
        ),
        user=(
            f"Current state: {state.commitment_state}\n"
            f"Next valid state: {candidate_str}\n"
            f"ACO detected: {state.aco_detected}\n"
            f"ACS inferred most-likely: {state.acs_estimate.most_likely()} "
            f"(confidence={state.acs_estimate.confidence:.2f})\n\n"
            f"Admissible evidence:\n{evidence_summary}"
        ),
    )

    # Default to "hold": if the model failed, the safe choice is to not move.
    action = result.get("action", "hold")
    reasoning = result.get("reasoning", "")

    # --- Turn the model's answer into a proposal ----------------------------
    if action == "advance" and candidate:
        state.proposed_transition = candidate
        state.messages.append(
            f"[transition_evaluation] Proposing advance → {candidate.value}: {reasoning}"
        )
    elif action == "escalate":
        state.proposed_transition = None
        state.messages.append(
            f"[transition_evaluation] Escalating to human review: {reasoning}"
        )
        # Clear any verdict left over from an earlier review, so no old
        # decision is mistaken for an answer to this escalation. Note: with
        # nothing proposed, graph.py only routes to human_review if ACO was
        # also detected (see route_after_guard there).
        state.human_approval = None  # Reset so human_review node fires
    else:
        state.proposed_transition = None
        state.messages.append(
            f"[transition_evaluation] Holding at {state.commitment_state}: {reasoning}"
        )

    # --- Audit the proposal, whatever it was ---------------------------------
    state.append_audit("TRANSITION_PROPOSED", {
        "action": action,
        "proposed": state.proposed_transition.value if state.proposed_transition else None,
        "reasoning": reasoning,
    })
    return state


# ===========================================================================
# SCENE 5 — THE BOUNCER
# transition_guard(): is the proposed move legal at all?
# ===========================================================================

def transition_guard(state: CCLFAgentState) -> CCLFAgentState:
    """
    Structural guard: enforce blocked transitions before any state change.

    Enter:   state   the shared agent state; uses state.commitment_state and
                     state.proposed_transition
    Exit:    the same state. If the move is illegal, state.proposed_transition
             is set back to None and a TRANSITION_BLOCKED audit entry is
             written. If it is legal (or nothing was proposed), only a
             message is added.

    Why there is no LLM here: this node is intentionally LLM-free. The
    safety property must be deterministic and not subject to probabilistic
    override. A model could be talked into a bad answer by misleading
    evidence, or simply answer differently on a second try. The rules in
    guards.check_transition() are plain Python: same input, same answer,
    every time. This also means the guard keeps working when the model is
    unavailable and _llm_json() is returning error dicts.
    """
    # PLAYERS IN THIS SCENE
    #   allowed   True if guards.check_transition() permits the move
    #   reason    its explanation sentence, recorded in messages and audit

    # --- Nothing proposed: nothing to guard ---------------------------------
    if state.proposed_transition is None:
        state.messages.append("[transition_guard] No proposed transition; guard passed trivially.")
        return state

    # --- Ask the rule book ----------------------------------------------------
    # check_transition() returns a tuple; `allowed, reason = ...` unpacks it
    # into two variables in one line.
    allowed, reason = check_transition(state.commitment_state, state.proposed_transition)

    if not allowed:
        # --- Refused: record why, then cancel the proposal ------------------
        state.messages.append(f"[transition_guard] ❌ BLOCKED — {reason}")
        state.append_audit("TRANSITION_BLOCKED", {
            "from": state.commitment_state,
            "to": state.proposed_transition,
            "reason": reason,
        })
        state.proposed_transition = None   # Cancel the proposal
    else:
        # --- Permitted: the proposal stays, and goes on to human review ------
        state.messages.append(f"[transition_guard] ✅ Guard passed — {reason}")

    return state


# ===========================================================================
# SCENE 6 — THE HUMAN IN THE LOOP
# human_review(): does a person (or unattended mode) approve this?
# ===========================================================================

def human_review(state: CCLFAgentState) -> CCLFAgentState:
    """
    Human-in-the-loop checkpoint: show the reviewer the situation and record
    their decision.

    Enter:   state   the shared agent state; graph.py routes here when a
                     move is proposed (and has passed the guard) or when ACO
                     was detected
    Exit:    the same state, with state.human_approval (True / False) and
             state.human_rationale set; one message and one HUMAN_REVIEW
             audit entry. Prints a review panel to stdout as a side effect.

    How the decision is made, in order:
      1. Unattended mode. If the environment variable CCLF_AUTO_APPROVE is
         "true" (any capitalisation; run_demo.py --no-hitl and the tests set
         it), the node approves without asking anyone, and records the
         rationale "AUTO-APPROVED (unattended mode, no human reviewer)". That
         wording goes into the audit log on purpose, so the audit chain never
         shows an automatic decision as a human approval. The LLM-free guard
         has already run, so an illegal move cannot get this far.
      2. Interactive, with a proposal. Ask "Approve transition to X?" on
         stdin. An answer starting with "y" approves (rationale "Approved by
         human reviewer."); anything else rejects, and the typed answer
         itself becomes the rationale, so a reviewer can type a reason.
      3. Interactive, no proposal (we are here because of ACO / escalation).
         Ask "Continue monitoring?"; "y..." means approved, and the typed
         answer is the rationale either way.

    How a service deployment would pause before this node: build the graph
    with a checkpointer and interrupt_before=["human_review"] (graph.py's
    build_graph(interrupt_before_human=True) does exactly that). The run
    stops just before this node and saves its state. An external system
    (webhook, UI click, etc.) later records the decision with
    graph.update_state(config, {...}) and resumes with
    graph.invoke(None, config); see tests/test_checkpoint.py. Be aware that
    resuming runs this node's body: as written it will still prompt on
    stdin, or in unattended mode overwrite human_approval / human_rationale
    with the AUTO-APPROVED decision. The CLI (run_demo.py) therefore does
    not pause; it runs this node inline.

    LangGraph interrupt pattern:
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph().compile(checkpointer=MemorySaver(),
                                       interrupt_before=["human_review"])
        # External system resumes with: graph.invoke(state, config)
    (In this repo build_graph() already compiles the graph and takes care of
    the checkpointer and interrupt itself, as described above.)
    """
    # PLAYERS IN THIS SCENE
    #   a           short alias for state.acs_estimate, for the printout
    #   msg         one recent message, in the printing loop
    #   approved    the decision: True (approved) or False (rejected)
    #   rationale   the reason recorded alongside the decision
    #   answer      what the reviewer typed (interactive modes only)

    # --- Show the reviewer the situation -----------------------------------
    # "="*60 repeats the "=" character 60 times to draw a rule line.
    print("\n" + "="*60)
    print("🔔  HUMAN REVIEW REQUIRED")
    print("="*60)
    print(f"Current commitment state : {state.commitment_state}")
    print(f"Proposed transition      : {state.proposed_transition}")
    print(f"ACO detected             : {state.aco_detected}")
    if state.aco_detected:
        print(f"ACO reasoning            : {state.aco_reasoning}")
    print("\nRecent messages:")
    # state.messages[-5:] is a slice: the last five items (fewer if shorter).
    for msg in state.messages[-5:]:
        print(f"  {msg}")
    print("\nACS estimate:")
    a = state.acs_estimate
    print(f"  OPEN={a.p_open:.2f}  TRAJECTORY={a.p_trajectory:.2f}  "
          f"AUTHORITY={a.p_authority:.2f}  EXECUTION={a.p_execution:.2f}")
    print(f"  Reasoning: {a.reasoning}")

    # --- Get the decision ------------------------------------------------------
    # os.environ.get(name, "") returns "" when the variable is unset, so
    # .lower() is always safe to call.
    if os.environ.get("CCLF_AUTO_APPROVE", "").lower() == "true":
        # Unattended demo mode (run_demo.py --no-hitl). The LLM-free guard
        # has already passed; the decision is recorded as automatic so the
        # audit chain never shows it as a human approval.
        approved, rationale = True, "AUTO-APPROVED (unattended mode, no human reviewer)"
    elif state.proposed_transition:
        # input() blocks until the reviewer presses Enter; .strip() removes
        # surrounding spaces and the newline.
        answer = input(
            f"\nApprove transition to {state.proposed_transition}? [y/n/reason]: "
        ).strip()
        approved = answer.lower().startswith("y")
        rationale = answer if not approved else "Approved by human reviewer."
    else:
        answer = input(
            "\nNo transition proposed (escalation). Continue monitoring? [y/n]: "
        ).strip()
        approved = answer.lower().startswith("y")
        rationale = answer

    # --- Record the decision on the state, in messages and in the audit -------
    state.human_approval  = approved
    state.human_rationale = rationale
    state.messages.append(
        f"[human_review] Decision: {'APPROVED' if approved else 'REJECTED'} — {rationale}"
    )
    state.append_audit("HUMAN_REVIEW", {
        "proposed": state.proposed_transition.value if state.proposed_transition else None,
        "approved": approved,
        "rationale": rationale,
    })
    print("="*60 + "\n")
    return state


# ===========================================================================
# SCENE 7 — THE COMMITMENT
# apply_transition(): make the approved move official
# ===========================================================================

def apply_transition(state: CCLFAgentState) -> CCLFAgentState:
    """
    Commit the proposed transition to state.

    Enter:   state   the shared agent state; uses state.proposed_transition,
                     state.human_approval and state.human_rationale
    Exit:    the same state. One of three outcomes:
               nothing proposed     -> message only
               human rejected it    -> message, proposal cleared
               otherwise            -> state.commitment_state moves forward,
                                       proposal and approval are cleared, a
                                       TRANSITION_APPLIED audit entry is
                                       written, and should_terminate is set
                                       if EXECUTION was reached

    graph.py always comes here after the guard, either directly (nothing
    proposed, no ACO) or via human_review. Any surviving proposal has
    therefore passed the guard and been through review.

    Note the test is `human_approval is False`, not `not human_approval`:
    only an explicit rejection stops the move. A value of None (no decision
    recorded) does not block it.
    """
    # PLAYERS IN THIS SCENE
    #   from_state   the state we are leaving, kept for the log and audit

    # --- Case 1: nothing to do -------------------------------------------------
    if not state.proposed_transition:
        state.messages.append("[apply_transition] Nothing to apply.")
        return state

    # --- Case 2: the reviewer said no --------------------------------------------
    if state.human_approval is False:
        state.messages.append(
            f"[apply_transition] Transition rejected by human: {state.human_rationale}"
        )
        state.proposed_transition = None
        return state

    # --- Case 3: apply it, and reset the proposal and verdict for next time ---
    from_state = state.commitment_state
    state.commitment_state    = state.proposed_transition
    state.proposed_transition = None
    state.human_approval      = None

    state.messages.append(
        f"[apply_transition] ✅ Transition applied: {from_state} → {state.commitment_state}"
    )
    # This is the one audit entry that also fills the AuditEntry's own
    # from_state / to_state fields (passed as keyword arguments), not just
    # the payload, so state changes are easy to find in the chain.
    state.append_audit("TRANSITION_APPLIED", {
        "from": from_state,
        "to": state.commitment_state,
    }, from_state=from_state, to_state=state.commitment_state)

    # --- The final state: nothing further can happen -------------------------
    # EXECUTION state reached → flag for termination after audit.
    # graph.py's route_after_apply sees should_terminate and goes to Scene 8.
    if state.commitment_state == CommitmentState.EXECUTION:
        state.messages.append(
            "[apply_transition] EXECUTION state reached. "
            "Commitment is now irreversible. Terminating loop."
        )
        state.should_terminate = True

    return state


# ===========================================================================
# SCENE 8 — THE CURTAIN
# terminate(): write the closing audit summary
# ===========================================================================

def terminate(state: CCLFAgentState) -> CCLFAgentState:
    """
    Write final audit summary and signal graph completion.

    Enter:   state   the shared agent state at the end of the session
    Exit:    the same state, with a SESSION_END audit entry, a closing
             message, and state.should_terminate set to True

    graph.py runs this when should_terminate is set (EXECUTION reached);
    run_demo.py also calls it directly if a scenario ends without
    terminating, so every session's audit log ends with SESSION_END.
    """
    # --- The closing audit entry --------------------------------------------
    # "audit_entries" counts the entries *before* this one is added.
    # sum(1 for e in ... if ...) counts matching items without building a list.
    state.append_audit("SESSION_END", {
        "final_state":        state.commitment_state,
        "aco_detected":       state.aco_detected,
        "evidence_count":     len(state.evidence_buffer),
        "admissible_count":   sum(1 for e in state.evidence_buffer if e.is_admissible()),
        "audit_entries":      len(state.audit_log),
    })

    # --- Closing message (this count now includes SESSION_END) ---------------
    state.messages.append(
        f"[terminate] Session complete. "
        f"Final state: {state.commitment_state}. "
        f"Audit entries: {len(state.audit_log)}."
    )
    state.should_terminate = True
    return state

# EXEUNT — end of file.

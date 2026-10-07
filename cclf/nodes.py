"""
CCL-F LangGraph Nodes
=====================
Each node is a pure function: CCLFAgentState → CCLFAgentState.
LangGraph calls nodes by name; edges (including conditional edges) are
wired in graph.py.

Node inventory:
  1. evidence_intake        — validate and score incoming evidence
  2. acs_inference          — LLM estimates hidden commitment state
  3. aco_detection          — LLM checks for Adversarial Commitment Opacity
  4. transition_evaluation  — LLM proposes a state transition (or hold)
  5. transition_guard       — structural guard (no LLM; pure logic)
  6. human_review           — interrupt node; surfaces to human approver
  7. apply_transition       — commits the transition and writes audit entry
  8. terminate              — writes final audit summary and exits
"""

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
from .guards import check_transition, next_valid_state

# ---------------------------------------------------------------------------
# LLM initialisation — delegates to backend registry
# Set CCLF_LLM_BACKEND=openai|anthropic|azure|bedrock
# For hospital/HIPAA use: azure or bedrock only. See COMPLIANCE.md.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helper: call LLM and parse JSON response
# ---------------------------------------------------------------------------

def _llm_json(system: str, user: str) -> dict[str, Any]:
    messages = [
        SystemMessage(content=system + "\n\nRespond ONLY with valid JSON. No markdown fences."),
        HumanMessage(content=user),
    ]
    try:
        result = get_llm().invoke(messages)
    except Exception as exc:  # missing credentials, network or provider error
        # Same graceful-degradation contract as a non-JSON reply: downstream
        # nodes see an error dict, and the LLM-free guard still decides alone.
        return {"error": f"LLM call failed: {type(exc).__name__}: {exc}"}
    try:
        return json.loads(result.content)
    except json.JSONDecodeError:
        # Graceful degradation: return empty dict so downstream nodes can handle
        return {"error": "LLM returned non-JSON", "raw": result.content}


# ---------------------------------------------------------------------------
# Node 1 — Evidence intake
# ---------------------------------------------------------------------------

def evidence_intake(state: CCLFAgentState) -> CCLFAgentState:
    """
    Score each un-scored piece of evidence for novelty and independence.
    Novelty:      does this add genuinely new information?
    Independence: does this come from a source independent of prior signals?

    Both must clear 0.5 to be admissible (see Evidence.is_admissible()).
    """
    unscored = [e for e in state.evidence_buffer
                if e.novelty_score is None or e.independence_score is None]

    if not unscored:
        state.messages.append("[evidence_intake] No new evidence to score.")
        return state

    prior_ids = [e.evidence_id for e in state.evidence_buffer if e not in unscored]

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
        ev.novelty_score     = result.get("novelty", 0.0)
        ev.independence_score = result.get("independence", 0.0)
        reasoning = result.get("reasoning", "")
        state.messages.append(
            f"[evidence_intake] {ev.evidence_id}: "
            f"novelty={ev.novelty_score:.2f}, independence={ev.independence_score:.2f} — {reasoning}"
        )
        state.append_audit(
            "EVIDENCE_SCORED",
            {"evidence_id": ev.evidence_id, "novelty": ev.novelty_score,
             "independence": ev.independence_score, "reasoning": reasoning},
        )

    return state


# ---------------------------------------------------------------------------
# Node 2 — ACS hidden-state inference
# ---------------------------------------------------------------------------

def acs_inference(state: CCLFAgentState) -> CCLFAgentState:
    """
    Maintain a probability distribution over CommitmentStates by inferring
    the true Authority Commitment Signal (ACS) from behavioural signals.

    The agent cannot observe ACS directly (it may be concealed or distorted —
    see ACO failure mode). This node produces a best-effort estimate.
    """
    admissible = [e for e in state.evidence_buffer if e.is_admissible()]
    evidence_summary = "\n".join(
        f"  [{e.evidence_id}] {e.source}: {e.content}"
        for e in admissible
    ) or "  (no admissible evidence yet)"

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

    state.acs_estimate = ACSEstimate(
        p_open       = result.get("p_open", 1.0),
        p_trajectory = result.get("p_trajectory", 0.0),
        p_authority  = result.get("p_authority", 0.0),
        p_execution  = result.get("p_execution", 0.0),
        confidence   = result.get("confidence", 0.0),
        reasoning    = result.get("reasoning", ""),
    )
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


# ---------------------------------------------------------------------------
# Node 3 — ACO detection
# ---------------------------------------------------------------------------

def aco_detection(state: CCLFAgentState) -> CCLFAgentState:
    """
    Detect Adversarial Commitment Opacity (ACO): a failure mode in which
    the true commitment state is deliberately or structurally concealed from
    agents who need it to act safely.

    ACO conditions (any one sufficient):
      C1: Formal state ≠ inferred ACS most-likely state AND confidence > 0.7
      C2: High-novelty, high-independence evidence is being ignored
      C3: Decision authority is inaccessible while trajectory is locked
    """
    admissible = [e for e in state.evidence_buffer if e.is_admissible()]
    ignored = [e for e in state.evidence_buffer if not e.is_admissible()]
    acs_most_likely = state.acs_estimate.most_likely()

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

    state.aco_detected  = result.get("aco_detected", False)
    state.aco_reasoning = result.get("reasoning", "")

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


# ---------------------------------------------------------------------------
# Node 4 — Transition evaluation
# ---------------------------------------------------------------------------

def transition_evaluation(state: CCLFAgentState) -> CCLFAgentState:
    """
    The LLM proposes whether to advance the commitment state, hold, or flag.
    This node sets state.proposed_transition but does NOT apply it —
    that happens only after the structural guard and human approval.
    """
    admissible = [e for e in state.evidence_buffer if e.is_admissible()]
    evidence_summary = "\n".join(
        f"  [{e.evidence_id}] {e.source}: {e.content}"
        for e in admissible
    ) or "  (no admissible evidence)"

    candidate = next_valid_state(state.commitment_state)
    candidate_str = candidate.value if candidate else "NONE (already at EXECUTION)"

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

    action = result.get("action", "hold")
    reasoning = result.get("reasoning", "")

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
        state.human_approval = None  # Reset so human_review node fires
    else:
        state.proposed_transition = None
        state.messages.append(
            f"[transition_evaluation] Holding at {state.commitment_state}: {reasoning}"
        )

    state.append_audit("TRANSITION_PROPOSED", {
        "action": action,
        "proposed": state.proposed_transition.value if state.proposed_transition else None,
        "reasoning": reasoning,
    })
    return state


# ---------------------------------------------------------------------------
# Node 5 — Transition guard (pure logic, no LLM)
# ---------------------------------------------------------------------------

def transition_guard(state: CCLFAgentState) -> CCLFAgentState:
    """
    Structural guard: enforce blocked transitions before any state change.
    This node is intentionally LLM-free — the safety property must be
    deterministic and not subject to probabilistic override.
    """
    if state.proposed_transition is None:
        state.messages.append("[transition_guard] No proposed transition; guard passed trivially.")
        return state

    allowed, reason = check_transition(state.commitment_state, state.proposed_transition)

    if not allowed:
        state.messages.append(f"[transition_guard] ❌ BLOCKED — {reason}")
        state.append_audit("TRANSITION_BLOCKED", {
            "from": state.commitment_state,
            "to": state.proposed_transition,
            "reason": reason,
        })
        state.proposed_transition = None   # Cancel the proposal
    else:
        state.messages.append(f"[transition_guard] ✅ Guard passed — {reason}")

    return state


# ---------------------------------------------------------------------------
# Node 6 — Human review (interrupt node)
# ---------------------------------------------------------------------------

def human_review(state: CCLFAgentState) -> CCLFAgentState:
    """
    Human-in-the-loop checkpoint.
    In production this node emits an interrupt and waits for an external
    approval event (webhook, UI click, etc.). In this reference implementation
    we print to stdout and read from stdin, making the checkpoint auditable
    even in CLI mode.

    LangGraph interrupt pattern:
        from langgraph.checkpoint.memory import MemorySaver
        graph = build_graph().compile(checkpointer=MemorySaver(),
                                       interrupt_before=["human_review"])
        # External system resumes with: graph.invoke(state, config)
    """
    print("\n" + "="*60)
    print("🔔  HUMAN REVIEW REQUIRED")
    print("="*60)
    print(f"Current commitment state : {state.commitment_state}")
    print(f"Proposed transition      : {state.proposed_transition}")
    print(f"ACO detected             : {state.aco_detected}")
    if state.aco_detected:
        print(f"ACO reasoning            : {state.aco_reasoning}")
    print("\nRecent messages:")
    for msg in state.messages[-5:]:
        print(f"  {msg}")
    print("\nACS estimate:")
    a = state.acs_estimate
    print(f"  OPEN={a.p_open:.2f}  TRAJECTORY={a.p_trajectory:.2f}  "
          f"AUTHORITY={a.p_authority:.2f}  EXECUTION={a.p_execution:.2f}")
    print(f"  Reasoning: {a.reasoning}")

    if os.environ.get("CCLF_AUTO_APPROVE", "").lower() == "true":
        # Unattended demo mode (run_demo.py --no-hitl). The LLM-free guard
        # has already passed; the decision is recorded as automatic so the
        # audit chain never shows it as a human approval.
        approved, rationale = True, "AUTO-APPROVED (unattended mode, no human reviewer)"
    elif state.proposed_transition:
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


# ---------------------------------------------------------------------------
# Node 7 — Apply transition
# ---------------------------------------------------------------------------

def apply_transition(state: CCLFAgentState) -> CCLFAgentState:
    """
    Commit the proposed transition to state.
    Only reached if transition_guard passed AND human approved.
    """
    if not state.proposed_transition:
        state.messages.append("[apply_transition] Nothing to apply.")
        return state

    if state.human_approval is False:
        state.messages.append(
            f"[apply_transition] Transition rejected by human: {state.human_rationale}"
        )
        state.proposed_transition = None
        return state

    from_state = state.commitment_state
    state.commitment_state    = state.proposed_transition
    state.proposed_transition = None
    state.human_approval      = None

    state.messages.append(
        f"[apply_transition] ✅ Transition applied: {from_state} → {state.commitment_state}"
    )
    state.append_audit("TRANSITION_APPLIED", {
        "from": from_state,
        "to": state.commitment_state,
    }, from_state=from_state, to_state=state.commitment_state)

    # EXECUTION state reached → flag for termination after audit
    if state.commitment_state == CommitmentState.EXECUTION:
        state.messages.append(
            "[apply_transition] EXECUTION state reached. "
            "Commitment is now irreversible. Terminating loop."
        )
        state.should_terminate = True

    return state


# ---------------------------------------------------------------------------
# Node 8 — Terminate
# ---------------------------------------------------------------------------

def terminate(state: CCLFAgentState) -> CCLFAgentState:
    """
    Write final audit summary and signal graph completion.
    """
    state.append_audit("SESSION_END", {
        "final_state":        state.commitment_state,
        "aco_detected":       state.aco_detected,
        "evidence_count":     len(state.evidence_buffer),
        "admissible_count":   sum(1 for e in state.evidence_buffer if e.is_admissible()),
        "audit_entries":      len(state.audit_log),
    })
    state.messages.append(
        f"[terminate] Session complete. "
        f"Final state: {state.commitment_state}. "
        f"Audit entries: {len(state.audit_log)}."
    )
    state.should_terminate = True
    return state

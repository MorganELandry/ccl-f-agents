"""
THE FULL DRESS REHEARSAL
A Play in Six Scenes
========================

PROLOGUE
--------
End-to-end graph runs with a scripted stand-in for the LLM.
Exercises every node — including human_review and the LLM-free guard —
without credentials or network access.

The other test files check pieces in isolation. This one runs the whole
agent graph from start to finish over all five MCAS evidence items, the way
run_demo.py does, but with two substitutions so it is fast and repeatable:

  - the LLM is replaced by `scripted_llm`, a fake that always gives the same
    answers, so no API key or network is needed and results never vary;
  - human approval is switched to automatic (CCLF_AUTO_APPROVE=true), so the
    human_review node does not stop and wait for keyboard input.

Everything else is real: the graph, the transition guard, apply_transition,
terminate and the hash-chained audit log.

Run: pytest tests/ -v

THE PLAYBILL
    Scene 1  scripted_llm()   (helper) build a fake LLM with fixed answers
    Scene 2  run()            (helper) feed evidence batches through the graph
    Scene 3  test_advances_one_state_per_batch_and_terminates
    Scene 4  test_unattended_approvals_are_labelled_automatic
    Scene 5  test_audit_hash_chain_is_intact
    Scene 6  test_hold_never_changes_state

READER'S NOTE — helpers in a test file
    pytest only treats names starting with `test_` as tests. `scripted_llm`
    and `run` are ordinary helper functions that the tests call. Because
    pytest.ini lists `tests` on its `pythonpath`, other test files can import
    them too: test_checkpoint.py does `from test_end_to_end import scripted_llm`.

READER'S NOTE — why monkeypatch swaps in a fake LLM
    Every LLM-using node in cclf/nodes.py calls one private helper,
    nodes._llm_json(system, user), which sends the prompt to the real model
    and returns the parsed JSON reply. `monkeypatch.setattr(nodes,
    "_llm_json", fake)` replaces that module attribute with our fake for the
    duration of one test. The nodes look the name up at call time, so they
    call the fake without knowing it. Benefits:
      - no API key, no network, no cost;
      - the same answers every run, so the tests are deterministic;
      - we choose the answers, so we can steer the agent ("advance" vs
        "hold") and check exactly what the rest of the system does with them.
    When the test ends, pytest puts the real _llm_json back automatically.

READER'S NOTE — closures
    scripted_llm(action) defines an inner function `fake` and returns it.
    `fake` keeps access to `action` even after scripted_llm has returned;
    that remembered variable is called a *closure*. It lets one helper make
    an "always advance" fake or an "always hold" fake on demand.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       the test runner; imported but no `pytest.` helper is called.
# cclf         build_graph, the agent state, the four states, and Evidence.
# cclf.nodes   imported as a module object so its `_llm_json` attribute can
#              be replaced with monkeypatch.setattr(nodes, "_llm_json", ...).
# scenarios    MCAS_SCENARIO, the five evidence items fed to the graph.
# ===========================================================================

import pytest

from cclf import build_graph, CCLFAgentState, CommitmentState, Evidence
from cclf import nodes
from scenarios import MCAS_SCENARIO


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# (none) — the file defines two helper functions and four tests, no data.
# ===========================================================================


# ===========================================================================
# SCENE 1 — THE UNDERSTUDY
# scripted_llm(): build a fake LLM that gives each node a fixed, sensible reply.
# ===========================================================================

def scripted_llm(action: str):
    """
    Return a fake _llm_json that answers each node's prompt consistently.

    Enter:   action   what the fake transition evaluator should say:
                      "advance", "hold" or "escalate"
    Exit:    a function fake(system, user) -> dict with the same signature as
             nodes._llm_json, ready to be swapped in with monkeypatch

    The fake tells the four LLM-using nodes apart by the first line of their
    system prompt, then returns a reply in the JSON shape that node expects:
      evidence evaluator    novelty 0.9, independence 0.9 (so it is admissible)
      ACS inference engine  TRAJECTORY most likely, confidence 0.9
      ACO detector          ACO detected, condition C1
      transition evaluator  the `action` passed in
    Any other prompt raises AssertionError, so a new or renamed node fails
    the test loudly instead of being answered wrongly.
    """
    # PLAYERS IN THIS SCENE
    #   fake   the inner function returned to the caller (it remembers `action`)

    def fake(system: str, user: str) -> dict:
        # PLAYERS IN THIS SCENE
        #   header   the first line of the node's system prompt, used to tell
        #            which node is calling

        # --- Identify the caller -------------------------------------------
        # `user` (the per-call details) is ignored: the scripted answers do
        # not depend on the evidence.
        header = system.splitlines()[0]

        # --- Answer as the node expects ------------------------------------
        # The phrases checked below are the "You are a ..." openings of the
        # system prompts in cclf/nodes.py.
        if "evidence evaluator" in header:
            return {"novelty": 0.9, "independence": 0.9, "reasoning": "scripted"}
        if "ACS inference engine" in header:
            return {"p_open": 0.1, "p_trajectory": 0.7, "p_authority": 0.1,
                    "p_execution": 0.1, "confidence": 0.9, "reasoning": "scripted"}
        if "ACO (Adversarial Commitment Opacity) detector" in header:
            return {"aco_detected": True, "conditions_met": ["C1"], "reasoning": "scripted"}
        if "transition evaluator" in header:
            return {"action": action, "reasoning": "scripted"}

        # --- Unknown caller: fail loudly -----------------------------------
        raise AssertionError(f"unexpected prompt: {header}")
    return fake


# ===========================================================================
# SCENE 2 — THE RUN-THROUGH
# run(): stream evidence batches through a real graph with the fake LLM.
# ===========================================================================

def run(evidence_batches, monkeypatch, action="advance"):
    """
    Run the full graph once per evidence batch and return the final state.

    Enter:   evidence_batches   a list of batches; each batch is a list of
                                evidence dicts (the tests use one item per batch)
             monkeypatch        the calling test's monkeypatch fixture, passed
                                through so the patches are undone after that test
             action             what the fake evaluator proposes each cycle
                                (default "advance")
    Exit:    the CCLFAgentState after the last batch run (or after the batch
             that set should_terminate)

    This mirrors run_demo.py: one graph cycle per batch, with the checkpointer
    carrying state between cycles under the same thread_id.
    """
    # PLAYERS IN THIS SCENE
    #   graph    the compiled agent graph
    #   state    the agent state; replaced after every streamed chunk
    #   config   LangGraph run settings; thread_id "e2e" names this run
    #   batch    the evidence dicts for one cycle
    #   chunk    one state snapshot from graph.stream()

    # --- Setting the stage: swap in the fake and set the switches ----------
    # CCLF_AUTO_APPROVE=true makes human_review approve automatically and
    # label the decision "AUTO-APPROVED" in the audit log, instead of
    # calling input(). CCLF_OBSERVABILITY_ENABLED=false is a precaution
    # meaning "no OpenTelemetry" (build_graph() itself adds no telemetry).
    monkeypatch.setattr(nodes, "_llm_json", scripted_llm(action))
    monkeypatch.setenv("CCLF_AUTO_APPROVE", "true")
    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "false")

    # --- Setting the stage: build the graph --------------------------------
    # interrupt_before_human=False runs human_review inline (no pause), which
    # is safe here because auto-approve means it never reads the keyboard.
    graph = build_graph(interrupt_before_human=False, use_checkpointer=True)
    state = CCLFAgentState()
    config = {"configurable": {"thread_id": "e2e"}}

    # --- The action: one graph cycle per batch -----------------------------
    # `.extend(Evidence(**e) for e in batch)` turns each dict into an
    # Evidence object and adds them all to the buffer.
    for batch in evidence_batches:
        state.evidence_buffer.extend(Evidence(**e) for e in batch)
        for chunk in graph.stream(state, config=config, stream_mode="values"):
            state = CCLFAgentState.from_stream(chunk)
        # Stop feeding evidence once the agent has reached its end.
        if state.should_terminate:
            break
    return state


# ===========================================================================
# SCENE 3 — ALL THE WAY TO EXECUTION
# Proves: with an "advance" evaluator, the agent moves exactly one state per
# batch and terminates on reaching EXECUTION.
# ===========================================================================

def test_advances_one_state_per_batch_and_terminates(monkeypatch):
    """
    Five MCAS batches carry the agent from OPEN to EXECUTION, then it stops.

    Enter:   monkeypatch   pytest fixture, handed on to run()
    Exit:    passes if the final state is EXECUTION and should_terminate is set

    OPEN → TRAJECTORY → AUTHORITY → EXECUTION takes three batches; the
    `break` in run() means later batches are never sent.
    """
    # PLAYERS IN THIS SCENE
    #   state   the final agent state

    # --- Setting the stage / The action ------------------------------------
    # `[[e] for e in MCAS_SCENARIO]` wraps each item in its own list, making
    # five one-item batches.
    state = run([[e] for e in MCAS_SCENARIO], monkeypatch)
    # --- The verdict -------------------------------------------------------
    assert state.commitment_state == CommitmentState.EXECUTION
    assert state.should_terminate


# ===========================================================================
# SCENE 4 — NO PRETEND HUMANS
# Proves: when approval is automatic, every HUMAN_REVIEW audit entry says
# "AUTO-APPROVED", so the record never passes off a machine decision as a
# human one.
# ===========================================================================

def test_unattended_approvals_are_labelled_automatic(monkeypatch):
    """
    Every review in an unattended run is recorded as AUTO-APPROVED.

    Enter:   monkeypatch   pytest fixture, handed on to run()
    Exit:    passes if there is at least one HUMAN_REVIEW entry and all of
             them carry "AUTO-APPROVED" in their rationale
    """
    # PLAYERS IN THIS SCENE
    #   state     the final agent state
    #   reviews   the audit entries written by the human_review node

    # --- Setting the stage / The action ------------------------------------
    state = run([[e] for e in MCAS_SCENARIO], monkeypatch)
    reviews = [a for a in state.audit_log if a.event_type == "HUMAN_REVIEW"]

    # --- The verdict -------------------------------------------------------
    # `assert reviews` fails on an empty list: we must have actually
    # exercised human_review, or the all(...) check would pass vacuously.
    assert reviews
    assert all("AUTO-APPROVED" in a.payload["rationale"] for a in reviews)


# ===========================================================================
# SCENE 5 — THE RECORD HOLDS
# Proves: after a full run, the audit log is an unbroken hash chain.
# ===========================================================================

def test_audit_hash_chain_is_intact(monkeypatch):
    """
    Every audit entry from a real run links to the entry before it.

    Enter:   monkeypatch   pytest fixture, handed on to run()
    Exit:    passes if the first entry starts from "GENESIS" and each later
             entry's prev_hash equals its predecessor's entry_hash
    """
    # PLAYERS IN THIS SCENE
    #   state       the final agent state
    #   log         its audit log (a list of AuditEntry)
    #   prev, cur   two neighbouring entries

    # --- Setting the stage / The action ------------------------------------
    state = run([[e] for e in MCAS_SCENARIO], monkeypatch)
    log = state.audit_log

    # --- The verdict -------------------------------------------------------
    # zip(log, log[1:]) pairs each entry with the one after it:
    # (0, 1), (1, 2), (2, 3), ...
    assert log[0].prev_hash == "GENESIS"
    for prev, cur in zip(log, log[1:]):
        assert cur.prev_hash == prev.entry_hash


# ===========================================================================
# SCENE 6 — STANDING FIRM
# Proves: if the evaluator always says "hold", the state never moves and the
# agent never terminates, even after all five batches.
# ===========================================================================

def test_hold_never_changes_state(monkeypatch):
    """
    A "hold" evaluator leaves the agent in OPEN throughout.

    Enter:   monkeypatch   pytest fixture, handed on to run()
    Exit:    passes if the final state is OPEN and should_terminate is False
    """
    # PLAYERS IN THIS SCENE
    #   state   the final agent state

    # --- Setting the stage / The action ------------------------------------
    state = run([[e] for e in MCAS_SCENARIO], monkeypatch, action="hold")
    # --- The verdict -------------------------------------------------------
    assert state.commitment_state == CommitmentState.OPEN
    assert not state.should_terminate

# EXEUNT — end of file.

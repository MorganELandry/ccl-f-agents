"""
End-to-end graph runs with a scripted stand-in for the LLM.
Exercises every node — including human_review and the LLM-free guard —
without credentials or network access.

Run: pytest tests/ -v
"""

import pytest

from cclf import build_graph, CCLFAgentState, CommitmentState, Evidence
from cclf import nodes
from scenarios import MCAS_SCENARIO


def scripted_llm(action: str):
    """Return a fake _llm_json that answers each node's prompt consistently."""
    def fake(system: str, user: str) -> dict:
        header = system.splitlines()[0]
        if "evidence evaluator" in header:
            return {"novelty": 0.9, "independence": 0.9, "reasoning": "scripted"}
        if "ACS inference engine" in header:
            return {"p_open": 0.1, "p_trajectory": 0.7, "p_authority": 0.1,
                    "p_execution": 0.1, "confidence": 0.9, "reasoning": "scripted"}
        if "ACO (Adversarial Commitment Opacity) detector" in header:
            return {"aco_detected": True, "conditions_met": ["C1"], "reasoning": "scripted"}
        if "transition evaluator" in header:
            return {"action": action, "reasoning": "scripted"}
        raise AssertionError(f"unexpected prompt: {header}")
    return fake


def run(evidence_batches, monkeypatch, action="advance"):
    monkeypatch.setattr(nodes, "_llm_json", scripted_llm(action))
    monkeypatch.setenv("CCLF_AUTO_APPROVE", "true")
    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "false")
    graph = build_graph(interrupt_before_human=False, use_checkpointer=True)
    state = CCLFAgentState()
    config = {"configurable": {"thread_id": "e2e"}}
    for batch in evidence_batches:
        state.evidence_buffer.extend(Evidence(**e) for e in batch)
        for chunk in graph.stream(state, config=config, stream_mode="values"):
            state = CCLFAgentState.from_stream(chunk)
        if state.should_terminate:
            break
    return state


def test_advances_one_state_per_batch_and_terminates(monkeypatch):
    state = run([[e] for e in MCAS_SCENARIO], monkeypatch)
    assert state.commitment_state == CommitmentState.EXECUTION
    assert state.should_terminate


def test_unattended_approvals_are_labelled_automatic(monkeypatch):
    state = run([[e] for e in MCAS_SCENARIO], monkeypatch)
    reviews = [a for a in state.audit_log if a.event_type == "HUMAN_REVIEW"]
    assert reviews
    assert all("AUTO-APPROVED" in a.payload["rationale"] for a in reviews)


def test_audit_hash_chain_is_intact(monkeypatch):
    state = run([[e] for e in MCAS_SCENARIO], monkeypatch)
    log = state.audit_log
    assert log[0].prev_hash == "GENESIS"
    for prev, cur in zip(log, log[1:]):
        assert cur.prev_hash == prev.entry_hash


def test_hold_never_changes_state(monkeypatch):
    state = run([[e] for e in MCAS_SCENARIO], monkeypatch, action="hold")
    assert state.commitment_state == CommitmentState.OPEN
    assert not state.should_terminate

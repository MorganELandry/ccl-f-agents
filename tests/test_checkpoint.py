"""
Checkpoint round-trip and audit-integrity tests. No LLM credentials required.

Run: pytest tests/ -v
"""

import dataclasses
import io
import contextlib

import pytest

from cclf import build_graph, CCLFAgentState, CommitmentState, Evidence, AuditEntry
from cclf import nodes
from scenarios import MCAS_SCENARIO
from test_end_to_end import scripted_llm


def test_audit_entry_rebuilds_from_its_own_fields():
    entry = AuditEntry(0, "TEST", None, None, {"k": "v"}, prev_hash="GENESIS")
    rebuilt = AuditEntry(**dataclasses.asdict(entry))
    assert rebuilt.entry_hash == entry.entry_hash


def test_tampered_audit_entry_is_rejected():
    entry = AuditEntry(0, "TEST", None, None, {"k": "v"}, prev_hash="GENESIS")
    fields = dataclasses.asdict(entry)
    fields["payload"] = {"k": "forged"}
    with pytest.raises(ValueError, match="integrity"):
        AuditEntry(**fields)


def test_pause_update_resume(monkeypatch):
    """Service pattern: pause before human_review, record a decision, resume."""
    monkeypatch.setattr(nodes, "_llm_json", scripted_llm("advance"))
    monkeypatch.setenv("CCLF_AUTO_APPROVE", "true")   # node body must not read stdin
    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "false")
    graph = build_graph(interrupt_before_human=True, use_checkpointer=True)
    config = {"configurable": {"thread_id": "resume"}}
    state = CCLFAgentState()
    state.evidence_buffer.append(Evidence(**MCAS_SCENARIO[0]))

    with contextlib.redirect_stdout(io.StringIO()):
        graph.invoke(state, config)
        assert graph.get_state(config).next == ("human_review",)

        restored = CCLFAgentState.from_stream(graph.get_state(config).values)
        assert all(isinstance(a, AuditEntry) for a in restored.audit_log)

        graph.update_state(config, {"human_approval": True,
                                    "human_rationale": "Approved by review board"})
        final = CCLFAgentState.from_stream(graph.invoke(None, config))

    assert final.commitment_state == CommitmentState.TRAJECTORY
    assert graph.get_state(config).next == ()
    for prev, cur in zip(final.audit_log, final.audit_log[1:]):
        assert cur.prev_hash == prev.entry_hash

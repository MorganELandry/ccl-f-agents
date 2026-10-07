"""
THE INTERMISSION
A Play in Three Scenes
====================

PROLOGUE
--------
Checkpoint round-trip and audit-integrity tests. No LLM credentials required.

In production the agent does not wait at a keyboard for a human decision.
Instead the graph *pauses* just before the human_review node, its state is
saved by a LangGraph checkpointer, an outside system (a web form, a review
board) records the decision, and the graph is *resumed* from where it
stopped. This file proves that round trip works, and that the audit log
survives being saved and rebuilt without anyone being able to forge it.

Run: pytest tests/ -v

THE PLAYBILL
    Scene 1  test_audit_entry_rebuilds_from_its_own_fields   an honest copy rebuilds
    Scene 2  test_tampered_audit_entry_is_rejected           a forged copy is refused
    Scene 3  test_pause_update_resume                        pause, decide, resume

READER'S NOTE — pytest.raises
    Some behaviour is "this must fail". `with pytest.raises(ValueError,
    match="integrity"):` opens a block in which the code is *expected* to
    raise ValueError. The test passes only if that exception is raised and
    its message matches the regular expression "integrity" (a plain word
    here, so it means "the message contains 'integrity'"). If nothing is
    raised, or a different exception type is raised, the test fails.

READER'S NOTE — dataclasses.asdict
    AuditEntry is a dataclass. dataclasses.asdict(entry) turns it into a
    plain dict of {field name: value}. Feeding that dict back with
    AuditEntry(**fields) is exactly what happens when a checkpoint is
    loaded, which is why the first two scenes use it.

READER'S NOTE — the monkeypatch fixture and the fake LLM
    See tests/test_end_to_end.py: `scripted_llm` builds a fake replacement
    for cclf.nodes._llm_json, and monkeypatch.setattr swaps it in for one
    test so no API key or network is needed. It is imported from that file
    below, which works because pytest.ini puts tests/ on the import path
    (`pythonpath = . tests`).
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# dataclasses   for asdict(), to turn an AuditEntry into a plain dict.
# io            for StringIO, an in-memory "file" to swallow printed output.
# contextlib    for redirect_stdout(), which sends print() into that StringIO
#               so human_review's banner does not clutter the test output.
# pytest        for pytest.raises.
# cclf          the graph builder, agent state, states, Evidence, AuditEntry.
# cclf.nodes    the module whose _llm_json is replaced with a fake.
# scenarios     MCAS_SCENARIO, real evidence to feed the graph.
# test_end_to_end.scripted_llm   the shared fake-LLM factory.
# ===========================================================================

import dataclasses
import io
import contextlib

import pytest

from cclf import build_graph, CCLFAgentState, CommitmentState, Evidence, AuditEntry
from cclf import nodes
from scenarios import MCAS_SCENARIO
from test_end_to_end import scripted_llm


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# (none) — every test builds its own entries, state and graph.
# ===========================================================================


# ===========================================================================
# SCENE 1 — AN HONEST REPRINT
# Proves: an AuditEntry rebuilt from its own fields (including its stored
# hash) is accepted and has the same hash.
# ===========================================================================

def test_audit_entry_rebuilds_from_its_own_fields():
    """
    Round-tripping an entry through a dict reproduces the same hash.

    Enter:   (nothing)
    Exit:    passes if the rebuilt entry's entry_hash equals the original's

    AuditEntry recomputes its hash on creation and, if a hash was supplied,
    checks the two match. An unchanged copy must therefore pass that check.
    """
    # PLAYERS IN THIS SCENE
    #   entry     an original audit entry
    #   rebuilt   a new entry built from entry's fields

    # --- Setting the stage -------------------------------------------------
    # Positional arguments: sequence=0, event_type="TEST", from_state=None,
    # to_state=None, payload={"k": "v"}; prev_hash is given by keyword.
    entry = AuditEntry(0, "TEST", None, None, {"k": "v"}, prev_hash="GENESIS")
    # --- The action --------------------------------------------------------
    rebuilt = AuditEntry(**dataclasses.asdict(entry))
    # --- The verdict -------------------------------------------------------
    assert rebuilt.entry_hash == entry.entry_hash


# ===========================================================================
# SCENE 2 — THE FORGERY
# Proves: changing an entry's payload but keeping its old hash is caught and
# rejected with a ValueError mentioning "integrity".
# ===========================================================================

def test_tampered_audit_entry_is_rejected():
    """
    An entry whose contents no longer match its stored hash is refused.

    Enter:   (nothing)
    Exit:    passes if building the tampered entry raises ValueError whose
             message contains "integrity"
    """
    # PLAYERS IN THIS SCENE
    #   entry    an original audit entry
    #   fields   its fields as a dict, then edited to forge the payload

    # --- Setting the stage: make a genuine entry, then tamper with it ------
    entry = AuditEntry(0, "TEST", None, None, {"k": "v"}, prev_hash="GENESIS")
    fields = dataclasses.asdict(entry)
    fields["payload"] = {"k": "forged"}

    # --- The action and the verdict ----------------------------------------
    # fields["entry_hash"] still holds the hash of the *original* payload,
    # so AuditEntry's integrity check must refuse it.
    with pytest.raises(ValueError, match="integrity"):
        AuditEntry(**fields)


# ===========================================================================
# SCENE 3 — PAUSE, DECIDE, RESUME
# Proves: the graph stops before human_review, its saved state rebuilds
# cleanly, an outside decision can be written in, and resuming applies it.
# ===========================================================================

def test_pause_update_resume(monkeypatch):
    """
    Service pattern: pause before human_review, record a decision, resume.

    Enter:   monkeypatch   pytest fixture used to swap in the fake LLM and
                           set environment variables for this test only
    Exit:    passes if the run pauses at human_review, resumes to TRAJECTORY,
             finishes with nothing left to run, and keeps an unbroken audit chain
    """
    # PLAYERS IN THIS SCENE
    #   graph       the compiled agent graph, set to pause before human_review
    #   config      LangGraph run settings; thread_id "resume" is the key under
    #               which the checkpointer saves this run's state
    #   state       the starting agent state, with one evidence item
    #   restored    the paused state, rebuilt from the checkpoint
    #   final       the state after resuming to the end
    #   prev, cur   two neighbouring audit entries

    # --- Setting the stage: fake LLM and switches --------------------------
    # The fake evaluator always says "advance", so the graph proposes
    # OPEN → TRAJECTORY and routes to human_review.
    monkeypatch.setattr(nodes, "_llm_json", scripted_llm("advance"))
    monkeypatch.setenv("CCLF_AUTO_APPROVE", "true")   # node body must not read stdin
    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "false")

    # --- Setting the stage: graph and starting state -----------------------
    # interrupt_before_human=True is the production setting: stop and save
    # just before human_review runs.
    graph = build_graph(interrupt_before_human=True, use_checkpointer=True)
    config = {"configurable": {"thread_id": "resume"}}
    state = CCLFAgentState()
    state.evidence_buffer.append(Evidence(**MCAS_SCENARIO[0]))

    # Everything printed inside this `with` block (human_review prints a
    # banner) goes into a throw-away StringIO instead of the terminal.
    with contextlib.redirect_stdout(io.StringIO()):
        # --- The action, part 1: run until the pause -----------------------
        # graph.get_state(config).next is a tuple naming the node(s) that
        # will run next; ("human_review",) means "paused right before it".
        graph.invoke(state, config)
        assert graph.get_state(config).next == ("human_review",)

        # --- The verdict, part 1: the saved state rebuilds properly --------
        # Every audit entry must come back as a real AuditEntry (and so has
        # passed its own integrity check), not as a loose dict.
        restored = CCLFAgentState.from_stream(graph.get_state(config).values)
        assert all(isinstance(a, AuditEntry) for a in restored.audit_log)

        # --- The action, part 2: the outside world decides, then resume ----
        # update_state() writes the human decision into the saved state.
        # invoke(None, config) means "no new input: carry on from the
        # checkpoint". human_review then runs; because CCLF_AUTO_APPROVE is
        # set it approves without reading stdin (writing its own
        # "AUTO-APPROVED" rationale over the one supplied here), and
        # apply_transition commits the move.
        graph.update_state(config, {"human_approval": True,
                                    "human_rationale": "Approved by review board"})
        final = CCLFAgentState.from_stream(graph.invoke(None, config))

    # --- The verdict, part 2 -----------------------------------------------
    # The move happened, nothing is left to run (an empty tuple), and the
    # audit chain is unbroken from end to end.
    assert final.commitment_state == CommitmentState.TRAJECTORY
    assert graph.get_state(config).next == ()
    for prev, cur in zip(final.audit_log, final.audit_log[1:]):
        assert cur.prev_hash == prev.entry_hash

# EXEUNT — end of file.

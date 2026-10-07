"""
THE ADVISOR WHO MAY ONLY PROPOSE
A Play in Eleven Scenes
================================

PROLOGUE
--------
Tests for cclf/advisor.py and cclf/graph.py: the probabilistic automation
(a language model) and the event pipeline that feeds the supervisor.

What CCL-F v0.2 asks of probabilistic automation (AI Applications, spec
lines 1296-1320):
  - "AI as Coordination Signal Classifier" (line 1308): identify which of
    the six signal types a report is.
  - As a behavioural specification (line 1310): "never classify
    off-envelope conditions as nominal without validating evidence".
  - EES (line 494): model output never counts as independent evidence.

So the advisor may only propose. These tests use fake models (plain
Python functions) to show three things: when the model is missing or
talks nonsense, the fallback is never nominal; when a model proposes
nominal without evidence, the supervisor refuses it exactly as it would
refuse a human; and the pipeline records refused operations as outcomes
rather than crashing a replay.

No network is used. The one test that builds an Advisor without a fake
removes OPENAI_API_KEY first, so building a real client fails and the
advisor falls back.

THE PLAYBILL
    Scene 1   fake_model()                    (helper) a model with a fixed reply
    Scene 2   test_unavailable_model_falls_back_never_nominal
    Scene 3   test_bad_replies_fall_back_never_nominal     (parametrized, 4 runs)
    Scene 4   test_good_reply_is_parsed_and_marked_from_model
    Scene 5   test_model_nominal_without_evidence_is_refused_by_supervisor
    Scene 6   test_model_proposal_is_not_evidence
    Scene 7   test_report_event_runs_through_build_graph
    Scene 8   test_replay_records_refusals_and_continues
    Scene 9   test_unknown_and_private_operations_are_refused
    Scene 10  test_assess_reports_coherence_for_decision_events
    Scene 11  test_unknown_decision_is_refused_not_raised  (was a code defect; now fixed)

READER'S NOTE — monkeypatch.delenv
    `monkeypatch.delenv("NAME", raising=False)` removes an environment
    variable for the duration of one test and puts it back afterwards.
    raising=False means "no error if it was not set to begin with".

READER'S NOTE — a closure as a fake
    fake_model(reply) returns an inner function that remembers `reply`.
    Each call to fake_model makes a new fake with its own fixed answer.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# json      builds fake JSON replies.
# pytest    fixtures, parametrize, monkeypatch, xfail.
# cclf      Advisor, AuditTrail, CommitmentState, ExecutionClass,
#           OperationalState, SignalType, Supervisor, build_graph, replay.
# cclf.advisor   FALLBACK_STATE, FALLBACK_TYPE.
# stagehands     CUST, entries.
# ===========================================================================

import json

import pytest

from cclf import (
    Advisor, AuditTrail, CommitmentState, ExecutionClass, OperationalState, SignalType,
    Supervisor, build_graph, replay,
)
from cclf.advisor import FALLBACK_STATE, FALLBACK_TYPE
from stagehands import entries


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# NOMINAL_REPLY — what an over-confident model says about a cold launch.
NOMINAL_REPLY = json.dumps({"signal_type": "constraint", "operational_state": "nominal",
                            "rationale": "prior flights were fine"})

# REPORT — a "report" event: raw text for the advisor to interpret.
REPORT = {"op": "report", "signal_id": "r1", "by": "engineer",
          "text": "Forecast O-ring temperature is below all test data."}


# ===========================================================================
# SCENE 1 — A MODEL WITH ONE LINE
# fake_model(): a stand-in model that always gives the same reply.
# ===========================================================================

def fake_model(reply):
    """
    Build a fake model function.

    Enter:   reply   the text to return, or an Exception instance to raise
    Exit:    a function (system, user) -> str, the shape Advisor expects
    """
    def ask(system, user):
        if isinstance(reply, Exception):
            raise reply
        return reply
    return ask


# ===========================================================================
# SCENE 2 — NOBODY HOME
# Proves: with no model available the advisor falls back to the
# conservative reading, never nominal, and says it is not from a model.
# ===========================================================================

def test_unavailable_model_falls_back_never_nominal(monkeypatch):
    """
    An Advisor with no API key returns the fallback proposal.

    Enter:   monkeypatch   removes OPENAI_API_KEY so no client can be built
    Exit:    passes if the proposal is the fallback, not nominal, and
             from_model is False
    """
    # PLAYERS IN THIS SCENE
    #   p   the proposal

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = Advisor(backend="openai").propose("anything")
    assert (p.signal_type, p.operational_state) == (FALLBACK_TYPE, FALLBACK_STATE)
    assert p.operational_state != OperationalState.NOMINAL
    assert p.from_model is False


# ===========================================================================
# SCENE 3 — NONSENSE IN, CAUTION OUT
# Proves: an error, non-JSON, or JSON naming unknown types or states all
# give the fallback. (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("reply", [
    RuntimeError("rate limited"),
    "I think it's probably fine.",
    json.dumps({"signal_type": "vibes", "operational_state": "nominal"}),
    json.dumps({"signal_type": "constraint", "operational_state": "mostly_ok"}),
], ids=["raises", "prose", "bad-type", "bad-state"])
def test_bad_replies_fall_back_never_nominal(reply):
    """
    Unusable model replies give the fallback, never nominal.

    Enter:   reply   an exception or unusable text
    Exit:    passes if the state is the fallback and from_model is False
    """
    p = Advisor(ask=fake_model(reply)).propose("report")
    assert p.operational_state == FALLBACK_STATE != OperationalState.NOMINAL
    assert p.from_model is False


# ===========================================================================
# SCENE 4 — A USABLE ANSWER
# Proves: a well-formed reply (even wrapped in chatter) is parsed and
# marked as coming from the model.
# ===========================================================================

def test_good_reply_is_parsed_and_marked_from_model():
    """
    JSON inside prose is parsed into a Proposal with from_model True.

    Enter:   (nothing)
    Exit:    passes if type, state and from_model are as replied
    """
    p = Advisor(ask=fake_model("Sure: " + NOMINAL_REPLY)).propose("report")
    assert p.signal_type == SignalType.CONSTRAINT
    assert p.operational_state == OperationalState.NOMINAL
    assert p.from_model is True


# ===========================================================================
# SCENE 5 — THE MODEL SAYS NOMINAL; THE SUPERVISOR SAYS NO
# Proves: line 1310 and Rule 2: a model's nominal without validating
# evidence is refused, the refusal names the model as proposer, and the
# signal is registered with the type the model proposed.
# ===========================================================================

def test_model_nominal_without_evidence_is_refused_by_supervisor():
    """
    A report event with a fake model proposing nominal ends elevated_uncertainty.

    Enter:   (nothing)
    Exit:    passes if the signal is a classified constraint at
             elevated_uncertainty and CLASSIFICATION_REJECTED records
             proposed_by_model True
    """
    # PLAYERS IN THIS SCENE
    #   sv    the Supervisor after replay
    #   sig   the registered signal

    sv = replay([REPORT], advisor=Advisor(ask=fake_model(NOMINAL_REPLY)))
    sig = sv.signals["r1"]
    assert sig.signal_type == SignalType.CONSTRAINT
    assert sig.state == CommitmentState.CLASSIFIED
    assert sig.operational_state == OperationalState.ELEVATED_UNCERTAINTY
    [rejected] = entries(sv, "CLASSIFICATION_REJECTED")
    assert rejected.payload["proposed_by_model"] is True


# ===========================================================================
# SCENE 6 — WORDS ARE NOT EVIDENCE
# Proves: line 494, model output recorded as evidence cannot close a
# signal by evidence, even when it is new.
# ===========================================================================

def test_model_proposal_is_not_evidence():
    """
    Citing a model_output evidence item yields authority, not evidence, closure.

    Enter:   (nothing)
    Exit:    passes if the signal ends closed_authority
    """
    # PLAYERS IN THIS SCENE
    #   events   a scripted history ending in a closure citing model output
    #   sv       the Supervisor after replay

    events = [
        REPORT,
        {"op": "open_review", "signal_id": "r1", "by": "engineer"},
        {"op": "add_evidence", "evidence_id": "llm-1", "content": "It is safe.",
         "source": "assistant", "kind": "model_output", "produced_by": "gpt",
         "by": "manager", "signal_ids": ["r1"]},
        {"op": "attempt_closure", "signal_id": "r1", "by": "manager",
         "referent": "customer", "evidence_ids": ["llm-1"]},
    ]
    sv = replay(events, advisor=Advisor(ask=fake_model(NOMINAL_REPLY)))
    assert sv.signals["r1"].state == CommitmentState.CLOSED_AUTHORITY


# ===========================================================================
# SCENE 7 — ONE EVENT THROUGH THE GRAPH
# Proves: build_graph() compiles, a report event passes interpret -> apply
# -> assess, and the output carries the proposal and outcome.
# ===========================================================================

def test_report_event_runs_through_build_graph():
    """
    graph.invoke on a report event returns proposal and outcome.

    Enter:   (nothing)
    Exit:    passes if the proposal names the model's type, the outcome
             says registered, refused is False, and the audit chain verifies
    """
    # PLAYERS IN THIS SCENE
    #   sv      a fresh Supervisor
    #   graph   the compiled pipeline
    #   out     the final pipeline state

    sv = Supervisor()
    graph = build_graph(sv, Advisor(ask=fake_model(NOMINAL_REPLY)))
    out = graph.invoke({"event": REPORT})
    assert out["proposal"]["signal_type"] == "constraint"
    assert out["proposal"]["from_model"] is True
    assert out["refused"] is False and out["outcome"].startswith("registered r1")
    assert AuditTrail.verify(sv.audit.entries())[0]


# ===========================================================================
# SCENE 8 — A REFUSAL IS A RESULT, NOT A CRASH
# Proves: a refused operation is recorded as the outcome and the replay
# carries on to the next event.
# ===========================================================================

def test_replay_records_refusals_and_continues():
    """
    Closing a signal before review is refused; the next event still runs.

    Enter:   (nothing)
    Exit:    passes if the on_event callback sees refused=True for the
             early closure and refused=False for the following open_review
    """
    # PLAYERS IN THIS SCENE
    #   outcomes   (op, refused) for each event, collected by the callback
    #   events     report, premature closure, then open_review

    outcomes = []
    events = [
        REPORT,
        {"op": "attempt_closure", "signal_id": "r1", "by": "vp", "referent": "customer"},
        {"op": "open_review", "signal_id": "r1", "by": "engineer"},
    ]
    sv = replay(events, advisor=Advisor(ask=fake_model(NOMINAL_REPLY)),
                on_event=lambda ev, out: outcomes.append((ev["op"], out["refused"])))
    assert outcomes == [("report", False), ("attempt_closure", True), ("open_review", False)]
    assert sv.signals["r1"].state == CommitmentState.UNDER_REVIEW


# ===========================================================================
# SCENE 9 — NO BACKSTAGE ACCESS
# Proves: the pipeline only calls public Supervisor operations; unknown
# and underscore-prefixed names are refused.
# ===========================================================================

def test_unknown_and_private_operations_are_refused():
    """
    "_move" and "teleport" events are refused, and change nothing.

    Enter:   (nothing)
    Exit:    passes if both outcomes are refused and the audit log is empty
    """
    # PLAYERS IN THIS SCENE
    #   sv      a fresh Supervisor
    #   graph   the compiled pipeline
    #   op      each forbidden operation name

    sv = Supervisor()
    graph = build_graph(sv, Advisor(ask=fake_model(NOMINAL_REPLY)))
    for op in ("_move", "teleport"):
        assert graph.invoke({"event": {"op": op, "by": "x"}})["refused"] is True
    assert len(sv.audit) == 0


# ===========================================================================
# SCENE 10 — THE ASSESSOR'S NOTE
# Proves: an event that names a decision gets a coherence snapshot.
# ===========================================================================

def test_assess_reports_coherence_for_decision_events():
    """
    A register_decision event returns a coherence dict for that decision.

    Enter:   (nothing)
    Exit:    passes if coherence names the decision and has five factors
    """
    # PLAYERS IN THIS SCENE
    #   sv      a fresh Supervisor
    #   graph   the compiled pipeline
    #   out     the pipeline output

    sv = Supervisor()
    graph = build_graph(sv, Advisor(ask=fake_model(NOMINAL_REPLY)))
    out = graph.invoke({"event": {"op": "register_decision", "decision_id": "d",
                                  "description": "x", "execution_class": "routine",
                                  "signal_ids": [], "by": "director"}})
    assert out["coherence"]["decision"] == "d"
    assert len(out["coherence"]["factors"]) == 5
    # The event's plain string "routine" was turned into the enum on the way in.
    assert sv.decisions["d"].execution_class is ExecutionClass.ROUTINE


# ===========================================================================
# SCENE 11 — A DECISION THAT DOES NOT EXIST
# Proves: a request about an unknown decision is a
# refused operation like any other, so a replay records it and continues.
# ===========================================================================

def test_unknown_decision_is_refused_not_raised():
    """
    request_execution on an unknown decision comes back refused.

    Enter:   (nothing)
    Exit:    passes if replay finishes and the outcome is refused
    """
    # PLAYERS IN THIS SCENE
    #   outcomes   the refused flag for each event

    outcomes = []
    replay([{"op": "request_execution", "decision_id": "nope", "by": "director"}],
           advisor=Advisor(ask=fake_model(NOMINAL_REPLY)),
           on_event=lambda ev, out: outcomes.append(out["refused"]))
    assert outcomes == [True]

# EXEUNT — end of file.

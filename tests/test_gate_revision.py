"""
THE GATE, REVISED
A Play in Twelve Scenes
=======================

PROLOGUE
--------
Tests for the October 2026 operational definitions of the execution gates
that are not covered elsewhere (CCL-F v0.2, Layer 4, Execution Gates,
"Operational definitions"), and for the threshold rule of Layer 2,
Escalation Conditions:

  Classification acknowledged: "every such signal carries an operational
    state, and every signal classified nominal cites an External Evidence
    Source that the condition lies within validated parameters".
  Open loops documented: "no such signal remains merely registered, and
    every loop still open has a named steward."
  Classification stabilized: "no signal has been reclassified toward a less
    cautious state since its first review opened: to nominal from any other
    state, or to elevated uncertainty from off-envelope, experimental, or
    containment. A domain may register a stabilization window instead ...
    The test runs over the signal's whole history, so closing and
    reopening a loop does not restart it. ... Second, the decision carries
    the registration Rule 3 requires — what is known, what is assumed, and
    what remains uncertain — recorded with its acceptance."
  Thresholds: "Raising a threshold above its default needs its rationale
    logged".
  The latch: a loop already carried open by one decision is signed for
    again by the next.

THE PLAYBILL
    Prelude   sv (fixture), STABLE_MSG
    Scene 1   test_nominal_classification_on_acceptor_evidence_is_not_acknowledged
    Scene 2   test_open_loop_without_steward_is_not_documented
    Scene 3   test_lowerings_by_definition                (parametrized, 7 runs)
    Scene 4   test_lowering_before_first_review_does_not_count
    Scene 5   test_close_and_reopen_does_not_restart_stability
    Scene 6   test_stabilization_window
    Scene 7   test_rule3_registration_required             (parametrized, 4 runs)
    Scene 8   test_raised_threshold_needs_rationale        (parametrized, 3 runs)
    Scene 9   test_lowered_threshold_needs_nothing_and_settings_are_logged
    Scene 10  test_second_decision_signs_for_a_loop_already_executed_open
    Scene 11  test_executed_open_loop_cannot_be_reopened_or_exited
    Scene 12  test_elevated_gate_needs_nothing_irreversible
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       fixtures, parametrize, raises.
# cclf         the runtime under test and its vocabulary.
# stagehands   shared set-up helpers (see tests/stagehands.py).
# ===========================================================================

import pytest

from cclf import (
    CommitmentState, ExecutionClass, ExitType, OperationalState, Settings, SignalType,
    Supervisor, TransitionRefused,
)
from stagehands import CUST, PROCESS, RULE3, TECH, add_ees, decision, entries, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# S, O — short aliases.
S = CommitmentState
O = OperationalState

# STABLE_MSG — prefix of the "classification stabilized" failures.
STABLE_MSG = "classification not stabilized"


# ===========================================================================
# PRELUDE — the fixture
# ===========================================================================

@pytest.fixture
def sv():
    """
    A new, empty Supervisor with default settings.

    Enter:   (nothing)
    Exit:    Supervisor()
    """
    return Supervisor()


def unstable(sv, decision_id="d"):
    """
    The signal ids named by the per-signal stability failure, if any.

    Enter:   sv, decision_id
    Exit:    the failure string naming signals, or None
    """
    return next((f for f in sv.request_execution(decision_id, "director").failures
                 if f.startswith(STABLE_MSG + ": [")), None)


# ===========================================================================
# SCENE 1 — VALIDATED BY THE OWNER'S OWN READING
# Proves: classification acknowledged re-checks a nominal classification at
# the gate with the accepting agent excluded: a measurement the acceptor
# produced does not validate it ("the agent accepting the decision it
# supports").
# ===========================================================================

def test_nominal_classification_on_acceptor_evidence_is_not_acknowledged(sv):
    """
    Setting the stage: "u" classified nominal by "engineer" citing a reading
    produced by "director" (accepted at classification time). Decision "d"
    is accepted by "director". The verdict: the gate reports the nominal
    signal as not acknowledged; a decision accepted by someone else does
    not.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   needle   the expected failure prefix

    sv.register_signal("u", SignalType.UNCERTAINTY, "u", "engineer", TECH, PROCESS,
                       steward="steward")
    add_ees(sv, "director-reading", produced_by="director")
    assert sv.classify("u", O.NOMINAL, "engineer", ["director-reading"]) == O.NOMINAL
    decision(sv, "d", ["u"], execution_class=ExecutionClass.ELEVATED)
    needle = "classification not acknowledged: nominal without an External Evidence Source"
    assert any(f.startswith(needle) for f in sv.request_execution("d", "director").failures)
    decision(sv, "d2", ["u"], execution_class=ExecutionClass.ELEVATED, by="other-director")
    assert not any(f.startswith(needle)
                   for f in sv.request_execution("d2", "other-director").failures)


# ===========================================================================
# SCENE 2 — SOMEONE ANSWERABLE FOR EACH OPEN LOOP
# Proves: "every loop still open has a named steward."
# ===========================================================================

def test_open_loop_without_steward_is_not_documented(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if an open uncertainty with no steward fails the elevated
             gate, and passes once a delegated exit names one
    """
    # PLAYERS IN THIS SCENE
    #   needle   the expected failure

    to_review(sv, "u", SignalType.UNCERTAINTY, steward=None)
    decision(sv, "d", ["u"], execution_class=ExecutionClass.ELEVATED)
    needle = "open loops not documented: no named steward: ['u']"
    assert needle in sv.request_execution("d", "director").failures
    sv.exit("u", ExitType.DELEGATED, "manager", "handed over", successor="new-steward")
    result = sv.request_execution("d", "director")
    assert needle not in result.failures and result.permitted


# ===========================================================================
# SCENE 3 — WHICH WAY IS LESS CAUTIOUS
# Proves: the lowerings are exactly "to nominal from any other state, or to
# elevated uncertainty from off-envelope, experimental, or containment";
# raising and re-confirming never destabilize.
# ===========================================================================

@pytest.mark.parametrize("before, after, lowers", [
    (O.CONTAINMENT, O.ELEVATED_UNCERTAINTY, True),
    (O.OFF_ENVELOPE, O.ELEVATED_UNCERTAINTY, True),
    (O.EXPERIMENTAL, O.NOMINAL, True),
    (O.ELEVATED_UNCERTAINTY, O.NOMINAL, True),
    (O.OFF_ENVELOPE, O.EXPERIMENTAL, False),
    (O.ELEVATED_UNCERTAINTY, O.CONTAINMENT, False),
    (O.EXPERIMENTAL, O.EXPERIMENTAL, False),
], ids=lambda v: v.value if isinstance(v, O) else str(v))
def test_lowerings_by_definition(sv, before, after, lowers):
    """
    Enter:   sv                      fixture
             before, after, lowers   one reclassification and the verdict
    Exit:    passes if the stability failure names "u" exactly when the
             change lowers caution
    """
    # PLAYERS IN THIS SCENE
    #   evidence   validating evidence, for a nominal classification

    to_review(sv, "u", SignalType.UNCERTAINTY, state=before)
    add_ees(sv, "validation")
    evidence = ["validation"] if after == O.NOMINAL else []
    assert sv.classify("u", after, "engineer", evidence) == after
    decision(sv, "d", ["u"])
    assert (unstable(sv) == f"{STABLE_MSG}: ['u']") is lowers


# ===========================================================================
# SCENE 4 — BEFORE ANYONE LOOKED
# Proves: the test runs "since its first review opened": a lowering before
# review opened does not count.
# ===========================================================================

def test_lowering_before_first_review_does_not_count(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if containment -> elevated uncertainty before review
             opens leaves the signal stable
    """
    sv.register_signal("u", SignalType.UNCERTAINTY, "u", "engineer", TECH, PROCESS,
                       steward="steward")
    sv.classify("u", O.CONTAINMENT, "engineer")
    sv.classify("u", O.ELEVATED_UNCERTAINTY, "engineer")
    sv.open_review("u", "engineer")
    decision(sv, "d", ["u"])
    assert unstable(sv) is None


# ===========================================================================
# SCENE 5 — CLOSING AND REOPENING DOES NOT WIPE THE SLATE
# Proves: "The test runs over the signal's whole history, so closing and
# reopening a loop does not restart it."
# ===========================================================================

def test_close_and_reopen_does_not_restart_stability(sv):
    """
    Setting the stage: "u" lowered during its first review, closed, then
    reopened (a new review opening). The verdict: still unstable.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    to_review(sv, "u", SignalType.UNCERTAINTY, state=O.EXPERIMENTAL)
    sv.classify("u", O.ELEVATED_UNCERTAINTY, "engineer")           # a lowering
    sv.attempt_closure("u", "vp", CUST)
    sv.reopen("u", "auditor", "look again")
    assert sv.signals["u"].review_opened_at > sv.signals["u"].first_review_opened_at
    decision(sv, "d", ["u"])
    assert unstable(sv) == f"{STABLE_MSG}: ['u']"


# ===========================================================================
# SCENE 6 — A REGISTERED WINDOW
# Proves: with Settings.stabilization_window, only lowerings within that
# many ticks before the request count.
# ===========================================================================

def test_stabilization_window():
    """
    Enter:   (nothing)
    Exit:    passes if, with a 3-tick window, a recent lowering counts and
             the same lowering followed by enough quiet ticks does not
    """
    # PLAYERS IN THIS SCENE
    #   sv   a Supervisor with a 3-tick window
    #   n    filler operations that advance the clock

    sv = Supervisor(Settings(stabilization_window=3))
    to_review(sv, "u", SignalType.UNCERTAINTY, state=O.EXPERIMENTAL)
    decision(sv, "d", ["u"])
    sv.classify("u", O.ELEVATED_UNCERTAINTY, "engineer")           # a lowering, now
    assert unstable(sv) == f"{STABLE_MSG}: ['u']"
    for n in range(4):                                             # quiet ticks
        add_ees(sv, f"filler-{n}")
    assert unstable(sv) is None


# ===========================================================================
# SCENE 7 — WHAT IS KNOWN, ASSUMED, UNCERTAIN
# Proves: the decision's Rule 3 registration, recorded with its acceptance,
# is part of "classification stabilized"; each of the three is needed.
# ===========================================================================

@pytest.mark.parametrize("missing", [None, "known", "assumed", "uncertain"])
def test_rule3_registration_required(sv, missing):
    """
    Enter:   sv        fixture
             missing   which part is left blank (None: none)
    Exit:    passes if the Rule 3 failure appears exactly when one is blank
    """
    # PLAYERS IN THIS SCENE
    #   rule3     the registration passed
    #   failure   whether the Rule 3 failure appeared

    to_review(sv, "c")
    decision(sv, "d", ["c"], accept=False)
    rule3 = dict(RULE3)
    if missing:
        rule3[missing] = " "
    sv.accept_decision("d", "director", "accepted", risk_claim="safe", **rule3)
    failure = any("Rule 3 registration" in f
                  for f in sv.request_execution("d", "director").failures)
    assert failure is (missing is not None)
    assert sv.decisions["d"].rule3_known == rule3["known"]


# ===========================================================================
# SCENE 8 — RAISING A THRESHOLD IS A CLAIM THAT NEEDS A REASON
# Proves: Settings with the recurrence, authority-closure or sender-discount
# threshold above the spec's default is refused without a rationale.
# ===========================================================================

@pytest.mark.parametrize("field, value", [
    ("recurrence_threshold", 4), ("authority_closure_threshold", 2),
    ("sender_discount_threshold", 5)])
def test_raised_threshold_needs_rationale(field, value):
    """
    Enter:   field, value   the threshold raised
    Exit:    passes if ValueError is raised without a rationale, and the
             Settings is built with one
    """
    with pytest.raises(ValueError, match="rationale"):
        Settings(**{field: value})
    assert getattr(Settings(**{field: value}, threshold_rationale="domain study 12"),
                   field) == value


# ===========================================================================
# SCENE 9 — LOWER IS ALWAYS ALLOWED, AND EVERYTHING IS LOGGED
# Proves: "A domain may set a lower count"; the supervisor logs its
# settings, with the rationale, when it is created.
# ===========================================================================

def test_lowered_threshold_needs_nothing_and_settings_are_logged():
    """
    Enter:   (nothing)
    Exit:    passes if a lowered threshold needs no rationale and the first
             audit entry is SETTINGS carrying thresholds and rationale
    """
    # PLAYERS IN THIS SCENE
    #   low, high   two supervisors
    #   first       each one's first audit entry

    low = Supervisor(Settings(recurrence_threshold=2))
    high = Supervisor(Settings(recurrence_threshold=5, threshold_rationale="rare events"))
    for sv, expected in ((low, 2), (high, 5)):
        first = sv.audit.entries()[0]
        assert first.event == "SETTINGS" and first.payload["recurrence_threshold"] == expected
    assert high.audit.entries()[0].payload["threshold_rationale"] == "rare events"


# ===========================================================================
# SCENE 10 — CARRIED OPEN TWICE
# Proves: a loop already latched by one decision's override is signed for
# again by the next decision's authorizer, without a state move.
# ===========================================================================

def test_second_decision_signs_for_a_loop_already_executed_open(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if "c" carries two authorization records, its steward is
             the second authorizer, and only one latch transition is logged
    """
    # PLAYERS IN THIS SCENE
    #   moves   the logged transitions into executed_open for "c"

    to_review(sv, "c")
    decision(sv, "d1", ["c"])
    decision(sv, "d2", ["c"])
    assert sv.request_execution("d1", "auditor-1", override_rationale="go").permitted
    assert sv.request_execution("d2", "auditor-2", override_rationale="go again").permitted
    assert [a.decision_id for a in sv.signals["c"].open_loop_authorizations] == ["d1", "d2"]
    assert sv.signals["c"].steward == "auditor-2"
    moves = [e for e in entries(sv, "TRANSITION")
             if e.payload["signal"] == "c" and e.payload["to"] == "executed_open"]
    assert len(moves) == 1


# ===========================================================================
# SCENE 11 — THE LATCH HOLDS
# Proves: executed_open is terminal: no reopen, no exit.
# ===========================================================================

def test_executed_open_loop_cannot_be_reopened_or_exited(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if reopen() and exit() are refused and the state stays
    """
    to_review(sv, "c")
    decision(sv, "d", ["c"])
    sv.request_execution("d", "auditor", override_rationale="go")
    with pytest.raises(TransitionRefused):
        sv.reopen("c", "auditor", "again")
    with pytest.raises(TransitionRefused):
        sv.exit("c", ExitType.TERMINAL, "auditor", "done", open_loop_state="x")
    assert sv.signals["c"].state == S.EXECUTED_OPEN and not sv.signals["c"].is_open


# ===========================================================================
# SCENE 12 — THE ELEVATED GATE STAYS ELEVATED
# Proves: the risk-claim, Rule 3 and other-loop requirements are
# irreversible-only: an elevated decision accepted with a rationale alone,
# over an open uncertainty with a steward, executes.
# ===========================================================================

def test_elevated_gate_needs_nothing_irreversible(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if permitted with no failures
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult

    to_review(sv, "u", SignalType.UNCERTAINTY)
    decision(sv, "d", ["u"], execution_class=ExecutionClass.ELEVATED, risk_checked=False)
    result = sv.request_execution("d", "director")
    assert result.permitted and result.failures == []


# EXEUNT — end of file.

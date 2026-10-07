"""
THE INTERLOCK
A Play in Seventeen Scenes
==========================

PROLOGUE
--------
Tests for Supervisor.request_execution(), the execution gates of CCL-F v0.2
Layer 4 (spec lines 988-996), together with what the gates draw on:

  Execution Gates table (lines 990-994):
    Irreversible  No open constraint loops; classification stabilized;
                  recurrence groups reviewed; minimum evidence closure ratio met
    Elevated      Classification acknowledged; open loops documented
    Routine       Signal registration complete
  Coherence threshold (line 960): "A score below the domain-configured
    threshold blocks irreversible execution pending acknowledgment."
  Overrides (line 996): "Gates can be overridden. Every override is
    permanently logged with the agent's identity, rationale, and timestamp."
  Rule 4 (line 338): "Before any execution-class decision, a single agent
    must explicitly accept authorization, risk acceptance, and rationale
    documentation as their responsibility."
  Lock-in (lines 946, 1216, 1236): overriding with open constraint loops is
    "open-loop irreversible execution", recorded as under_review ->
    trajectory_lock with a lock-in closure record.
  Layer 0 (lines 159-268): with the Architecture Precondition unmet, gates
    are "structurally void". The runtime reports the voids it can check.
  Reversibility Logic (line 506) and Operational States (lines 1190-1192).

THE PLAYBILL
    Scene 1   test_routine_needs_only_registration
    Scene 2   test_routine_with_unregistered_signal_is_blocked  (was a spec mismatch; now fixed)
    Scene 3   test_elevated_needs_classification_and_documented_loops
    Scene 4   test_irreversible_blocks_open_constraint_loops
    Scene 5   test_irreversible_blocks_unstable_classification
    Scene 6   test_irreversible_blocks_unreviewed_recurrence_group
    Scene 7   test_evidence_closure_ratio                      (impl. decision D4)
    Scene 8   test_coherence_threshold_blocks_irreversible     (impl. decision D3)
    Scene 9   test_clean_irreversible_decision_is_permitted
    Scene 10  test_rule4_acceptance_required_and_not_overridable
    Scene 11  test_override_logged_with_identity_rationale_and_time
    Scene 12  test_override_latches_open_constraints_into_trajectory_lock
    Scene 13  test_layer0_voids_are_reported                    (impl. decision D9)
    Scene 14  test_exited_constraint_still_counts_as_open      (was a spec mismatch; now fixed)
    Scene 15  test_off_envelope_or_containment_needs_more     (was a spec mismatch, now fixed;
                                                                parametrized, 2 runs)
    Scene 16  test_executed_decision_cannot_execute_again
    Scene 17  test_elevated_override_does_not_lock
    Scene 18  test_evidence_for_unknown_signal_changes_nothing
    Scene 19  test_suppressed_signal_blocks_the_first_irreversible_request
    Scene 20  test_duplicate_decision_is_refused
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       fixtures, parametrize, raises.
# cclf         Architecture, ClosureType, CommitmentState, ExecutionClass,
#              ExitType, OperationalState, Settings, SignalType, Supervisor,
#              TransitionRefused.
# stagehands   CUST, TECH, PROCESS, to_review, add_ees, decision, entries.
# ===========================================================================

import pytest

from cclf import (
    Architecture, ClosureType, CommitmentState, ExecutionClass, ExitType, OperationalState,
    Settings, SignalType, Supervisor, TransitionRefused,
)
from stagehands import CUST, PROCESS, TECH, add_ees, decision, entries, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# S, O, X — short aliases for CommitmentState, OperationalState, ExecutionClass.
S = CommitmentState
O = OperationalState
X = ExecutionClass


# ===========================================================================
# THE FIXTURE AND A HELPER
# ===========================================================================

@pytest.fixture
def sv():
    """
    A new, empty Supervisor with default settings.

    Enter:   (nothing)
    Exit:    Supervisor()
    """
    return Supervisor()


def evidence_close(sv, signal_id):
    """
    Close a signal under review by novel, independent evidence.

    Enter:   sv, signal_id   a signal currently under_review
    Exit:    the ClosureRecord (typed EVIDENCE)
    """
    add_ees(sv, f"ev-{signal_id}", [signal_id])
    return sv.attempt_closure(signal_id, "chief-engineer", CUST, [f"ev-{signal_id}"])


# ===========================================================================
# SCENE 1 — THE ROUTINE GATE
# Proves: "Routine — Signal registration complete": a merely registered,
# unclassified signal is enough.
# ===========================================================================

def test_routine_needs_only_registration(sv):
    """
    A routine decision over a registered, unclassified signal is permitted.

    Enter:   sv   fixture
    Exit:    passes if permitted with no failures and EXECUTION_PERMITTED logged
    """
    sv.register_signal("u", SignalType.UNCERTAINTY, "d", "eng", TECH, PROCESS)
    decision(sv, "d", ["u"], X.ROUTINE)
    result = sv.request_execution("d", "director")
    assert result.permitted and result.failures == []
    assert "EXECUTION_PERMITTED" in sv.audit.events()


# ===========================================================================
# SCENE 2 — A DECISION RESTING ON A SIGNAL NOBODY REGISTERED
# Proves: "Signal registration complete" is not met when
# a decision names a signal that was never registered.
# ===========================================================================

def test_routine_with_unregistered_signal_is_blocked(sv):
    """
    A routine decision naming an unregistered signal is not permitted.

    Enter:   sv   fixture
    Exit:    passes if the gate refuses
    """
    decision(sv, "d", ["never-registered"], X.ROUTINE)
    assert not sv.request_execution("d", "director").permitted


# ===========================================================================
# SCENE 3 — THE ELEVATED GATE
# Proves: "Elevated — Classification acknowledged; open loops documented":
# unclassified fails; classified and in review passes.
# ===========================================================================

def test_elevated_needs_classification_and_documented_loops(sv):
    """
    Elevated fails over a registered-only signal and passes once it is in review.

    Enter:   sv   fixture
    Exit:    passes if the first decision's failures name classification and
             undocumented loops, and the second decision is permitted
    """
    sv.register_signal("u", SignalType.UNCERTAINTY, "d", "eng", TECH, PROCESS)
    decision(sv, "d1", ["u"], X.ELEVATED)
    failures = sv.request_execution("d1", "director").failures
    assert any("classification not acknowledged" in f for f in failures)
    assert any("open loops not documented" in f for f in failures)
    # --- Now acknowledge the classification and open (document) the loop ---
    to_review(sv, "u2", signal_type=SignalType.UNCERTAINTY)
    decision(sv, "d2", ["u2"], X.ELEVATED)
    assert sv.request_execution("d2", "director").permitted


# ===========================================================================
# SCENE 4 — NO OPEN CONSTRAINT LOOPS
# Proves: the first irreversible requirement; an open uncertainty (not a
# constraint) does not trip it.
# ===========================================================================

def test_irreversible_blocks_open_constraint_loops(sv):
    """
    An open constraint blocks an irreversible decision; an open uncertainty
    alone does not produce that failure.

    Enter:   sv   fixture
    Exit:    passes if the failure names "c" but not "u"
    """
    to_review(sv, "c")
    to_review(sv, "u", signal_type=SignalType.UNCERTAINTY)
    decision(sv, "d", ["c", "u"])
    result = sv.request_execution("d", "director")
    assert not result.permitted
    assert "open constraint loops: ['c']" in result.failures


# ===========================================================================
# SCENE 5 — CLASSIFICATION STABILIZED
# Proves: the second irreversible requirement (Rule 3: "held stable before
# irreversible action proceeds"); reclassification during review is
# instability.
# ===========================================================================

def test_irreversible_blocks_unstable_classification(sv):
    """
    Implementation-decision test for the stability rule (D8: stable means
    classified and not reclassified since review last opened). A signal
    reclassified after review opened blocks the gate even when closed by
    evidence.

    Enter:   sv   fixture
    Exit:    passes if the failure "classification not stabilized" names "c"
    """
    to_review(sv, "c")
    sv.classify("c", O.EXPERIMENTAL, "eng")
    evidence_close(sv, "c")
    decision(sv, "d", ["c"])
    assert "classification not stabilized: ['c']" in \
        sv.request_execution("d", "director").failures


# ===========================================================================
# SCENE 6 — RECURRENCE GROUPS REVIEWED
# Proves: the third irreversible requirement; resolving the group's
# structural review clears it.
# ===========================================================================

def test_irreversible_blocks_unreviewed_recurrence_group(sv):
    """
    An open recurrence-group review blocks; after Rule 8 resolution it does not.

    Enter:   sv   fixture
    Exit:    passes if the failure names the group before resolution, and the
             decision is permitted after resolution and evidence closure
    """
    for n in (1, 2, 3):
        sv.register_signal(f"m{n}", SignalType.UNCERTAINTY, "d", "eng", TECH, PROCESS,
                           recurrence_group="g")
    decision(sv, "d", ["m1", "m2", "m3"])
    assert "recurrence groups not reviewed: ['g']" in \
        sv.request_execution("d", "director").failures
    sv.resolve_review("R1", "board", "change the joint design")
    for n in (1, 2, 3):
        sv.classify(f"m{n}", O.ELEVATED_UNCERTAINTY, "eng")
        sv.open_review(f"m{n}", "eng")
        evidence_close(sv, f"m{n}")
    assert sv.request_execution("d", "director").permitted


# ===========================================================================
# SCENE 7 — MINIMUM EVIDENCE CLOSURE RATIO
# Proves (implementation decision D4): the ratio threshold is 0.5 and is
# met exactly at 0.5.
# ===========================================================================

def test_evidence_closure_ratio(sv):
    """
    Implementation-decision test (D4: minimum evidence closure ratio 0.5).
    All-authority closures (ratio 0) fail; one evidence plus one authority
    closure (ratio 0.5) passes the ratio check.

    Enter:   sv   fixture
    Exit:    passes if d1 names the ratio failure and d2 has no ratio failure
    """
    to_review(sv, "u1", signal_type=SignalType.UNCERTAINTY)
    sv.attempt_closure("u1", "vp", CUST)
    decision(sv, "d1", ["u1"])
    assert any("evidence closure ratio 0.00" in f
               for f in sv.request_execution("d1", "director").failures)
    to_review(sv, "u2", signal_type=SignalType.UNCERTAINTY)
    to_review(sv, "u3", signal_type=SignalType.UNCERTAINTY)
    evidence_close(sv, "u2")
    sv.attempt_closure("u3", "vp", CUST)
    decision(sv, "d2", ["u2", "u3"])
    assert not any("evidence closure ratio" in f
                   for f in sv.request_execution("d2", "director").failures)


# ===========================================================================
# SCENE 8 — BELOW THE LINE
# Proves (implementation decision D3): a coherence score below the
# configured threshold blocks irreversible execution, and the threshold is
# domain-configurable through Settings.
# ===========================================================================

def test_coherence_threshold_blocks_irreversible():
    """
    Implementation-decision test (D3: default threshold 0.6). A decision
    whose only failure is coherence is blocked at threshold 0.95 and the
    same history is permitted at 0.6.

    Enter:   (nothing)
    Exit:    passes if the strict supervisor reports only the coherence
             failure and the default supervisor permits
    """
    # PLAYERS IN THIS SCENE
    #   strict, lax   supervisors with thresholds 0.95 and the default
    #   sv            each in turn

    strict, lax = Supervisor(Settings(coherence_threshold=0.95)), Supervisor()
    assert lax.settings.coherence_threshold == 0.6
    for sv in (strict, lax):
        to_review(sv, "u", signal_type=SignalType.UNCERTAINTY)   # open, not a constraint
        decision(sv, "d", ["u"])
    failures = strict.request_execution("d", "director").failures
    assert len(failures) == 1 and failures[0].startswith("coherence")
    assert lax.request_execution("d", "director").permitted


# ===========================================================================
# SCENE 9 — THE GATE OPENS FOR CLEAN WORK
# Proves: when every requirement is met the irreversible gate permits, not
# overridden; "The system does not prevent decisions" (line 996).
# ===========================================================================

def test_clean_irreversible_decision_is_permitted(sv):
    """
    Evidence-closed constraint, stable classification: permitted, no override.

    Enter:   sv   fixture
    Exit:    passes if permitted, not overridden, the decision is executed
    """
    to_review(sv, "c")
    evidence_close(sv, "c")
    decision(sv, "d", ["c"])
    result = sv.request_execution("d", "director")
    assert result.permitted and not result.overridden
    assert sv.decisions["d"].executed


# ===========================================================================
# SCENE 10 — RULE 4 CANNOT BE WAIVED
# Proves: Rule 4 acceptance is required for every class, needs a
# rationale, and an override does not stand in for it.
# ===========================================================================

def test_rule4_acceptance_required_and_not_overridable(sv):
    """
    No acceptance: refused even with an override. Acceptance needs a rationale.

    Enter:   sv   fixture
    Exit:    passes if every class is refused (also when overriding), the
             refusal is logged, nothing executes, and a blank acceptance
             rationale raises
    """
    # PLAYERS IN THIS SCENE
    #   cls      each execution class
    #   result   the GateResult

    sv.register_signal("u", SignalType.UNCERTAINTY, "d", "eng", TECH, PROCESS)
    for cls in X:
        decision(sv, f"d-{cls.value}", ["u"], cls, accept=False)
        result = sv.request_execution(f"d-{cls.value}", "director",
                                      override_rationale="we must go")
        assert not result.permitted and not result.overridden
        assert any("Rule 4" in f for f in result.failures)
        assert not sv.decisions[f"d-{cls.value}"].executed
    assert len(entries(sv, "EXECUTION_REFUSED")) == 3
    assert entries(sv, "GATE_OVERRIDE") == []
    with pytest.raises(TransitionRefused):
        sv.accept_decision("d-routine", "director", "")


# ===========================================================================
# SCENE 11 — THE OVERRIDE ON THE PERMANENT RECORD
# Proves: line 996, the override is logged with identity, rationale and
# timestamp, along with what it overrode.
# ===========================================================================

def test_override_logged_with_identity_rationale_and_time(sv):
    """
    A GATE_OVERRIDE entry carries actor, rationale, time and the failures.

    Enter:   sv   fixture
    Exit:    passes if the result is permitted+overridden and the entry has
             actor "kilminster", the rationale, a positive `at` and failures
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult
    #   log      the single GATE_OVERRIDE entry

    to_review(sv, "c")
    decision(sv, "d", ["c"])
    result = sv.request_execution("d", "kilminster", override_rationale="management call")
    assert result.permitted and result.overridden
    [log] = entries(sv, "GATE_OVERRIDE")
    assert log.actor == "kilminster"
    assert log.payload["rationale"] == "management call"
    assert log.at > 0
    assert log.payload["failures"] == result.failures


# ===========================================================================
# SCENE 12 — OPEN-LOOP IRREVERSIBLE EXECUTION
# Proves: lines 946 and 1236: overriding an irreversible gate latches each
# constraint still under review into trajectory_lock with a LOCK_IN closure
# record, and the event is logged as open-loop irreversible execution.
# ===========================================================================

def test_override_latches_open_constraints_into_trajectory_lock(sv):
    """
    Constraints under review become trajectory_lock with a LOCK_IN record;
    a non-constraint stays under review.

    Enter:   sv   fixture
    Exit:    passes if "c" is trajectory_lock with a LOCK_IN record carrying
             the override rationale, "u" is untouched, and
             OPEN_LOOP_IRREVERSIBLE_EXECUTION lists "c" as locked
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult
    #   rec      the lock-in ClosureRecord on "c"

    to_review(sv, "c")
    to_review(sv, "u", signal_type=SignalType.UNCERTAINTY)
    decision(sv, "d", ["c", "u"])
    result = sv.request_execution("d", "director", override_rationale="proceed")
    assert result.locked_signals == ["c"]
    assert sv.signals["c"].state == S.TRAJECTORY_LOCK
    rec = sv.signals["c"].closures[-1]
    assert rec.closure_type == ClosureType.LOCK_IN and rec.rationale == "proceed"
    assert sv.signals["u"].state == S.UNDER_REVIEW
    assert entries(sv, "OPEN_LOOP_IRREVERSIBLE_EXECUTION")[0].payload["locked"] == ["c"]


# ===========================================================================
# SCENE 13 — THE ARCHITECTURE BENEATH THE GATE
# Proves: Layer 0 voids the runtime can check are reported and mark the
# gate architecture_void: AP-A (no steward), AP.1b (no successor), AP-F
# (every reporter is an interested party), AP.2 (untested channel).
# ===========================================================================

def test_layer0_voids_are_reported():
    """
    Implementation-decision test (D9: only AP-A, AP.1b, AP-F, AP-G and AP.2
    are checkable from registered facts; AP.3/4/5/8 need interviews).
    Each of four registered voids appears among the gate's failures.

    Enter:   (nothing)
    Exit:    passes if architecture_void is True and each void prefix appears
    """
    # PLAYERS IN THIS SCENE
    #   arch     the registered architecture with a captured channel and an
    #            untested hotline
    #   sv       a Supervisor holding it
    #   result   the GateResult

    arch = Architecture(reporters={"mode": {"maker"}}, interested_parties={"mode": {"maker"}},
                        channels_tested={"hotline": False})
    sv = Supervisor(architecture=arch)
    to_review(sv, "a", signal_type=SignalType.ANOMALY, steward=None, successor=None,
              failure_mode="mode")
    evidence_close(sv, "a")
    decision(sv, "d", ["a"])
    result = sv.request_execution("d", "director")
    assert result.architecture_void and not result.permitted
    for prefix in ("AP-A", "AP.1b", "AP-F", "AP.2"):
        assert any(f.startswith(prefix) for f in result.failures), prefix


# ===========================================================================
# SCENE 14 — PARKED IS NOT RESOLVED
# Proves: a deferred constraint is "Open — indefinite,
# documented" (line 533); Reversibility Logic (line 506) still requires
# evidence closure or an explicit open-loop authorization.
# ===========================================================================

def test_exited_constraint_still_counts_as_open(sv):
    """
    An irreversible decision over a deferred constraint is not permitted
    without an override.

    Enter:   sv   fixture
    Exit:    passes if the gate refuses
    """
    to_review(sv, "c")
    sv.exit("c", ExitType.DEFERRED, "steward", "parked for later")
    decision(sv, "d", ["c"])
    assert not sv.request_execution("d", "director").permitted


# ===========================================================================
# SCENE 15 — OFF THE MAP, OR IN CONTAINMENT
# Proves: line 1190, off-envelope requires
# "Evidence-based classification ... before irreversible execution";
# line 1192, containment requires "extraordinary justification and
# independent steward review". Neither is satisfied by an anomaly whose
# structural review is still open.
# ===========================================================================

@pytest.mark.parametrize("state", [O.OFF_ENVELOPE, O.CONTAINMENT], ids=lambda s: s.value)
def test_off_envelope_or_containment_needs_more(state):
    """
    An irreversible decision over an escalated off-envelope/containment
    anomaly is not permitted without an override.

    Enter:   state   OFF_ENVELOPE or CONTAINMENT
    Exit:    passes if the gate refuses
    """
    # PLAYERS IN THIS SCENE
    #   sv   a Supervisor holding one escalated anomaly

    sv = Supervisor()
    to_review(sv, "a", signal_type=SignalType.ANOMALY, state=state)
    assert sv.signals["a"].state == S.ESCALATED
    decision(sv, "d", ["a"])
    assert not sv.request_execution("d", "director").permitted


# ===========================================================================
# SCENE 16 — IRREVERSIBLE MEANS ONCE
# Proves: an executed decision cannot be executed again.
# ===========================================================================

def test_executed_decision_cannot_execute_again(sv):
    """
    A second execution request on an executed decision raises.

    Enter:   sv   fixture
    Exit:    passes if TransitionRefused is raised
    """
    to_review(sv, "u", signal_type=SignalType.UNCERTAINTY)
    decision(sv, "d", ["u"], X.ROUTINE)
    sv.request_execution("d", "director")
    with pytest.raises(TransitionRefused):
        sv.request_execution("d", "director")


# ===========================================================================
# SCENE 17 — AN ELEVATED OVERRIDE
# Proves: lock-in is about irreversible execution; overriding an elevated
# gate is logged but latches nothing.
# ===========================================================================

def test_elevated_override_does_not_lock(sv):
    """
    Overriding a failing elevated gate logs GATE_OVERRIDE but locks nothing.

    Enter:   sv   fixture
    Exit:    passes if permitted+overridden, no locked signals, the
             constraint still under review, no OPEN_LOOP_IRREVERSIBLE_EXECUTION
    """
    to_review(sv, "c")
    sv.register_signal("u", SignalType.UNCERTAINTY, "d", "eng", TECH, PROCESS)
    decision(sv, "d", ["c", "u"], X.ELEVATED)
    result = sv.request_execution("d", "director", override_rationale="proceed")
    assert result.permitted and result.overridden and result.locked_signals == []
    assert sv.signals["c"].state == S.UNDER_REVIEW
    assert entries(sv, "OPEN_LOOP_IRREVERSIBLE_EXECUTION") == []


# ===========================================================================
# SCENE 18 — ALL OR NOTHING
# Proves: evidence naming an unknown signal is refused whole; nothing is
# stored, nothing is attached, and the clock does not move.
# ===========================================================================

def test_evidence_for_unknown_signal_changes_nothing(sv):
    """
    add_evidence with one good and one unknown signal id stores nothing.

    Enter:   sv   fixture
    Exit:    passes if TransitionRefused is raised, the evidence is absent,
             the known signal has no evidence attached, and the audit trail
             is the same length as before
    """
    # PLAYERS IN THIS SCENE
    #   before   audit length before the failed call

    to_review(sv, "c")
    before = len(sv.audit.entries())
    with pytest.raises(TransitionRefused):
        add_ees(sv, "e1", signal_ids=["c", "no-such-signal"])
    assert "e1" not in sv.evidence
    assert sv.signals["c"].evidence_ids == []
    assert len(sv.audit.entries()) == before


# ===========================================================================
# SCENE 19 — WHAT WAS HIDDEN BLOCKS AT ONCE
# Proves: a suppressed signal escalates on the first irreversible request,
# and that escalation's open review blocks the same request.
# ===========================================================================

def test_suppressed_signal_blocks_the_first_irreversible_request(sv):
    """
    The very first irreversible request over a suppressed signal is refused.

    Enter:   sv   fixture
    Exit:    passes if the gate refuses, and SUPPRESSED_BEFORE_EXECUTION
             was escalated during that request
    """
    to_review(sv, "c")
    sv.suppress("c", "program-manager", "out of scope for this flight")
    decision(sv, "d", ["c"])
    assert not sv.request_execution("d", "director").permitted
    assert any("suppressed_before_execution" in str(e.payload)
               for e in sv.audit.entries() if e.event.startswith("ESCALAT"))


# ===========================================================================
# SCENE 20 — ONE NAME, ONE DECISION
# Proves: registering a second decision under an existing id is refused,
# so an accepted decision cannot be silently replaced.
# ===========================================================================

def test_duplicate_decision_is_refused(sv):
    """
    register_decision with an id already in use raises.

    Enter:   sv   fixture
    Exit:    passes if TransitionRefused is raised and the original
             decision (and its acceptance) is untouched
    """
    to_review(sv, "u", signal_type=SignalType.UNCERTAINTY)
    first = decision(sv, "d", ["u"], X.ROUTINE)
    with pytest.raises(TransitionRefused):
        sv.register_decision("d", "replacement", X.ROUTINE, ["u"], "someone-else")
    assert sv.decisions["d"] is first and first.accepted_by == "director"

# EXEUNT — end of file.

"""
THE NINE ALARMS
A Play in Seventeen Scenes
=========================

PROLOGUE
--------
Tests for automatic escalation to structural review in cclf/supervisor.py,
derived from CCL-F v0.2 Layer 2, Escalation Conditions (spec lines
508-520), Rules 7 and 8 (lines 402-431), Credibility Discounting
(lines 470-480) and the escalated -> under_review recovery transition
(line 886).

The spec lists nine conditions that "automatically escalate to structural
review". The code names them in EscalationCondition. Each scene below makes
one condition happen and checks that a StructuralReview with that
condition is opened. Then the recovery rules are checked: an escalated
signal cannot close (Rules 7-8), and it returns to under_review only when
the review documents a coordination-model update (Rule 8: "the review
produce a documented update to the coordination model — not a
re-approval of existing practice").

Settings the spec leaves open are the code's choices (D1, D5, D6, D7):
recurrence threshold 3, authority-closure threshold 1 ("exceeds", so two
closures), sender-discount threshold 3, and the "stable or improving"
accuracy rule. Tests that pin those numbers say so in their docstrings.

THE PLAYBILL
    Scene 1   test_recurrence_threshold_escalates_on_third_member   (impl. decision D1)
    Scene 2   test_off_envelope_or_containment_escalates          (parametrized, 2 runs)
    Scene 3   test_authority_closure_count_escalates             (impl. decision D5)
    Scene 4   test_authority_count_ignores_closure_order          (was a spec mismatch; now fixed)
    Scene 5   test_role_switch_on_constraint_escalates
    Scene 6   test_role_switch_on_non_constraint_does_not_escalate
    Scene 7   test_lock_in_with_open_constraints_escalates
    Scene 8   test_suppressed_before_execution_escalates
    Scene 9   test_framing_adopted_over_open_constraints_escalates
    Scene 10  test_credibility_discounting_escalates_only_for_accurate_senders
    Scene 11  test_sender_discount_recurrence_is_ap_g          (impl. decision D6)
    Scene 12  test_accuracy_rule               (impl. decision D7; parametrized, 8 runs)
    Scene 13  test_escalated_signal_cannot_close
    Scene 14  test_resolution_requires_model_update
    Scene 15  test_resolution_recovers_signals_to_under_review
    Scene 16  test_signal_held_by_two_reviews_waits_for_both
    Scene 17  test_recovery_only_through_model_update        (was a spec mismatch, now fixed;
                                                              parametrized, 2 runs)

READER'S NOTE — Settings
    Supervisor(Settings(...)) changes a threshold for one supervisor only.
    The tests use the defaults unless a scene is about a threshold.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       fixtures, parametrize, raises, xfail.
# cclf         CommitmentState, EscalationCondition, ExecutionClass,
#              OperationalState, SignalType, Supervisor, TransitionRefused.
# stagehands   CUST, TECH, PROCESS, to_review, decision.
# ===========================================================================

import pytest

from cclf import (
    CommitmentState, EscalationCondition, ExecutionClass, OperationalState, SignalType,
    Supervisor, TransitionRefused,
)
from stagehands import CUST, PROCESS, TECH, decision, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# S, E, O — short aliases used in every verdict.
S = CommitmentState
E = EscalationCondition
O = OperationalState


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


def conditions(sv):
    """
    The set of escalation conditions that have opened a review so far.

    Enter:   sv   a Supervisor
    Exit:    a set of EscalationCondition values
    """
    return {r.condition for r in sv.reviews}


# ===========================================================================
# SCENE 1 — THE THIRD EROSION
# Proves: Rule 7, the recurrence group escalates at the threshold, and every
# member is named by the review.
# ===========================================================================

def test_recurrence_threshold_escalates_on_third_member(sv):
    """
    Implementation-decision test (D1: recurrence threshold 3, from the
    Challenger note "The escalation threshold was crossed after the third
    occurrence", line 412). Two members: no review. Third: one review
    naming all three.

    Enter:   sv   fixture
    Exit:    passes if no review after two members and one RECURRENCE_THRESHOLD
             review naming m1..m3 after the third
    """
    # PLAYERS IN THIS SCENE
    #   n        member number
    #   review   the recurrence review

    for n in (1, 2):
        sv.register_signal(f"m{n}", SignalType.ANOMALY, "erosion", "eng", TECH, PROCESS,
                           recurrence_group="g")
    assert sv.reviews == []
    sv.register_signal("m3", SignalType.ANOMALY, "erosion", "eng", TECH, PROCESS,
                       recurrence_group="g")
    [review] = sv.reviews
    assert review.condition == E.RECURRENCE_THRESHOLD
    assert review.scope == "group:g"
    assert sorted(review.signal_ids) == ["m1", "m2", "m3"]


# ===========================================================================
# SCENE 2 — OUTSIDE THE ENVELOPE
# Proves: "Operational state classified as off-envelope or containment"
# escalates, and a signal whose review opens afterwards lands in escalated.
# ===========================================================================

@pytest.mark.parametrize("state", [O.OFF_ENVELOPE, O.CONTAINMENT], ids=lambda s: s.value)
def test_off_envelope_or_containment_escalates(sv, state):
    """
    Classifying off-envelope or containment opens a review on the signal.

    Enter:   sv      fixture
             state   OFF_ENVELOPE or CONTAINMENT
    Exit:    passes if the condition is OFF_ENVELOPE_OR_CONTAINMENT and,
             once review opens, the signal is escalated
    """
    to_review(sv, "c", state=state)
    assert conditions(sv) == {E.OFF_ENVELOPE_OR_CONTAINMENT}
    assert sv.signals["c"].state == S.ESCALATED


# ===========================================================================
# SCENE 3 — TOO MANY OVERRIDES
# Proves: "Authority closure count exceeds threshold on an irreversible
# decision" escalates.
# ===========================================================================

def test_authority_closure_count_escalates(sv):
    """
    Implementation-decision test (D5: threshold 1, so the second authority
    closure on an irreversible decision's signals escalates).

    Enter:   sv   fixture
    Exit:    passes if one closure gives no review and two give one
             AUTHORITY_CLOSURE_COUNT review scoped to the decision
    """
    to_review(sv, "a")
    to_review(sv, "b")
    decision(sv, "d", ["a", "b"])
    sv.attempt_closure("a", "vp", CUST)
    assert sv.reviews == []
    sv.attempt_closure("b", "vp", CUST)
    assert [(r.condition, r.scope) for r in sv.reviews] == \
        [(E.AUTHORITY_CLOSURE_COUNT, "decision:d")]


# ===========================================================================
# SCENE 4 — THE COUNT DOES NOT CARE WHEN THE DECISION WAS FILED
# Proves: the condition is a property of the decision's
# signals, not of the order in which the decision and closures were recorded.
# ===========================================================================

def test_authority_count_ignores_closure_order(sv):
    """
    Two authority closures, then the irreversible decision: still escalates
    (at the latest when execution is requested).

    Enter:   sv   fixture
    Exit:    passes if an AUTHORITY_CLOSURE_COUNT review exists after the
             execution request
    """
    to_review(sv, "a")
    to_review(sv, "b")
    sv.attempt_closure("a", "vp", CUST)
    sv.attempt_closure("b", "vp", CUST)
    decision(sv, "d", ["a", "b"])
    sv.request_execution("d", "director")
    assert E.AUTHORITY_CLOSURE_COUNT in conditions(sv)


# ===========================================================================
# SCENE 5 — THE HAT CHANGE ON A CONSTRAINT
# Proves: "Role-switch closure detected on a safety-constraint signal"
# escalates. The closure stands (line 468: "not blocked, but permanently
# recorded and requiring independent review").
# ===========================================================================

def test_role_switch_on_constraint_escalates(sv):
    """
    A role-switch closure on a constraint opens a review; the state stays closed.

    Enter:   sv   fixture
    Exit:    passes if ROLE_SWITCH_ON_CONSTRAINT is opened naming the signal
             and the signal is closed_role_switch
    """
    to_review(sv, "c", by="lund")
    sv.attempt_closure("c", "lund", CUST)
    assert [r.condition for r in sv.reviews] == [E.ROLE_SWITCH_ON_CONSTRAINT]
    assert sv.reviews[0].signal_ids == ["c"]
    assert sv.signals["c"].state == S.CLOSED_ROLE_SWITCH


# ===========================================================================
# SCENE 6 — THE HAT CHANGE ELSEWHERE
# Proves: the condition is specific to safety-constraint signals.
# ===========================================================================

def test_role_switch_on_non_constraint_does_not_escalate(sv):
    """
    A role-switch closure on an uncertainty signal opens no review.

    Enter:   sv   fixture
    Exit:    passes if no review exists
    """
    to_review(sv, "u", signal_type=SignalType.UNCERTAINTY, by="lund")
    sv.attempt_closure("u", "lund", CUST)
    assert sv.reviews == []


# ===========================================================================
# SCENE 7 — LOCK-IN OVER OPEN CONSTRAINTS
# Proves: "Lock-in closure detected in the presence of open constraint
# loops" escalates when an irreversible gate is overridden.
# ===========================================================================

def test_lock_in_with_open_constraints_escalates(sv):
    """
    Overriding an irreversible gate with a constraint under review escalates.

    Enter:   sv   fixture
    Exit:    passes if LOCK_IN_WITH_OPEN_CONSTRAINTS is opened for the decision
    """
    to_review(sv, "c")
    decision(sv, "d", ["c"])
    sv.request_execution("d", "director", override_rationale="schedule")
    assert any(r.condition == E.LOCK_IN_WITH_OPEN_CONSTRAINTS and r.scope == "decision:d"
               for r in sv.reviews)


# ===========================================================================
# SCENE 8 — THE MISSING SIGNAL
# Proves: "Suppressed signal detected before irreversible execution".
# ===========================================================================

def test_suppressed_before_execution_escalates(sv):
    """
    An irreversible execution request with a suppressed signal escalates.

    Enter:   sv   fixture
    Exit:    passes if SUPPRESSED_BEFORE_EXECUTION is opened for the decision
    """
    to_review(sv, "u", signal_type=SignalType.UNCERTAINTY)
    sv.suppress("u", "manager", "lost in the noise")
    decision(sv, "d", ["u"])
    sv.request_execution("d", "director")
    assert any(r.condition == E.SUPPRESSED_BEFORE_EXECUTION for r in sv.reviews)


# ===========================================================================
# SCENE 9 — "PROVE IT'S UNSAFE"
# Proves: "Framing signal achieves frame adoption while technical
# constraint signals remain open"; and per line 1212 the displaced signal
# is suppressed.
# ===========================================================================

def test_framing_adopted_over_open_constraints_escalates(sv):
    """
    Adopting a frame that displaces an open constraint suppresses it and escalates.

    Enter:   sv   fixture
    Exit:    passes if the constraint ends suppressed, the frame
             closed_authority, and FRAMING_ADOPTED_OVER_OPEN_CONSTRAINTS opened
    """
    to_review(sv, "c")
    to_review(sv, "frame", signal_type=SignalType.FRAMING, by="mgr", referent=CUST)
    sv.adopt_frame("frame", "mgr", ["c"], "burden of proof inverted")
    assert sv.signals["c"].state == S.SUPPRESSED
    assert sv.signals["frame"].state == S.CLOSED_AUTHORITY
    assert E.FRAMING_ADOPTED_OVER_OPEN_CONSTRAINTS in conditions(sv)


# ===========================================================================
# SCENE 10 — SHOOTING THE MESSENGER
# Proves: line 519, discounting escalates against an agent "whose signals
# show a stable or improving accuracy rate", and not otherwise (line 229:
# "Where negative characterization tracks accurately with genuinely poor
# signal quality, no void exists").
# ===========================================================================

def test_credibility_discounting_escalates_only_for_accurate_senders(sv):
    """
    Discounting an accurate sender escalates; discounting an inaccurate one does not.

    Enter:   sv   fixture
    Exit:    passes if exactly one CREDIBILITY_DISCOUNTING review exists,
             scoped to the accurate agent
    """
    sv.record_signal_outcome("accurate", True, "observer")
    sv.record_signal_outcome("inaccurate", False, "observer")
    sv.record_credibility_discount("accurate", "manager", "too direct")
    sv.record_credibility_discount("inaccurate", "manager", "too direct")
    assert [(r.condition, r.scope) for r in sv.reviews] == \
        [(E.CREDIBILITY_DISCOUNTING, "agent:accurate")]


# ===========================================================================
# SCENE 11 — AP-G: THE CHANNEL IS BROKEN FOR THIS SENDER
# Proves: line 520, recurrence of discounting against the same agent
# escalates as Sender Discount and becomes a Layer 0 void for that
# sender's signals (lines 478, 1202).
# ===========================================================================

def test_sender_discount_recurrence_is_ap_g(sv):
    """
    Implementation-decision test (D6: sender-discount threshold 3,
    "provisionally mirroring Rule 7"). The third discount opens
    SENDER_DISCOUNT_RECURRENCE, and a gate over that sender's constraint
    reports an AP-G void.

    Enter:   sv   fixture
    Exit:    passes if AP-G is absent after two discounts, present after
             three, and reported by the gate
    """
    # PLAYERS IN THIS SCENE
    #   result   GateResult for a decision over boisjoly's signal

    sv.record_signal_outcome("boisjoly", True, "observer")
    for label in ("difficult", "not a team player"):
        sv.record_credibility_discount("boisjoly", "manager", label)
    assert E.SENDER_DISCOUNT_RECURRENCE not in conditions(sv)
    sv.record_credibility_discount("boisjoly", "manager", "emotional")
    assert E.SENDER_DISCOUNT_RECURRENCE in conditions(sv)
    # --- The Layer 0 consequence -------------------------------------------
    to_review(sv, "c", by="boisjoly")
    decision(sv, "d", ["c"])
    result = sv.request_execution("d", "director")
    assert result.architecture_void
    assert any(f.startswith("AP-G") for f in result.failures)


# ===========================================================================
# SCENE 12 — WHAT "STABLE OR IMPROVING" MEANS HERE
# Proves (implementation decision D7): the accuracy rule as coded.
# ===========================================================================

@pytest.mark.parametrize("record,expected", [
    ([], False),                         # no track record: no claim of accuracy
    ([True], True),                      # one correct outcome counts
    ([False], False),
    ([False, True], True),               # improving
    ([True, False], False),              # declining
    ([True, False, True, False], True),  # stable at 0.5 -> 0.5, overall 0.5
    ([True, True, False, True], False),  # 1.0 -> 0.5 is declining, despite 0.75 overall
    ([False, False, False, False], False),  # stable but below one half overall
])
def test_accuracy_rule(sv, record, expected):
    """
    Implementation-decision test (D7). The spec says "stable or improving
    accuracy rate" without a formula; the code compares the later half of
    the outcomes with the earlier half and also requires overall accuracy
    of at least one half.

    Enter:   sv         fixture
             record     outcomes recorded for agent "a", in order
             expected   what accuracy_stable_or_improving should return
    Exit:    passes if the rule returns `expected`
    """
    for correct in record:
        sv.record_signal_outcome("a", correct, "observer")
    assert sv.accuracy_stable_or_improving("a") is expected


# ===========================================================================
# SCENE 13 — NO WAIVER WHILE THE ALARM SOUNDS
# Proves: an escalated signal cannot be closed by any closure type
# (Rule 7 "structural review is mandatory and automatic — not a judgment
# call"; code's fifth blocked transition), and nothing changes.
# ===========================================================================

def test_escalated_signal_cannot_close(sv):
    """
    Closure attempts of every kind on an escalated signal are refused.

    Enter:   sv   fixture
    Exit:    passes if authority and role-switch attempts raise
             TransitionRefused, the state stays escalated, and the refusal
             is logged
    """
    to_review(sv, "c", by="eng", state=O.OFF_ENVELOPE)
    for closer in ("vp", "eng"):
        with pytest.raises(TransitionRefused):
            sv.attempt_closure("c", closer, CUST)
    assert sv.signals["c"].state == S.ESCALATED
    assert sv.signals["c"].closures == []
    assert "TRANSITION_REFUSED" in sv.audit.events()


# ===========================================================================
# SCENE 14 — RULE 8: A REVIEW MUST CHANGE THE MODEL
# Proves: a structural review cannot be resolved by a blank re-approval.
# ===========================================================================

def test_resolution_requires_model_update(sv):
    """
    resolve_review with an empty or whitespace model update is refused.

    Enter:   sv   fixture
    Exit:    passes if both attempts raise and the review stays unresolved
    """
    to_review(sv, "c", state=O.OFF_ENVELOPE)
    for update in ("", "   "):
        with pytest.raises(TransitionRefused):
            sv.resolve_review("R1", "board", update)
    assert not sv.reviews[0].resolved


# ===========================================================================
# SCENE 15 — RECOVERY
# Proves: line 886, "escalated -> under_review (Rule 8 model update
# documented)"; after recovery the signal can be closed again.
# ===========================================================================

def test_resolution_recovers_signals_to_under_review(sv):
    """
    Resolving the review with a model update returns the signal to review.

    Enter:   sv   fixture
    Exit:    passes if the signal is under_review, the update is stored and
             logged, and a closure then succeeds
    """
    # PLAYERS IN THIS SCENE
    #   review   the off-envelope review

    to_review(sv, "c", state=O.OFF_ENVELOPE)
    sv.resolve_review("R1", "board", "add cold-weather test to the envelope")
    review = sv.reviews[0]
    assert review.resolved and review.resolved_by == "board"
    assert sv.signals["c"].state == S.UNDER_REVIEW
    assert "STRUCTURAL_REVIEW_RESOLVED" in sv.audit.events()
    sv.attempt_closure("c", "vp", CUST)
    assert sv.signals["c"].state == S.CLOSED_AUTHORITY


# ===========================================================================
# SCENE 16 — TWO ALARMS, TWO ANSWERS
# Proves: a signal named by two open reviews stays escalated until both
# document their model updates.
# ===========================================================================

def test_signal_held_by_two_reviews_waits_for_both(sv):
    """
    A recurrence member classified off-envelope needs both reviews resolved.

    Enter:   sv   fixture
    Exit:    passes if resolving one review leaves the signal escalated and
             resolving the second returns it to under_review
    """
    # PLAYERS IN THIS SCENE
    #   ids   review ids, in the order they were opened

    for n in (1, 2, 3):
        sv.register_signal(f"m{n}", SignalType.ANOMALY, "erosion", "eng", TECH, PROCESS,
                           recurrence_group="g", steward="s", successor="u")
    sv.classify("m3", O.OFF_ENVELOPE, "eng")
    sv.open_review("m3", "eng")
    ids = [r.review_id for r in sv.reviews]
    assert len(ids) == 2
    sv.resolve_review(ids[0], "board", "redesign the joint")
    assert sv.signals["m3"].state == S.ESCALATED
    sv.resolve_review(ids[1], "board", "extend the validated envelope")
    assert sv.signals["m3"].state == S.UNDER_REVIEW


# ===========================================================================
# SCENE 17 — NO RECOVERY THROUGH THE SIDE DOOR
# Proves: line 886, escalated -> under_review is the
# recovery transition "(Rule 8 model update documented)". No other call may
# take it, and it must not reset what the stability rule measures from.
# ===========================================================================

@pytest.mark.parametrize("call", ["open_review", "reenter_suppressed"])
def test_recovery_only_through_model_update(sv, call):
    """
    Any call other than resolve_review that would move an escalated signal
    to under_review is refused and logs no recovery transition.

    Enter:   sv     fixture
             call   the Supervisor method tried on the escalated signal
    Exit:    passes if the call raises TransitionRefused and no
             escalated -> under_review transition was logged
    """
    # PLAYERS IN THIS SCENE
    #   method   the bound Supervisor method named by `call`
    #   moves    (from, to) pairs logged for the signal

    to_review(sv, "c", state=O.OFF_ENVELOPE)
    method = getattr(sv, call)
    with pytest.raises(TransitionRefused):
        if call == "open_review":
            method("c", "manager")
        else:
            method("c", "manager", "let us look again")
    moves = [(e.payload["from"], e.payload["to"]) for e in sv.audit.entries()
             if e.event == "TRANSITION" and e.payload.get("signal") == "c"]
    assert ("escalated", "under_review") not in moves

# EXEUNT — end of file.

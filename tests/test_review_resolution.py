"""
THE REVIEW ROOM
A Play in Eleven Scenes
=======================

PROLOGUE
--------
Tests for Supervisor.resolve_review() as revised in October 2026: a
structural review is resolved by what its trigger requires, never by those
closest to the decision. From the CCL-F v0.2 draft:

  Layer 2, Escalation Conditions: "The review is resolved by what its
    trigger requires — evidence-based reclassification to nominal or
    elevated uncertainty for off-envelope, independent steward review for
    containment, a documented Rule 8 update for a threshold count or
    relabeling after refusal, and for every other condition either that
    update or an independent finding that no model element requires change
    — by an agent who neither accepted the decision nor requested its
    execution, and who meets the independence conditions under Overrides."
  Rule 8, "What counts as an update": "An update changes at least one
    registered element of the coordination model ... and names the element
    it changes." Scope: "The update is made at the level where the
    recurring instances are generated". Effect: "If the same recurrence
    group recurs after the update, the update is recorded as ineffective
    and a new structural review opens. The earlier resolution stays in the
    record, beside the recurrence that contradicted it."

Off-envelope and containment share one escalation condition
(OFF_ENVELOPE_OR_CONTAINMENT, one bullet in the spec's list). The review
records which state opened it in StructuralReview.trigger, and that is how
the two are told apart.

THE PLAYBILL
    Prelude   sv (fixture), held() (helper)
    Scene 1   test_off_envelope_and_containment_open_separate_reviews
    Scene 2   test_off_envelope_needs_evidence_based_reclassification (parametrized, 2 runs)
    Scene 3   test_off_envelope_reclassification_must_cite_ees_for_the_reclassifier
    Scene 4   test_off_envelope_resolved_by_reclassification_releases_the_signal
    Scene 5   test_containment_resolved_by_independent_steward_review
    Scene 6   test_containment_resolver_must_be_independent       (parametrized, 3 runs)
    Scene 7   test_rule8_update_must_name_changed_elements
    Scene 8   test_recurrence_update_must_name_the_level
    Scene 9   test_recurrence_after_update_is_recorded_ineffective
    Scene 10  test_reporting_line_conflict_refuses_a_rule8_resolution
    Scene 11  test_resolver_needs_obligation_capacity
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       fixtures, parametrize, raises.
# cclf         AgentKind, CommitmentState, EscalationCondition,
#              OperationalState, SignalType, Supervisor, TransitionRefused.
# stagehands   shared set-up helpers (see tests/stagehands.py).
# ===========================================================================

import pytest

from cclf import (
    AgentKind, CommitmentState, EscalationCondition, OperationalState, SignalType,
    Supervisor, TransitionRefused,
)
from stagehands import UPDATE, UPDATE_AT_LEVEL, add_ees, decision, entries, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# S, E, O — short aliases used in every verdict.
S = CommitmentState
E = EscalationCondition
O = OperationalState

# BOARD — an independent reviewer: never accepts or requests anything here.
BOARD = "review-board"


# ===========================================================================
# PRELUDE — the fixture and a helper
# ===========================================================================

@pytest.fixture
def sv():
    """
    A new, empty Supervisor with default settings.

    Enter:   (nothing)
    Exit:    Supervisor()
    """
    return Supervisor()


def held(sv, signal_id, state):
    """
    Put a constraint under review classified `state` (off-envelope or
    containment), under an accepted irreversible decision "d" requested by
    "launch-manager"; return the review the classification opened.

    Enter:   sv, signal_id, state
    Exit:    the StructuralReview
    """
    to_review(sv, signal_id, state=state)
    decision(sv, "d", [signal_id])
    sv.request_execution("d", "launch-manager")
    [review] = [r for r in sv.reviews if r.trigger == state]
    return review


# ===========================================================================
# SCENE 1 — TWO TRIGGERS, TWO REVIEWS
# Proves: one escalation condition, two triggers: a signal classified
# off-envelope and then containment has two reviews, told apart by trigger.
# ===========================================================================

def test_off_envelope_and_containment_open_separate_reviews(sv):
    """
    Setting the stage: "c" classified off-envelope, then containment.
    The verdict: two OFF_ENVELOPE_OR_CONTAINMENT reviews, one per trigger;
    re-confirming off-envelope joins the first rather than opening a third.

    Enter:   sv   fixture
    Exit:    passes if the triggers are [off_envelope, containment]
    """
    to_review(sv, "c", state=O.OFF_ENVELOPE)
    sv.classify("c", O.CONTAINMENT, "eng")
    sv.classify("c", O.OFF_ENVELOPE, "eng")
    assert [(r.condition, r.trigger) for r in sv.reviews] == [
        (E.OFF_ENVELOPE_OR_CONTAINMENT, O.OFF_ENVELOPE),
        (E.OFF_ENVELOPE_OR_CONTAINMENT, O.CONTAINMENT)]
    assert all(r.suspendable for r in sv.reviews)


# ===========================================================================
# SCENE 2 — AN UPDATE IS NOT A MEASUREMENT
# Proves: an off-envelope review is not resolved by a Rule 8 update, nor by
# reclassifying to experimental or containment: the spec resolves it "only
# by reclassification to nominal or elevated uncertainty, supported by an
# External Evidence Source that the condition lies within validated
# parameters" (Overrides).
# ===========================================================================

@pytest.mark.parametrize("state", [O.EXPERIMENTAL, O.CONTAINMENT], ids=lambda s: s.name)
def test_off_envelope_needs_evidence_based_reclassification(sv, state):
    """
    Setting the stage: an off-envelope review holding decision "d".
    The action: resolve with a full Rule 8 update; then reclassify to
    `state` (with evidence) and try again. The verdict: both refused,
    the review open, the signal escalated.

    Enter:   sv      fixture
             state   EXPERIMENTAL or CONTAINMENT: neither lies within
                     validated parameters
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   review   the off-envelope review

    review = held(sv, "c", O.OFF_ENVELOPE)
    with pytest.raises(TransitionRefused, match="reclassified out of off-envelope"):
        sv.resolve_review(review.review_id, BOARD, finding="looks fine", **UPDATE)
    add_ees(sv, "rig-run")
    sv.classify("c", state, "test-engineer", ["rig-run"])
    with pytest.raises(TransitionRefused, match="to nominal or elevated uncertainty"):
        sv.resolve_review(review.review_id, BOARD, finding="now " + state.value)
    assert not review.resolved
    assert sv.signals["c"].state == S.ESCALATED


# ===========================================================================
# SCENE 3 — WHOSE EVIDENCE?
# Proves: the reclassification must cite an External Evidence Source for
# the RECLASSIFYING agent's claim; their own measurement does not count,
# nor does a reclassification without evidence (which classify() records as
# elevated uncertainty, not nominal).
# ===========================================================================

def test_off_envelope_reclassification_must_cite_ees_for_the_reclassifier(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if a reclassification on the reclassifier's own
             evidence, and one with no evidence, are both refused
    """
    # PLAYERS IN THIS SCENE
    #   review   the off-envelope review

    review = held(sv, "c", O.OFF_ENVELOPE)
    add_ees(sv, "own-run", produced_by="test-engineer")
    sv.classify("c", O.ELEVATED_UNCERTAINTY, "test-engineer", ["own-run"])
    with pytest.raises(TransitionRefused, match="cites no External Evidence Source"):
        sv.resolve_review(review.review_id, BOARD, finding="tested")
    sv.classify("c", O.NOMINAL, "test-engineer")                  # refused nominal
    with pytest.raises(TransitionRefused, match="cites no External Evidence Source"):
        sv.resolve_review(review.review_id, BOARD, finding="tested")
    assert not review.resolved


# ===========================================================================
# SCENE 4 — THE MEASUREMENT IS TAKEN
# Proves: a reclassification out of off-envelope citing an independent EES,
# documented in a written finding by an independent agent, resolves the
# review and releases the signal (escalated -> under_review).
# ===========================================================================

def test_off_envelope_resolved_by_reclassification_releases_the_signal(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the review resolves with its finding, the signal
             returns to under_review, and a finding is required
    """
    # PLAYERS IN THIS SCENE
    #   review   the off-envelope review
    #   logged   its STRUCTURAL_REVIEW_RESOLVED entry

    review = held(sv, "c", O.OFF_ENVELOPE)
    add_ees(sv, "cold-test")
    sv.classify("c", O.ELEVATED_UNCERTAINTY, "test-engineer", ["cold-test"])
    with pytest.raises(TransitionRefused, match="written finding"):
        sv.resolve_review(review.review_id, BOARD)
    sv.resolve_review(review.review_id, BOARD, finding="tested at the condition")
    assert review.resolved and review.finding == "tested at the condition"
    assert sv.signals["c"].state == S.UNDER_REVIEW
    [logged] = entries(sv, "STRUCTURAL_REVIEW_RESOLVED")
    assert logged.payload["resolved_by_kind"] == "evidence-based reclassification"


# ===========================================================================
# SCENE 5 — THE STEWARD LOOKS AGAIN
# Proves: a containment review is resolved by an independent steward
# review: a written finding, recorded with the reviewing steward. No
# reclassification is required.
# ===========================================================================

def test_containment_resolved_by_independent_steward_review(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if a blank finding is refused, and a finding by BOARD
             resolves it with BOARD as reviewing_steward while the signal
             stays classified containment
    """
    # PLAYERS IN THIS SCENE
    #   review   the containment review

    review = held(sv, "c", O.CONTAINMENT)
    with pytest.raises(TransitionRefused, match="written finding"):
        sv.resolve_review(review.review_id, BOARD, finding="  ")
    sv.resolve_review(review.review_id, BOARD,
                      finding="isolation verified; containment boundary holds")
    assert review.resolved and review.reviewing_steward == BOARD
    assert sv.signals["c"].operational_state == O.CONTAINMENT
    assert entries(sv, "STRUCTURAL_REVIEW_RESOLVED")[0].payload["reviewing_steward"] == BOARD


# ===========================================================================
# SCENE 6 — NOT THE PEOPLE WHO WANT IT TO GO
# Proves: the independent steward is not the acceptor, not a requester, and
# not in the acceptor's reporting line.
# ===========================================================================

@pytest.mark.parametrize("who", ["director", "launch-manager", "deputy"])
def test_containment_resolver_must_be_independent(sv, who):
    """
    Enter:   sv    fixture
             who   the acceptor, the requester, or the acceptor's report
    Exit:    passes if the resolution is refused, logged, the review stays
             open, and the message names the external-reviewer remedy
    """
    # PLAYERS IN THIS SCENE
    #   review   the containment review

    review = held(sv, "c", O.CONTAINMENT)
    sv.register_reporting_line("deputy", "director", by="hr")
    with pytest.raises(TransitionRefused, match="external reviewer"):
        sv.resolve_review(review.review_id, who, finding="it is fine")
    assert not review.resolved
    assert entries(sv, "REVIEW_RESOLUTION_REFUSED")


# ===========================================================================
# SCENE 7 — WHAT COUNTS AS AN UPDATE
# Proves: a Rule 8 review needs the update text AND the registered elements
# it changes; "a documented re-approval of existing practice, however
# thorough, is not an update".
# ===========================================================================

def test_rule8_update_must_name_changed_elements(sv):
    """
    Setting the stage: a role-switch review (a Rule 8 condition).
    The verdict: refused without elements, or with only blank ones;
    resolved with UPDATE, which records the elements.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   review   the role-switch review

    to_review(sv, "c", by="lund")
    sv.attempt_closure("c", "lund", "customer")
    [review] = sv.open_reviews()
    assert review.condition == E.ROLE_SWITCH_ON_CONSTRAINT
    for elements in ([], ["  "]):
        with pytest.raises(TransitionRefused, match="name the registered elements"):
            sv.resolve_review(review.review_id, BOARD, "a thorough re-approval",
                              elements_changed=elements)
    sv.resolve_review(review.review_id, BOARD, **UPDATE)
    assert review.elements_changed == tuple(UPDATE["elements_changed"])


# ===========================================================================
# SCENE 8 — AT THE LEVEL WHERE IT RECURS
# Proves: Rule 8, Scope: a recurrence review's update names "the level
# where the recurring instances are generated".
# ===========================================================================

def test_recurrence_update_must_name_the_level(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the update without a level is refused and with
             UPDATE_AT_LEVEL is accepted, recording the level
    """
    # PLAYERS IN THIS SCENE
    #   n        member number
    #   review   the recurrence review

    for n in (1, 2, 3):
        to_review(sv, f"m{n}", recurrence_group="g")
    [review] = sv.open_reviews()
    with pytest.raises(TransitionRefused, match="Scope"):
        sv.resolve_review(review.review_id, BOARD, **UPDATE)
    sv.resolve_review(review.review_id, BOARD, **UPDATE_AT_LEVEL)
    assert review.level == UPDATE_AT_LEVEL["level"]


# ===========================================================================
# SCENE 9 — THE UPDATE DID NOT HOLD
# Proves: Rule 8, Effect: a new member of a group after its review was
# resolved logs UPDATE_INEFFECTIVE naming that review and opens a new
# structural review for the group; the earlier resolution stays.
# ===========================================================================

def test_recurrence_after_update_is_recorded_ineffective(sv):
    """
    Setting the stage: group "g" crosses its threshold; the review is
    resolved at the right level. The action: a fourth member registers.
    The verdict: UPDATE_INEFFECTIVE names R1; a new open review covers all
    four members; R1 stays resolved; the gate again reports the group
    unreviewed.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   n            member number
    #   first        the first recurrence review
    #   ineffective  the UPDATE_INEFFECTIVE entries
    #   second       the new review

    for n in (1, 2, 3):
        to_review(sv, f"m{n}", recurrence_group="g")
    [first] = sv.open_reviews()
    sv.resolve_review(first.review_id, BOARD, **UPDATE_AT_LEVEL)
    assert "g" in sv.reviewed_groups
    to_review(sv, "m4", recurrence_group="g")
    ineffective = entries(sv, "UPDATE_INEFFECTIVE")
    assert len(ineffective) == 1 and ineffective[0].payload["review"] == first.review_id
    [second] = sv.open_reviews()
    assert second.scope == "group:g" and second.signal_ids == ["m1", "m2", "m3", "m4"]
    assert first.resolved and "g" not in sv.reviewed_groups
    assert sv.signals["m4"].state == S.ESCALATED
    decision(sv, "d", ["m4"])
    assert "recurrence groups not reviewed: ['g']" in sv.request_execution("d", "x").failures


# ===========================================================================
# SCENE 10 — THE ACCEPTOR'S DEPUTY
# Proves: a Rule 8 review holding an irreversible decision cannot be
# resolved by an agent who reports to the acceptor, directly or through
# others ("where reporting lines are registered, sits outside the
# accepting agent's").
# ===========================================================================

def test_reporting_line_conflict_refuses_a_rule8_resolution(sv):
    """
    Setting the stage: "c" role-switch closed under decision "d" accepted
    by "director"; "analyst" reports to "deputy", who reports to
    "director". The verdict: the analyst's resolution is refused (logged);
    BOARD's is accepted.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   review   the role-switch review

    to_review(sv, "c", by="lund")
    decision(sv, "d", ["c"])
    sv.attempt_closure("c", "lund", "customer")
    [review] = sv.open_reviews()
    sv.register_reporting_line("deputy", "director", by="hr")
    sv.register_reporting_line("analyst", "deputy", by="hr")
    assert sv.in_reporting_line("analyst", "director")
    with pytest.raises(TransitionRefused, match="reports to director"):
        sv.resolve_review(review.review_id, "analyst", **UPDATE)
    assert [e.event for e in entries(sv, "REPORTING_LINE_REGISTERED")] == \
        ["REPORTING_LINE_REGISTERED"] * 2
    sv.resolve_review(review.review_id, BOARD, **UPDATE)
    assert review.resolved


# ===========================================================================
# SCENE 11 — A MONITOR CANNOT SIGN OFF
# Proves: Agent Admissibility: resolving a review is a stewardship act and
# needs obligation capacity, whether or not a decision is involved.
# ===========================================================================

def test_resolver_needs_obligation_capacity(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if an AUTOMATION agent is refused and a PERSON resolves
    """
    # PLAYERS IN THIS SCENE
    #   review   the credibility-discounting review

    sv.record_credibility_discount("kim", "manager", "difficult")
    [review] = sv.open_reviews()
    sv.register_agent("review-bot", AgentKind.AUTOMATION, by="ops")
    sv.register_agent(BOARD, AgentKind.UNIT, by="ops")
    with pytest.raises(TransitionRefused, match="obligation capacity"):
        sv.resolve_review(review.review_id, "review-bot", **UPDATE)
    sv.resolve_review(review.review_id, BOARD, **UPDATE)
    assert review.resolved and review.resolved_by == BOARD


# EXEUNT — end of file.

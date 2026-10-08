"""
THE SECOND READING
A Play in Twenty-Five Scenes
============================

PROLOGUE
--------
An October 2026 review of the runtime found ways round its own rules: a
lower-class decision linked to a blocked one after registration, a
re-acceptance that lowered the applied class, a former acceptor overriding
after a subordinate re-accepted, a review resolved by the future acceptor
before the decision existed, and more. Each attack was written as a
throwaway script (review/a01-a12); each is kept here, permanently, as a
scene whose verdict is that the attack is refused. The second half of the
play covers the spec changes made in the same pass:

  Overrides, "Structural review holds irreversible execution": "A review
    opened by an off-envelope classification is resolved only by
    reclassification to nominal or elevated uncertainty, supported by an
    External Evidence Source that the condition lies within validated
    parameters ... A review opened by a count crossing its threshold —
    recurrence (Rule 7), authority closures, AP-G — or by relabeling after
    refusal is resolved only by a Rule 8 update. A review opened by any
    other condition is resolved by that update, or by a documented finding
    from the independent reviewer, with rationale, that the event was
    handled on its own record and no model element requires change."
  Classification stabilized: "neither does a reclassification that
    resolves an off-envelope or containment review under the standard its
    trigger requires".
  Commitment State Machine: "A loop exited to an external process
    (whistleblower, legal) keeps that exit state, because it continues
    elsewhere, and carries the authorization record as an annotation."
  Architecture Precondition met: "each of AP.2-AP.8 either passes its
    registered check or is reported in the gate record as unverified".
  At least one External Evidence Source for the principal risk claim:
    "Whether the cited evidence bears on the claim is attested by an agent
    other than the acceptor who meets the independence conditions under
    Overrides, and the attestation stays in the record."

THE PLAYBILL
    Prelude   sv (fixture), off_env(), ej(), relabel_reviews()
    ACT I — THE ATTACKS, REFUSED
    Scene 1   test_linking_a_lower_class_decision_to_a_blocked_one_escalates        (a01)
    Scene 2   test_reacceptance_that_lowers_the_applied_class_escalates           (a02)
    Scene 3   test_former_acceptor_cannot_override_after_a_subordinate_reaccepts  (a03)
    Scene 4   test_former_acceptor_cannot_give_an_off_scene_justification
    Scene 5   test_resolution_before_acceptance_counts_unresolved_at_the_gate     (a04)
    Scene 6   test_every_entry_into_review_starts_the_stability_clock   (a06, 2 runs)
    Scene 7   test_outcomes_the_parties_control_do_not_count            (a07, 3 runs)
    Scene 8   test_second_emergency_on_one_loop_suspends_the_post_event_review   (a05)
    Scene 9   test_post_event_review_holds_a_later_decision_on_the_same_loop
    Scene 10  test_third_emergency_is_refused_whatever_the_threshold    (a05, 2 runs)
    Scene 11  test_emergency_count_restarts_after_its_rule7_review      (a05)
    Scene 12  test_off_envelope_turned_containment_admits_an_emergency  (a11)
    Scene 13  test_acceptor_capacity_is_rechecked_at_the_gate           (a10)
    Scene 14  test_settings_cannot_change_after_construction            (a12)
    Scene 15  test_bypass_attempts_are_refused                          (a09, 17 runs)
    ACT II — THE SPEC CHANGES
    Scene 16  test_count_and_relabel_reviews_need_a_rule8_update
    Scene 17  test_other_reviews_resolve_by_an_independent_no_change_finding
    Scene 18  test_resolving_reclassification_does_not_destabilize
    Scene 19  test_external_exit_keeps_its_state_and_is_annotated       (2 runs)
    Scene 20  test_gate_record_lists_unverified_preconditions
    Scene 21  test_attestation_refused_without_independence             (6 runs)
    Scene 22  test_new_acceptance_voids_the_attestation
    Scene 23  test_gate_rechecks_the_attester
    Scene 24  test_on_scene_acceptor_becomes_steward
    Scene 25  test_demo_narrates_annotation_and_attestation
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# dataclasses  FrozenInstanceError, raised on assignment to a frozen field.
# pytest       fixtures, parametrize, raises.
# cclf         the Supervisor, its settings and the vocabulary types.
# stagehands   shared set-up helpers (see tests/stagehands.py).
# run_demo     describe(), the demo's one-line narration of an audit entry.
# ===========================================================================

import dataclasses

import pytest

from cclf import (
    AgentKind, Architecture, CommitmentState, EmergencyConsequence, EmergencyJustification,
    EscalationCondition, EvidenceKind, ExecutionClass, ExitType, LegalSubtype,
    OperationalState, Settings, SignalType, Supervisor, TransitionRefused,
)
from stagehands import (
    ATTESTER, PROCESS, RULE3, TECH, UPDATE, UPDATE_AT_LEVEL, add_ees, attest, decision,
    entries, to_review,
)
from run_demo import describe


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# S, E, O, X — short aliases used in every verdict.
S = CommitmentState
E = EscalationCondition
O = OperationalState
X = ExecutionClass

# BOARD — an independent reviewer: never accepts or requests anything here.
BOARD = "review-board"

# GIVER — gives Emergency Justifications; never accepts a decision.
GIVER = "flight-director"

# MODE — the failure mode of every emergency scene's loops.
MODE = "life-support"

# EXIT_OBLIGATIONS — what the two external exits must record (Layer 2).
EXIT_OBLIGATIONS = {
    ExitType.WHISTLEBLOWER: {"external_pathway": "Rogers Commission testimony",
                             "suppression_ref": "audit seq 12"},
    ExitType.LEGAL: {"open_loop_state": "under review when the order arrived",
                     "legal_subtype": LegalSubtype.REGULATORY_INTERVENTION},
}


# ===========================================================================
# PRELUDE — the fixture and helpers
# ===========================================================================

@pytest.fixture
def sv():
    """
    A new, empty Supervisor with default settings.

    Enter:   (nothing)
    Exit:    Supervisor()
    """
    return Supervisor()


def off_env(sv, signal_id, mode=MODE, **kwargs):
    """
    A constraint classified off-envelope, then experimental on the best
    evidence ("proc"): ready for an Emergency Justification (element 4).

    Enter:   sv, signal_id   where and which signal
             mode            its failure mode (emergency counting)
             **kwargs        passed on to to_review (successor, ...)
    Exit:    the Signal
    """
    if "proc" not in sv.evidence:
        add_ees(sv, "proc")
    sig = to_review(sv, signal_id, state=O.OFF_ENVELOPE, failure_mode=mode, **kwargs)
    sv.classify(signal_id, O.EXPERIMENTAL, "engineer", ["proc"])
    return sig


def ej(on_scene=False, consequence=EmergencyConsequence.LIFE_SAFETY_CATASTROPHIC):
    """
    An Emergency Justification with every element documented.

    Enter:   on_scene      element 5's proviso
             consequence   element 1
    Exit:    an EmergencyJustification
    """
    return EmergencyJustification(consequence, "crew lost before review completes",
                                  ("wait: loss of crew",), ("proc",), on_scene,
                                  rationale="survival")


def relabel_reviews(sv):
    """
    The ids of every relabeling-after-refusal review.

    Enter:   sv
    Exit:    a list of review ids
    """
    return [r.review_id for r in sv.reviews
            if r.condition == E.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK]


# ###########################################################################
# ACT I — THE ATTACKS, REFUSED
# ###########################################################################

# ===========================================================================
# SCENE 1 — THE SAME COMMITMENT UNDER A NEW NAME, LINKED LATER
# Proves: a decision registered at a lower class with no signals, then
# linked to a blocked decision's loop, is a relabeling after refusal
# (Execution Class Assignment), exactly as if it had been registered with
# the loop.
# ===========================================================================

def test_linking_a_lower_class_decision_to_a_blocked_one_escalates(sv):
    """
    Setting the stage: "launch" (irreversible) refused on an open
    constraint; "launch-b" registered elevated with a tested reversal path
    and no signals. The action: link the constraint to "launch-b". The
    verdict: a relabeling review opens and holds "launch-b".

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   result   launch-b's GateResult

    to_review(sv, "oring", failure_mode="joint")
    decision(sv, "launch", ["oring"])
    assert not sv.request_execution("launch", "director").permitted
    decision(sv, "launch-b", [], execution_class=X.ELEVATED)
    assert relabel_reviews(sv) == []
    sv.link_signal("launch-b", "oring", "director")
    assert len(relabel_reviews(sv)) == 1
    result = sv.request_execution("launch-b", "director")
    assert not result.permitted
    assert any(relabel_reviews(sv)[0] in f for f in result.failures)


# ===========================================================================
# SCENE 2 — THE CLASS DROPS WHEN SOMEONE ELSE ACCEPTS
# Proves: re-acceptance that lowers the applied class after a block (here
# because the reversal-path evidence counts once its producer no longer
# accepts) is a relabeling and opens the review.
# ===========================================================================

def test_reacceptance_that_lowers_the_applied_class_escalates(sv):
    """
    Setting the stage: "deploy" registered elevated, its reversal drill
    produced by "ops-lead", who accepts it: the drill is not independent,
    so the applied class is irreversible, and the request is refused.
    The action: "ops-peer" re-accepts; the applied class falls to elevated.
    The verdict: a relabeling review opens and the request is refused.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    to_review(sv, "oring", failure_mode="joint")
    sv.add_evidence("rb-test", "rollback drill", "drill", EvidenceKind.DIRECT_MEASUREMENT,
                    "ops-lead", "clerk")
    sv.register_decision("deploy", "deploy", X.ELEVATED, ["oring"], "planner",
                         reversal_path="rollback", reversal_evidence_ids=["rb-test"])
    sv.accept_decision("deploy", "ops-lead", "ok")
    assert sv.effective_class("deploy") == X.IRREVERSIBLE
    assert not sv.request_execution("deploy", "ops-lead").permitted
    sv.accept_decision("deploy", "ops-peer", "ok")
    assert sv.effective_class("deploy") == X.ELEVATED
    assert len(relabel_reviews(sv)) == 1
    assert not sv.request_execution("deploy", "ops-lead").permitted


# ===========================================================================
# SCENE 3 — THE ACCEPTOR STEPS BACK, THEN OVERRIDES
# Proves: an agent who EVER accepted a decision may not override its gate,
# even after a subordinate re-accepts in their place; the acceptor history
# is kept.
# ===========================================================================

def test_former_acceptor_cannot_override_after_a_subordinate_reaccepts(sv):
    """
    Setting the stage: "mason" accepts "launch" over an open constraint;
    "lund" reports to mason. The action: lund re-accepts, mason overrides.
    The verdict: refused; the decision remembers both acceptors.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   result   mason's second override attempt

    to_review(sv, "oring", failure_mode="joint")
    decision(sv, "launch", ["oring"], by="mason")
    sv.register_reporting_line("lund", "mason", "hr")
    add_ees(sv, "risk2")
    sv.accept_decision("launch", "lund", "I accept", evidence_ids=["risk2"], risk_claim="safe",
                       **RULE3)
    result = sv.request_execution("launch", "mason", override_rationale="schedule")
    assert not result.permitted and not result.overridden
    assert any("mason accepted this decision" in f for f in result.failures)
    assert sv.decisions["launch"].accepted_by == "lund"
    assert sv.decisions["launch"].acceptors == ("mason", "lund")
    assert sv.signals["oring"].state == S.UNDER_REVIEW


# ===========================================================================
# SCENE 4 — THE SAME, UNDER AN EMERGENCY
# Proves: element 5's separate authorization also counts every acceptor
# ever: a former acceptor, off scene, cannot give the justification.
# ===========================================================================

def test_former_acceptor_cannot_give_an_off_scene_justification(sv):
    """
    Setting the stage: off-envelope "tank", experimental; "cap" accepts
    "lifeboat", then "fo" (cap's report) re-accepts. The action: cap gives
    an off-scene justification. The verdict: refused under element 5.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   result   cap's attempt

    off_env(sv, "tank")
    decision(sv, "lifeboat", ["tank"], by="cap")
    sv.register_reporting_line("fo", "cap", "hr")
    sv.accept_decision("lifeboat", "fo", "I accept", evidence_ids=["risk-check-lifeboat"],
                       risk_claim="safe", **RULE3)
    result = sv.request_execution("lifeboat", "cap", emergency=ej())
    assert not result.permitted
    assert any("element 5: cap accepted this decision" in f for f in result.failures)


# ===========================================================================
# SCENE 5 — RESOLVED BY THE FUTURE ACCEPTOR
# Proves: independence of a review's resolution is re-checked at the gate
# against every decision it touches, so a resolution given before its
# resolver accepted counts as unresolved, and the gate says so. An
# independent re-resolution releases it and keeps the first in the record.
# ===========================================================================

def test_resolution_before_acceptance_counts_unresolved_at_the_gate(sv):
    """
    Setting the stage: three anomalies in group "oring" open a recurrence
    review; "mulloy" resolves it with a Rule 8 update while no decision
    exists, then the loops are evidence-closed and mulloy accepts "launch".
    The verdict: refused, naming the review as not independent of launch.
    The action: BOARD re-resolves. The verdict: launch is permitted;
    RESOLUTION_SUPERSEDED is logged with mulloy's resolution in history.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   ids      the three anomaly ids
    #   review   the recurrence review
    #   result   each GateResult

    ids = ["erosion1", "erosion2", "erosion3"]
    for sid in ids:
        to_review(sv, sid, signal_type=SignalType.ANOMALY, recurrence_group="oring",
                  failure_mode="joint")
    [review] = [r for r in sv.reviews if r.scope == "group:oring"]
    sv.resolve_review(review.review_id, "mulloy", **UPDATE_AT_LEVEL)
    for sid in ids:
        add_ees(sv, f"ev-{sid}", [sid])
        sv.attempt_closure(sid, "closer", TECH, [f"ev-{sid}"])
    decision(sv, "launch", ids, by="mulloy")
    result = sv.request_execution("launch", "mulloy")
    assert not result.permitted
    assert any(f"{review.review_id} counts as unresolved: its resolution is not independent "
               "of launch" in f for f in result.failures)
    sv.resolve_review(review.review_id, BOARD, **UPDATE_AT_LEVEL)
    assert review.resolved_by == BOARD
    assert review.history[0]["resolved_by"] == "mulloy"
    assert entries(sv, "RESOLUTION_SUPERSEDED")[-1].payload["previous"] == "mulloy"
    result = sv.request_execution("launch", "mulloy")
    assert result.permitted, result.failures


# ===========================================================================
# SCENE 6 — EVERY DOOR INTO REVIEW STARTS THE CLOCK
# Proves: any entry into under_review sets first_review_opened_at when
# unset, so a lowering made after re-entry still destabilizes.
# ===========================================================================

@pytest.mark.parametrize("via_reenter", [False, True], ids=["open_review", "exit-reenter"])
def test_every_entry_into_review_starts_the_stability_clock(sv, via_reenter):
    """
    Setting the stage: "temp" classified experimental, then brought into
    review by open_review() or by exit (recoverable) and reenter(). The
    action: reclassify to nominal on independent evidence. The verdict: the
    review clock is set, the lowering is seen, the signal is not stable.

    Enter:   sv            fixture
             via_reenter   which door into review
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   sig   the signal

    sig = sv.register_signal("temp", SignalType.UNCERTAINTY, "o-ring temp", "eng", TECH,
                             PROCESS, steward="s", successor="t")
    sv.classify("temp", O.EXPERIMENTAL, "eng")
    if via_reenter:
        sv.exit("temp", ExitType.RECOVERABLE, "eng", "parked", resolution_condition="data")
        sv.reenter("temp", "eng", "back")
    else:
        sv.open_review("temp", "eng")
    assert sig.state == S.UNDER_REVIEW and sig.first_review_opened_at is not None
    add_ees(sv, "lab")
    sv.classify("temp", O.NOMINAL, "mgr", ["lab"])
    assert [(old, new) for _, old, new in sv._lowerings(sig)] == [(O.EXPERIMENTAL, O.NOMINAL)]
    assert not sv._classification_stable(sig)


# ===========================================================================
# SCENE 7 — A RECORD THE PARTIES WROTE THEMSELVES
# Proves: an outcome does not count toward a credibility record when the
# discounter produced its evidence (M2), when the target scored it, or
# when only the target's own evidence confirms it (L4).
# ===========================================================================

@pytest.mark.parametrize("case", ["discounter-evidence", "self-scored", "target-evidence"])
def test_outcomes_the_parties_control_do_not_count(sv, case):
    """
    Setting the stage, by case:
      discounter-evidence  an ally scores boisjoly wrong three times, on
                           readings mason produced
      self-scored          boisjoly scores himself right on a lab reading
      target-evidence      a neutral scorer, on boisjoly's own test
    The verdict: no outcome counts for mason's discount of boisjoly; in the
    first case the discount is unsupported and escalates.

    Enter:   sv, case
    Exit:    passes as described
    """
    if case == "discounter-evidence":
        for i in range(3):
            sv.add_evidence(f"m{i}", "my reading", "x", EvidenceKind.DIRECT_MEASUREMENT,
                            "mason", "mason")
            sv.record_signal_outcome("boisjoly", False, "ally", evidence_ids=[f"m{i}"])
    elif case == "self-scored":
        add_ees(sv, "lab")
        for _ in range(3):
            sv.record_signal_outcome("boisjoly", True, "boisjoly", evidence_ids=["lab"])
    else:
        sv.add_evidence("own", "my test", "x", EvidenceKind.DIRECT_MEASUREMENT, "boisjoly",
                        "boisjoly")
        sv.record_signal_outcome("boisjoly", True, "neutral", evidence_ids=["own"])
    assert sv._counted_outcomes("boisjoly", "mason") == []
    if case == "discounter-evidence":
        assert not sv.discount_supported_by_record("boisjoly", "mason")
        sv.record_credibility_discount("boisjoly", "mason", "difficult")
        assert any(r.condition == E.CREDIBILITY_DISCOUNTING for r in sv.reviews)


# ===========================================================================
# SCENE 8 — A SECOND BURN ON THE SAME LOOP
# Proves: the post-event review of a first justification is suspendable,
# so a second emergency on the same loop (Apollo 13 had several burns) may
# proceed, and it counts toward the failure mode's total.
# ===========================================================================

def test_second_emergency_on_one_loop_suspends_the_post_event_review(sv):
    """
    Setting the stage: "lifeboat" off-envelope then experimental. The
    action: EJ1 for "power-down", EJ2 for "pc2-burn", both on lifeboat.
    The verdict: both permitted; the first post-event review is
    suspendable; two justifications are counted on the mode.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   post   the post-event reviews

    off_env(sv, "lifeboat")
    decision(sv, "power-down", ["lifeboat"], by="crew")
    assert sv.request_execution("power-down", GIVER, emergency=ej()).permitted
    post = [r for r in sv.reviews if r.condition == E.EMERGENCY_POST_EVENT]
    assert len(post) == 1 and post[0].suspendable
    decision(sv, "pc2-burn", ["lifeboat"], by="crew")
    result = sv.request_execution("pc2-burn", GIVER, emergency=ej())
    assert result.permitted and result.emergency_id == "EJ2"
    assert [e[2] for e in sv.emergencies] == [(MODE,), (MODE,)]


# ===========================================================================
# SCENE 9 — THE POST-EVENT REVIEW HOLDS
# Proves: "The post-event review holds later irreversible decisions on the
# same loops as an off-envelope review does".
# ===========================================================================

def test_post_event_review_holds_a_later_decision_on_the_same_loop(sv):
    """
    Setting the stage: EJ1 given for "power-down" on "lifeboat". The
    action: a plain request for "later" on lifeboat, with an override.
    The verdict: refused, the post-event review among the holds.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   post     the post-event review
    #   result   the later request

    off_env(sv, "lifeboat")
    decision(sv, "power-down", ["lifeboat"], by="crew")
    sv.request_execution("power-down", GIVER, emergency=ej())
    [post] = [r for r in sv.reviews if r.condition == E.EMERGENCY_POST_EVENT]
    decision(sv, "later", ["lifeboat"], by="crew")
    result = sv.request_execution("later", "other", override_rationale="schedule")
    assert not result.permitted
    assert any(f.startswith("unresolved structural reviews") and post.review_id in f
               for f in result.failures)


# ===========================================================================
# SCENE 10 — THREE IS A PATTERN, WHATEVER THE DOMAIN SAYS
# Proves: the third justification on a failure mode since its last review
# is refused and opens an unsuspendable Rule 7 review, at a domain
# recurrence threshold of one or five alike (the count is fixed at three).
# ===========================================================================

@pytest.mark.parametrize("threshold", [1, 5])
def test_third_emergency_is_refused_whatever_the_threshold(threshold):
    """
    Setting the stage: Settings(recurrence_threshold=threshold), with a
    rationale for the raised one. The action: three justifications, each on
    a new loop of MODE. The verdict: two permitted, the third refused, and
    its review on "emergency:life-support" is not suspendable.

    Enter:   threshold   the domain's ordinary recurrence threshold
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   sv        the Supervisor
    #   results   permitted? for each of the three
    #   review    the emergency recurrence review

    sv = Supervisor(Settings(recurrence_threshold=threshold,
                             threshold_rationale="" if threshold < 3 else "rare events"))
    results = []
    for n in (1, 2, 3):
        off_env(sv, f"loop-{n}")
        decision(sv, f"d{n}", [f"loop-{n}"], by="crew")
        results.append(sv.request_execution(f"d{n}", GIVER, emergency=ej()).permitted)
    assert results == [True, True, False]
    [review] = [r for r in sv.reviews if r.scope == f"emergency:{MODE}"]
    assert review.condition == E.RECURRENCE_THRESHOLD and not review.suspendable


# ===========================================================================
# SCENE 11 — THE COUNT RESTARTS AFTER ITS REVIEW
# Proves: justifications are counted since the failure mode's last
# resolved Rule 7 review, so after that review's Rule 8 update the next
# emergency may proceed.
# ===========================================================================

def test_emergency_count_restarts_after_its_rule7_review(sv):
    """
    Setting the stage: two justifications given, a third refused (its
    review opens). The action: BOARD resolves that review with a Rule 8
    update; a fourth loop's emergency is requested. The verdict: permitted.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   review   the emergency recurrence review

    for n in (1, 2, 3):
        off_env(sv, f"loop-{n}")
        decision(sv, f"d{n}", [f"loop-{n}"], by="crew")
        sv.request_execution(f"d{n}", GIVER, emergency=ej())
    [review] = [r for r in sv.reviews if r.scope == f"emergency:{MODE}"]
    sv.resolve_review(review.review_id, BOARD, **UPDATE_AT_LEVEL)
    off_env(sv, "loop-4")
    decision(sv, "d4", ["loop-4"], by="crew")
    assert sv.request_execution("d4", GIVER, emergency=ej()).permitted


# ===========================================================================
# SCENE 12 — FROM OFF-ENVELOPE TO CONTAINMENT
# Proves: element 4 accepts an off-envelope condition "classified
# Experimental ... or containment, if it has since become one".
# ===========================================================================

def test_off_envelope_turned_containment_admits_an_emergency(sv):
    """
    Setting the stage: "tank" off-envelope, then containment (two reviews).
    The action: an emergency for "lifeboat" on tank. The verdict: permitted.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    add_ees(sv, "proc")
    to_review(sv, "tank", state=O.OFF_ENVELOPE, failure_mode="o2")
    sv.classify("tank", O.CONTAINMENT, "engineer", ["proc"])
    assert [r.trigger for r in sv.reviews] == [O.OFF_ENVELOPE, O.CONTAINMENT]
    decision(sv, "lifeboat", ["tank"], by="crew")
    result = sv.request_execution("lifeboat", GIVER, emergency=ej())
    assert result.permitted and result.emergency_id == "EJ1", result.failures


# ===========================================================================
# SCENE 13 — CAPACITY LOST AFTER ACCEPTANCE
# Proves: the acceptor's obligation capacity is re-checked at the gate.
# ===========================================================================

def test_acceptor_capacity_is_rechecked_at_the_gate(sv):
    """
    Setting the stage: an evidence-closed constraint; "pipeline-bot"
    (unregistered, so capable) accepts; then it is registered as
    automation. The verdict: the gate refuses, asking for a new acceptance.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult

    to_review(sv, "c")
    add_ees(sv, "ev-c", ["c"])
    sv.attempt_closure("c", "closer", TECH, ["ev-c"])
    decision(sv, "d", ["c"], by="pipeline-bot")
    sv.register_agent("pipeline-bot", AgentKind.AUTOMATION, "registrar")
    result = sv.request_execution("d", "pipeline-bot")
    assert not result.permitted
    assert any("pipeline-bot no longer has obligation capacity" in f for f in result.failures)


# ===========================================================================
# SCENE 14 — THE THRESHOLDS ARE SET ONCE
# Proves: Settings is frozen, so a threshold cannot be raised after
# construction, past its rationale check and SETTINGS log entry.
# ===========================================================================

def test_settings_cannot_change_after_construction(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if assignment raises FrozenInstanceError and the
             threshold is unchanged
    """
    with pytest.raises(dataclasses.FrozenInstanceError):
        sv.settings.recurrence_threshold = 10
    assert sv.settings.recurrence_threshold == 3
    with pytest.raises(ValueError):
        Settings(recurrence_threshold=10)


# ===========================================================================
# SCENE 15 — A BATCH OF WAYS ROUND
# Proves: each attempt in review/a09 is refused. Each case below builds
# its own stage and returns whether the attack got through (True would be
# a bypass), except "acceptor-on-scene", the one legitimate path, which
# must get through.
# ===========================================================================

def _void_then(use_ej):
    def case(sv):
        off_env(sv, "s", mode="fm", successor=None)            # AP.1b: no successor
        decision(sv, "d", ["s"])
        if use_ej:
            return sv.request_execution("d", "other", emergency=ej()).permitted
        return sv.request_execution("d", "other", override_rationale="x").permitted
    return case


def _authority_count_ej(sv):
    off_env(sv, "s", mode="fm")
    to_review(sv, "a1", failure_mode="fm")
    to_review(sv, "a2", failure_mode="fm")
    sv.attempt_closure("a1", "boss", TECH)
    sv.attempt_closure("a2", "boss", TECH)
    decision(sv, "d", ["s", "a1", "a2"])
    return sv.request_execution("d", "other", emergency=ej()).permitted


def _schedule_ej(sv):
    off_env(sv, "s", mode="fm")
    decision(sv, "d", ["s"])
    return sv.request_execution("d", "other", emergency=ej(consequence="schedule")).permitted


def _ej_by(giver, on_scene):
    def case(sv):
        off_env(sv, "s", mode="fm")
        decision(sv, "d", ["s"], by="cap")
        sv.register_reporting_line("fo", "cap", "hr")
        sv.register_agent("autopilot", AgentKind.AUTOMATION, "hr")
        return sv.request_execution("d", giver, emergency=ej(on_scene=on_scene)).permitted
    return case


def _override_by(agent):
    def case(sv):
        to_review(sv, "c")
        decision(sv, "d", ["c"], by="cap")
        sv.register_reporting_line("fo", "cap", "hr")
        sv.register_reporting_line("jr", "fo", "hr")
        sv.register_agent("bot", AgentKind.AUTOMATION, "hr")
        return sv.request_execution("d", agent, override_rationale="x").permitted
    return case


def _relabel_then(use_ej):
    def case(sv):
        off_env(sv, "s", mode="fm")
        decision(sv, "d", ["s"])
        sv.request_execution("d", "other")
        add_ees(sv, "rb")
        sv.reclassify_decision("d", X.ELEVATED, "planner", "relabel", "rollback", ["rb"])
        if use_ej:
            return sv.request_execution("d", "other", emergency=ej()).permitted
        return sv.request_execution("d", "other", override_rationale="x").permitted
    return case


def _suppressed_then(use_ej):
    def case(sv):
        off_env(sv, "s", mode="fm")
        to_review(sv, "q", failure_mode="fm")
        sv.suppress("q", "boss", "noise")
        decision(sv, "d", ["s", "q"])
        if use_ej:
            return sv.request_execution("d", "other", emergency=ej()).permitted
        return sv.request_execution("d", "other", override_rationale="x").permitted
    return case


def _off_env_resolved_by(who):
    def case(sv):
        to_review(sv, "s", state=O.OFF_ENVELOPE, failure_mode="fm")
        decision(sv, "d", ["s"], by="cap")
        sv.classify("s", O.ELEVATED_UNCERTAINTY, "engineer")      # no evidence
        try:
            sv.resolve_review(sv.reviews[0].review_id, who, finding="f")
            return True
        except TransitionRefused:
            return False
    return case


def _new_id_lower_class(sv):
    to_review(sv, "c", failure_mode="fm")
    decision(sv, "d", ["c"])
    sv.request_execution("d", "director")
    decision(sv, "d2", ["c"], execution_class=X.ELEVATED)
    return sv.request_execution("d2", "director").permitted


# BYPASSES — (case id, stage function, whether it must get through).
BYPASSES = [
    ("void/override", _void_then(False), False),
    ("void/EJ", _void_then(True), False),
    ("authority-count/EJ", _authority_count_ej, False),
    ("schedule/EJ", _schedule_ej, False),
    ("acceptor/EJ", _ej_by("cap", False), False),
    ("subordinate/EJ", _ej_by("fo", False), False),
    ("automation/EJ-on-scene", _ej_by("autopilot", True), False),
    ("acceptor-on-scene", _ej_by("cap", True), True),
    ("transitive-subordinate/override", _override_by("jr"), False),
    ("automation/override", _override_by("bot"), False),
    ("relabel/override", _relabel_then(False), False),
    ("relabel/EJ", _relabel_then(True), False),
    ("suppressed/override", _suppressed_then(False), False),
    ("suppressed/EJ", _suppressed_then(True), False),
    ("off-envelope-resolved-by-acceptor", _off_env_resolved_by("cap"), False),
    ("off-envelope-resolved-without-evidence", _off_env_resolved_by(BOARD), False),
    ("new-id-lower-class", _new_id_lower_class, False),
]


@pytest.mark.parametrize("stage, gets_through", [(f, ok) for _, f, ok in BYPASSES],
                         ids=[name for name, _, _ in BYPASSES])
def test_bypass_attempts_are_refused(sv, stage, gets_through):
    """
    Enter:   sv             fixture
             stage          builds the attack, returns True if it got through
             gets_through   the expected answer
    Exit:    passes if the attack's result is as expected
    """
    assert stage(sv) is gets_through


# ###########################################################################
# ACT II — THE SPEC CHANGES
# ###########################################################################

# ===========================================================================
# SCENE 16 — A COUNT NEEDS A MODEL CHANGE
# Proves: a recurrence review (a count) is resolved only by a Rule 8
# update; an independent no-change finding is refused.
# ===========================================================================

def test_count_and_relabel_reviews_need_a_rule8_update(sv):
    """
    Setting the stage: three anomalies in one group open a recurrence
    review. The action: resolve by a no-change finding, then by a Rule 8
    update naming the level. The verdict: refused, then resolved.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   review   the recurrence review

    for i in (1, 2, 3):
        to_review(sv, f"e{i}", signal_type=SignalType.ANOMALY, recurrence_group="g")
    [review] = [r for r in sv.reviews if r.condition == E.RECURRENCE_THRESHOLD]
    with pytest.raises(TransitionRefused, match="Rule 8"):
        sv.resolve_review(review.review_id, BOARD, finding="handled on its own record",
                          no_model_change=True)
    assert not review.resolved
    sv.resolve_review(review.review_id, BOARD, **UPDATE_AT_LEVEL)
    assert review.resolved and not review.no_model_change


# ===========================================================================
# SCENE 17 — HANDLED ON ITS OWN RECORD
# Proves: a review of the "every other condition" kind (here credibility
# discounting) is resolved by an independent finding, with rationale, that
# no model element requires change; without a rationale it is refused.
# ===========================================================================

def test_other_reviews_resolve_by_an_independent_no_change_finding(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the blank finding is refused and the reasoned one
             resolves the review, recorded as a no-change finding
    """
    # PLAYERS IN THIS SCENE
    #   review   the credibility-discounting review

    sv.record_credibility_discount("boisjoly", "mason", "difficult")
    [review] = [r for r in sv.reviews if r.condition == E.CREDIBILITY_DISCOUNTING]
    with pytest.raises(TransitionRefused, match="rationale"):
        sv.resolve_review(review.review_id, BOARD, no_model_change=True)
    sv.resolve_review(review.review_id, BOARD, finding="one remark, retracted",
                      no_model_change=True)
    assert review.resolved and review.no_model_change
    assert entries(sv, "STRUCTURAL_REVIEW_RESOLVED")[-1].payload["resolved_by_kind"] == \
        "independent finding: no model element requires change"


# ===========================================================================
# SCENE 18 — THE RESOLVING RECLASSIFICATION
# Proves: a reclassification from off-envelope to nominal that resolves
# the off-envelope review under its trigger's standard does not
# destabilize; before the review is resolved, it does.
# ===========================================================================

def test_resolving_reclassification_does_not_destabilize(sv):
    """
    Setting the stage: "c" off-envelope under decision "d". The action:
    reclassify nominal on independent evidence; check; resolve by BOARD;
    check. The verdict: unstable before the resolution, stable after.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   sig      the signal
    #   review   the off-envelope review

    sig = to_review(sv, "c", state=O.OFF_ENVELOPE)
    decision(sv, "d", ["c"])
    [review] = [r for r in sv.reviews if r.trigger == O.OFF_ENVELOPE]
    add_ees(sv, "rig-run")
    sv.classify("c", O.NOMINAL, "test-engineer", ["rig-run"])
    assert not sv._classification_stable(sig)
    sv.resolve_review(review.review_id, BOARD, finding="within validated parameters")
    assert sig.resolving_reclassifications
    assert sv._classification_stable(sig)


# ===========================================================================
# SCENE 19 — CONTINUED ELSEWHERE
# Proves: a constraint exited whistleblower or legal still fails the gate;
# at an override it keeps its exit state and is annotated, not latched.
# ===========================================================================

@pytest.mark.parametrize("exit_type", [ExitType.WHISTLEBLOWER, ExitType.LEGAL],
                         ids=lambda x: x.name)
def test_external_exit_keeps_its_state_and_is_annotated(sv, exit_type):
    """
    Setting the stage: "c" exited `exit_type` with its obligations; "d"
    depends on it. The action: request; then override by "other". The
    verdict: refused on the constraint test; then overridden, "c" still in
    its exit state, listed as annotated, OPEN_LOOP_ANNOTATED logged.

    Enter:   sv, exit_type
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   before        c's state after the exit
    #   result        each GateResult

    to_review(sv, "c")
    sv.exit("c", exit_type, "boisjoly", "goes outside", **EXIT_OBLIGATIONS[exit_type])
    before = sv.signals["c"].state
    decision(sv, "d", ["c"])
    result = sv.request_execution("d", "director")
    assert any("not evidence-closed" in f and "'c'" in f for f in result.failures)
    result = sv.request_execution("d", "other", override_rationale="carried knowingly")
    assert result.permitted and result.overridden
    assert sv.signals["c"].state == before
    assert result.annotated_signals == ["c"]
    assert entries(sv, "OPEN_LOOP_ANNOTATED")[-1].payload["signal"] == "c"


# ===========================================================================
# SCENE 20 — WHAT THE GATE COULD NOT CHECK
# Proves: the gate record lists AP.2-AP.8 sub-conditions with no check
# behind them, reporting only: a clean decision still executes.
# ===========================================================================

def test_gate_record_lists_unverified_preconditions(sv):
    """
    Setting the stage: an evidence-closed constraint "c"; first with no
    channels or reporters registered, then with both. The verdict: the
    list shrinks from six labels to the four never checkable; both pass.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   result   each GateResult

    to_review(sv, "c")
    add_ees(sv, "ev-c", ["c"])
    sv.attempt_closure("c", "closer", TECH, ["ev-c"])
    decision(sv, "d", ["c"])
    assert sv.unverified_preconditions("d") == ["AP.2", "AP.3", "AP.4", "AP.5", "AP.6", "AP.8"]
    sv.register_architecture(Architecture(channels_tested={"hotline": True},
                                          reporters={"c": {"boisjoly"}}), "registrar")
    result = sv.request_execution("d", "director")
    assert result.permitted, result.failures
    assert result.unverified == ["AP.3", "AP.4", "AP.5", "AP.8"]
    assert entries(sv, "EXECUTION_PERMITTED")[-1].payload["unverified"] == result.unverified


# ===========================================================================
# SCENE 21 — WHO MAY ATTEST
# Proves: attest_risk_evidence() refuses an acceptor, a requester, an agent
# in an acceptor's reporting line, an agent without obligation capacity, a
# blank rationale, and an attestation before an acceptance with a risk
# claim; each refusal is logged.
# ===========================================================================

@pytest.mark.parametrize("case", ["acceptor", "requester", "subordinate", "automation",
                                  "no-rationale", "not-accepted"])
def test_attestation_refused_without_independence(sv, case):
    """
    Setting the stage: "d" accepted by "director" with a risk claim
    (not yet attested), or registered only ("not-accepted").
    The action: the case's agent attests. The verdict: TransitionRefused,
    RISK_ATTESTATION_REFUSED logged, no attestation stored.

    Enter:   sv, case
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   agent, why   who attests and with what rationale

    to_review(sv, "c")
    decision(sv, "d", ["c"], accept=(case != "not-accepted"))
    if case != "not-accepted":
        add_ees(sv, "risk")
        sv.accept_decision("d", "director", "ok", evidence_ids=["risk"], risk_claim="safe",
                           **RULE3)
    sv.register_reporting_line("deputy", "director", "hr")
    sv.register_agent("bot", AgentKind.AUTOMATION, "hr")
    if case == "requester":
        sv.request_execution("d", "launch-manager")
    agent = {"acceptor": "director", "requester": "launch-manager", "subordinate": "deputy",
             "automation": "bot"}.get(case, ATTESTER)
    why = "" if case == "no-rationale" else "the evidence measures the claim"
    with pytest.raises(TransitionRefused):
        sv.attest_risk_evidence("d", agent, why)
    assert sv.decisions["d"].risk_attestation is None
    assert entries(sv, "RISK_ATTESTATION_REFUSED")


# ===========================================================================
# SCENE 22 — A NEW ACCEPTANCE, A NEW ATTESTATION
# Proves: a new acceptance voids the attestation (logged), and the gate
# then refuses until an attestation is given again.
# ===========================================================================

def test_new_acceptance_voids_the_attestation(sv):
    """
    Setting the stage: an evidence-closed constraint; "d" accepted and
    attested. The action: "director" re-accepts on other evidence. The
    verdict: attestation gone, voiding logged, gate refused; attesting
    again lets it pass.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult after re-acceptance

    to_review(sv, "c")
    add_ees(sv, "ev-c", ["c"])
    sv.attempt_closure("c", "closer", TECH, ["ev-c"])
    decision(sv, "d", ["c"])
    assert sv.decisions["d"].risk_attestation.by == ATTESTER
    add_ees(sv, "risk-2")
    sv.accept_decision("d", "director", "again", evidence_ids=["risk-2"], risk_claim="safe",
                       **RULE3)
    assert sv.decisions["d"].risk_attestation is None
    assert entries(sv, "DECISION_ACCEPTED")[-1].payload["attestation_voided"] == ATTESTER
    result = sv.request_execution("d", "director")
    assert not result.permitted
    assert any("not attested by an independent agent" in f for f in result.failures)
    attest(sv, "d")
    assert sv.request_execution("d", "director").permitted


# ===========================================================================
# SCENE 23 — THE ATTESTER JOINS THE ACCEPTOR'S TEAM
# Proves: the gate re-checks the attester's independence when it runs.
# ===========================================================================

def test_gate_rechecks_the_attester(sv):
    """
    Setting the stage: an evidence-closed constraint; "d" accepted and
    attested. The action: ATTESTER is registered as reporting to the
    director. The verdict: the gate refuses, naming the attestation.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult

    to_review(sv, "c")
    add_ees(sv, "ev-c", ["c"])
    sv.attempt_closure("c", "closer", TECH, ["ev-c"])
    decision(sv, "d", ["c"])
    sv.register_reporting_line(ATTESTER, "director", "hr")
    result = sv.request_execution("d", "director")
    assert not result.permitted
    assert any(f"attestation by {ATTESTER} is no longer independent" in f
               for f in result.failures)


# ===========================================================================
# SCENE 24 — THE CAPTAIN ON SCENE
# Proves: under the on-scene proviso the acceptor may give the
# justification alone, and becomes steward of the loop carried open.
# ===========================================================================

def test_on_scene_acceptor_becomes_steward(sv):
    """
    Setting the stage: off-envelope "engines", experimental; "captain"
    accepts "ditch". The action: the captain gives an on-scene
    justification. The verdict: permitted; the captain is steward.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    off_env(sv, "engines")
    decision(sv, "ditch", ["engines"], by="captain")
    result = sv.request_execution("ditch", "captain", emergency=ej(on_scene=True))
    assert result.permitted, result.failures
    assert sv.signals["engines"].steward == "captain"


# ===========================================================================
# SCENE 25 — THE NARRATOR READS THE NEW ENTRIES
# Proves: run_demo's describe() narrates an attestation and names the loops
# annotated (not latched) at an override.
# ===========================================================================

def test_demo_narrates_annotation_and_attestation(sv):
    """
    Setting the stage: "c" exited whistleblower, "d" attested and then
    overridden by "other". The verdict: the attestation line names the
    attester; the execution line names "c" as annotated.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    to_review(sv, "c")
    sv.exit("c", ExitType.WHISTLEBLOWER, "boisjoly", "goes outside",
            **EXIT_OBLIGATIONS[ExitType.WHISTLEBLOWER])
    decision(sv, "d", ["c"])
    sv.request_execution("d", "other", override_rationale="carried knowingly")
    assert describe(entries(sv, "RISK_EVIDENCE_ATTESTED")[-1]) == \
        f"d: risk evidence attested by {ATTESTER}"
    assert "annotated in their external exits ['c']" in \
        describe(entries(sv, "OPEN_LOOP_IRREVERSIBLE_EXECUTION")[-1])


# EXEUNT — end of file.

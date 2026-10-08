"""
THE EMERGENCY
A Play in Fifteen Scenes
========================

PROLOGUE
--------
Tests for the Emergency Justification (CCL-F v0.2, Layer 4, Execution
Gates, Overrides), Supervisor.request_execution(..., emergency=...):

  "An irreversible decision held only by off-envelope or containment
  reviews may proceed before those reviews are resolved under an Emergency
  Justification, and under no other condition. Reviews opened by any other
  escalation condition ... record failures of the coordination process
  itself, not conditions of the world, and no emergency justifies
  proceeding past them. Every element below is required and documented
  before execution": 1 Consequence, 2 Time, 3 No in-envelope option,
  4 Registered, not reclassified, 5 Separate authorization and stewardship
  (or the agent on scene, alone).
  "The justification suspends the holding reviews; it does not resolve
  them. Each still produces its resolution afterward, and a mandatory
  post-event review records whether every element held. Emergency
  Justifications are counted per failure mode, and recurring ones escalate
  under Rule 7 ... The justification is judged by its elements, never by
  its outcome."

The scenario-level cases (US Airways 1549, Apollo 13, and schedule
pressure dressed as an emergency) are in tests/test_scenarios.py.

THE PLAYBILL
    Prelude   sv (fixture), held_off_envelope(), justification() (helpers)
    Scene 1   test_emergency_executes_and_suspends_without_resolving
    Scene 2   test_off_envelope_signal_must_be_registered_experimental
    Scene 3   test_containment_signal_must_stay_in_containment
    Scene 4   test_each_documented_element_is_required        (parametrized, 6 runs)
    Scene 5   test_separate_authorization_unless_on_scene
    Scene 6   test_giver_independence_and_capacity_hold_even_on_scene
    Scene 7   test_override_power_is_needed_when_authority_is_enforced
    Scene 8   test_other_holds_are_not_suspendable
    Scene 9   test_only_for_irreversible_decisions_that_are_held
    Scene 10  test_never_bypasses_acceptance_or_layer0
    Scene 11  test_third_emergency_on_a_failure_mode_is_refused_and_escalates
    Scene 12  test_post_event_and_suspended_reviews_resolve_afterward
    Scene 13  test_emergency_from_an_event_dict
    Scene 14  test_plain_override_cannot_pass_a_suspendable_hold
    Scene 15  test_giver_stewards_loops_behind_the_hold_even_if_resolved
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# dataclasses.replace   a copy of a justification with one element changed.
# pytest                fixtures, parametrize, raises.
# cclf                  the runtime: Supervisor and its vocabulary, plus
#                       build_graph and Advisor for Scene 13.
# stagehands            shared set-up helpers (see tests/stagehands.py).
# ===========================================================================

from dataclasses import replace

import pytest

from cclf import (
    Advisor, AgentKind, Architecture, CommitmentState, EmergencyConsequence,
    EmergencyJustification, EscalationCondition, ExecutionClass, OperationalState, Power,
    Settings, SignalType, Supervisor, build_graph,
)
from stagehands import UPDATE, add_ees, decision, entries, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# S, E, O — short aliases.
S = CommitmentState
E = EscalationCondition
O = OperationalState

# GIVER — the agent who gives the justification when it must be someone
#   other than the acceptor ("director").
GIVER = "flight-director"

# BOARD — an independent reviewer for the reviews afterward.
BOARD = "review-board"


# ===========================================================================
# PRELUDE — the fixture and two helpers
# ===========================================================================

@pytest.fixture
def sv():
    """
    A new, empty Supervisor with default settings.

    Enter:   (nothing)
    Exit:    Supervisor()
    """
    return Supervisor()


def held_off_envelope(sv, signal_id="c", decision_id="d", mode="tank", root=None):
    """
    An accepted irreversible decision held only by the off-envelope review
    of one constraint, whose condition is now registered experimental and
    whose best evidence is on record.

    Enter:   sv, signal_id, decision_id
             mode   the signal's failure mode (counting, Scene 11)
             root   with authority enforced, the root (see stagehands)
    Exit:    the off-envelope StructuralReview
    """
    # PLAYERS IN THIS SCENE
    #   review   the off-envelope review

    to_review(sv, signal_id, state=O.OFF_ENVELOPE, failure_mode=mode)
    decision(sv, decision_id, [signal_id], root=root)
    sv.classify(signal_id, O.EXPERIMENTAL, "engineer")             # element 4
    add_ees(sv, f"best-{signal_id}-{decision_id}")
    [review] = [r for r in sv.reviews if r.trigger == O.OFF_ENVELOPE
                and signal_id in r.signal_ids]
    return review


def justification(evidence_id="best-c-d", on_scene=False, **changes):
    """
    A justification with every element documented.

    Enter:   evidence_id   the best-evidence id (element 4)
             on_scene      element 5's proviso
             **changes     fields to replace, to break one element
    Exit:    an EmergencyJustification
    """
    ej = EmergencyJustification(
        consequence=EmergencyConsequence.LIFE_SAFETY_CATASTROPHIC,
        time_estimate="crew oxygen lasts hours; the review takes weeks",
        options_considered=("wait for the review: crew lost", "abort direct: no margin"),
        best_evidence=(evidence_id,), on_scene=on_scene,
        rationale="no in-envelope option survives the time available")
    return replace(ej, **changes) if changes else ej


# ===========================================================================
# SCENE 1 — PROCEED, AND KEEP THE QUESTION OPEN
# Proves: a valid justification executes the decision; the holding review
# is suspended, not resolved; the unresolved loop is latched into
# executed_open with the giver as steward; a post-event review opens; every
# element is logged.
# ===========================================================================

def test_emergency_executes_and_suspends_without_resolving(sv):
    """
    Enter:   sv   fixture
    Exit:    passes as described in the scene banner
    """
    # PLAYERS IN THIS SCENE
    #   review    the off-envelope review
    #   result    the GateResult
    #   logged    the EMERGENCY_JUSTIFICATION entry
    #   post      the post-event review
    #   auth      the latched loop's authorization record

    review = held_off_envelope(sv)
    result = sv.request_execution("d", GIVER, emergency=justification())
    assert result.permitted and result.overridden and result.emergency_id == "EJ1"
    assert sv.decisions["d"].executed
    # --- Suspended, not resolved -------------------------------------------
    assert not review.resolved and review.suspended_by == ["EJ1"]
    # --- The loop carried open ---------------------------------------------
    assert result.latched_signals == ["c"] and sv.signals["c"].state == S.EXECUTED_OPEN
    [auth] = sv.signals["c"].open_loop_authorizations
    assert (auth.authorized_by, auth.emergency_id) == (GIVER, "EJ1")
    assert sv.signals["c"].steward == GIVER
    # --- Every element on record -------------------------------------------
    [logged] = entries(sv, "EMERGENCY_JUSTIFICATION")
    for key in ("consequence", "time_estimate", "options_considered", "best_evidence",
                "on_scene", "given_by", "holding_reviews", "failure_modes"):
        assert key in logged.payload
    assert logged.payload["holding_reviews"] == [review.review_id]
    assert logged.payload["failure_modes"] == ["tank"]
    # --- The mandatory post-event review -----------------------------------
    [post] = [r for r in sv.reviews if r.condition == E.EMERGENCY_POST_EVENT]
    assert post.decision_id == "d" and not post.resolved and post.signal_ids == ["c"]
    assert entries(sv, "REVIEW_SUSPENDED")[0].payload["review"] == review.review_id


# ===========================================================================
# SCENE 2 — REGISTERED, NOT RECLASSIFIED
# Proves: element 4: "An off-envelope condition is classified Experimental".
# ===========================================================================

def test_off_envelope_signal_must_be_registered_experimental(sv):
    """
    Setting the stage: the signal is left classified off-envelope.
    The verdict: refused (EMERGENCY_REFUSED), nothing executed.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult

    to_review(sv, "c", state=O.OFF_ENVELOPE)
    decision(sv, "d", ["c"])
    add_ees(sv, "best-c-d")
    result = sv.request_execution("d", GIVER, emergency=justification())
    assert not result.permitted and not sv.decisions["d"].executed
    assert any("element 4" in f and "not experimental" in f for f in result.failures)
    assert entries(sv, "EMERGENCY_REFUSED")
    assert sv.signals["c"].state == S.ESCALATED


# ===========================================================================
# SCENE 3 — CONTAINMENT STAYS CONTAINMENT
# Proves: element 4: "a containment condition stays in containment".
# ===========================================================================

def test_containment_signal_must_stay_in_containment(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if a containment-held decision proceeds while the signal
             stays in containment, and a twin whose signal was moved out of
             containment is refused
    """
    # PLAYERS IN THIS SCENE
    #   ok, moved   the GateResults of the two decisions

    for sid, did in (("k1", "d1"), ("k2", "d2")):
        to_review(sv, sid, state=O.CONTAINMENT, failure_mode=f"mode-{sid}")
        decision(sv, did, [sid])
        add_ees(sv, f"best-{did}")
    sv.classify("k2", O.EXPERIMENTAL, "engineer")
    ok = sv.request_execution("d1", GIVER, emergency=justification("best-d1"))
    moved = sv.request_execution("d2", GIVER, emergency=justification("best-d2"))
    assert ok.permitted, ok.failures
    assert not moved.permitted
    assert any("no longer classified containment" in f for f in moved.failures)


# ===========================================================================
# SCENE 4 — EVERY ELEMENT IS DOCUMENTED BEFORE EXECUTION
# Proves: elements 1-4 and the rationale: each missing one is refused.
# ===========================================================================

@pytest.mark.parametrize("changes, needle", [
    (dict(consequence="schedule"), "element 1"),
    (dict(time_estimate="  "), "element 2"),
    (dict(options_considered=()), "element 3"),
    (dict(best_evidence=()), "element 4: no best engineering evidence"),
    (dict(best_evidence=("no-such-evidence",)), "not on record"),
    (dict(rationale=""), "rationale"),
], ids=["consequence", "time", "options", "no-evidence", "unknown-evidence", "rationale"])
def test_each_documented_element_is_required(sv, changes, needle):
    """
    Enter:   sv       fixture
             changes  the element broken
             needle   text the refusal must contain
    Exit:    passes if refused with that reason and nothing executed
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult

    held_off_envelope(sv)
    result = sv.request_execution("d", GIVER, emergency=justification(**changes))
    assert not result.permitted and not sv.decisions["d"].executed
    assert any(needle in f for f in result.failures), result.failures


# ===========================================================================
# SCENE 5 — A SECOND AGENT, UNLESS THERE IS NO TIME
# Proves: element 5: the acceptor cannot give it, unless on_scene: "Where
# the harm would arrive before any second agent could be consulted ... the
# agent on scene may act alone".
# ===========================================================================

def test_separate_authorization_unless_on_scene(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the acceptor ("director") is refused without
             on_scene (naming the external-reviewer remedy) and succeeds
             with it, becoming steward of the loop carried open
    """
    # PLAYERS IN THIS SCENE
    #   refused, granted   the two GateResults

    held_off_envelope(sv)
    refused = sv.request_execution("d", "director", emergency=justification())
    assert not refused.permitted
    assert any("element 5" in f for f in refused.failures)
    assert any("external reviewer" in f for f in refused.failures)
    granted = sv.request_execution("d", "director", emergency=justification(on_scene=True))
    assert granted.permitted and sv.signals["c"].steward == "director"


# ===========================================================================
# SCENE 6 — INDEPENDENCE AND CAPACITY
# Proves: off scene, the giver sits outside the acceptor's reporting line;
# on scene or off, the giver needs obligation capacity (Agent
# Admissibility: open-loop authorization is a stewardship act).
# ===========================================================================

def test_giver_independence_and_capacity_hold_even_on_scene(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the acceptor's report is refused off scene, and an
             automation agent is refused even on scene
    """
    # PLAYERS IN THIS SCENE
    #   result   each GateResult

    held_off_envelope(sv)
    sv.register_reporting_line(GIVER, "director", by="hr")
    result = sv.request_execution("d", GIVER, emergency=justification())
    assert not result.permitted and any("reports to director" in f for f in result.failures)
    sv.register_agent("autopilot", AgentKind.AUTOMATION, by="ops")
    result = sv.request_execution("d", "autopilot", emergency=justification(on_scene=True))
    assert not result.permitted and any("obligation capacity" in f for f in result.failures)


# ===========================================================================
# SCENE 7 — A GRANTED POWER, EVEN IN AN EMERGENCY
# Proves: with authority enforced, the giver needs OVERRIDE power.
# ===========================================================================

def test_override_power_is_needed_when_authority_is_enforced():
    """
    Enter:   (nothing)
    Exit:    passes if a giver with EXECUTE only is refused, and succeeds
             once granted OVERRIDE
    """
    # PLAYERS IN THIS SCENE
    #   sv       a Supervisor with "nasa" as authority root
    #   result   each GateResult

    sv = Supervisor(Settings(authority_roots=frozenset({"nasa"})))
    sv.grant("director", Power.AUTHORIZE, "d", by="nasa")
    sv.grant(GIVER, Power.EXECUTE, "d", by="nasa")
    held_off_envelope(sv, root="nasa")
    result = sv.request_execution("d", GIVER, emergency=justification())
    assert not result.permitted and any("does not hold override" in f for f in result.failures)
    sv.grant(GIVER, Power.OVERRIDE, "d", by="nasa")
    assert sv.request_execution("d", GIVER, emergency=justification()).permitted


# ===========================================================================
# SCENE 8 — FAILURES OF THE PROCESS ARE NOT EMERGENCIES
# Proves: a decision also held by any other review (here a recurrence
# review) cannot proceed under a justification.
# ===========================================================================

def test_other_holds_are_not_suspendable(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if refused naming the recurrence review, which stays
             unsuspended, and nothing executed
    """
    # PLAYERS IN THIS SCENE
    #   n        recurrence member number
    #   result   the GateResult
    #   recur    the recurrence review

    for n in (1, 2):
        to_review(sv, f"m{n}", recurrence_group="g")
    to_review(sv, "c", state=O.OFF_ENVELOPE, recurrence_group="g")   # third member
    decision(sv, "d", ["c"])
    sv.classify("c", O.EXPERIMENTAL, "engineer")
    add_ees(sv, "best-c-d")
    result = sv.request_execution("d", GIVER, emergency=justification())
    [recur] = [r for r in sv.reviews if r.condition == E.RECURRENCE_THRESHOLD]
    assert not result.permitted and not sv.decisions["d"].executed
    assert any(recur.review_id in f and "coordination process itself" in f
               for f in result.failures)
    assert recur.suspended_by == []


# ===========================================================================
# SCENE 9 — ONLY WHERE IT APPLIES
# Proves: "An irreversible decision held only by off-envelope or
# containment reviews": not a decision held by nothing, not an elevated one.
# ===========================================================================

def test_only_for_irreversible_decisions_that_are_held(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if an irreversible decision with no holding review, and
             an elevated decision, are both refused
    """
    # PLAYERS IN THIS SCENE
    #   result   each GateResult

    to_review(sv, "open-c")                                        # no review at all
    decision(sv, "free", ["open-c"])
    add_ees(sv, "best-c-d")
    result = sv.request_execution("free", GIVER, emergency=justification())
    assert not result.permitted and any("not held by an off-envelope" in f
                                        for f in result.failures)
    to_review(sv, "low", state=O.OFF_ENVELOPE)
    # The loop's steward leaves, so the elevated gate fails "open loops
    # documented" and the justification is actually judged.
    sv.signals["low"].steward = None
    decision(sv, "elev", ["low"], execution_class=ExecutionClass.ELEVATED)
    result = sv.request_execution("elev", GIVER, emergency=justification())
    assert not result.permitted and any("only to an irreversible decision" in f
                                        for f in result.failures)


# ===========================================================================
# SCENE 10 — WHAT AN EMERGENCY NEVER BYPASSES
# Proves: a missing Rule 4 acceptance, and a Layer 0 void at an
# irreversible decision.
# ===========================================================================

def test_never_bypasses_acceptance_or_layer0(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if an unaccepted decision is refused under Rule 4
             before the justification is read, and a decision whose
             failure mode has no steward is refused for the Layer 0 void
    """
    # PLAYERS IN THIS SCENE
    #   result   each GateResult

    to_review(sv, "c", state=O.OFF_ENVELOPE)
    sv.classify("c", O.EXPERIMENTAL, "engineer")
    decision(sv, "d", ["c"], accept=False)
    add_ees(sv, "best-c-d")
    result = sv.request_execution("d", GIVER, emergency=justification())
    assert not result.permitted and result.failures[0].startswith("Rule 4")
    to_review(sv, "v", state=O.OFF_ENVELOPE, steward=None)
    sv.classify("v", O.EXPERIMENTAL, "engineer")
    decision(sv, "dv", ["v"])
    result = sv.request_execution("dv", GIVER, emergency=justification())
    assert not result.permitted and result.architecture_void
    assert any("Layer 0 void cannot be suspended" in f for f in result.failures)


# ===========================================================================
# SCENE 11 — A THIRD EMERGENCY IS A PATTERN
# Proves: "Emergency Justifications are counted per failure mode, and
# recurring ones escalate under Rule 7: a third emergency on the same
# failure mode is a pattern, not a black swan." The third is refused and
# opens a recurrence review no justification can suspend.
# ===========================================================================

def test_third_emergency_on_a_failure_mode_is_refused_and_escalates(sv):
    """
    Setting the stage: three decisions, each held by the off-envelope review
    of its own signal, all naming failure mode "tank". The verdict: the
    first two proceed (EJ1, EJ2); the third is refused, a RECURRENCE review
    on "emergency:tank" opens over all three signals, and another failure
    mode is unaffected.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   n        decision number
    #   result   the third GateResult
    #   recur    the emergency recurrence review

    for n in (1, 2):
        held_off_envelope(sv, f"c{n}", f"d{n}")
        assert sv.request_execution(f"d{n}", GIVER,
                                    emergency=justification(f"best-c{n}-d{n}")).permitted
    held_off_envelope(sv, "c3", "d3")
    result = sv.request_execution("d3", GIVER, emergency=justification("best-c3-d3"))
    assert not result.permitted and any("Rule 7" in f and "'tank'" in f
                                        for f in result.failures)
    [recur] = [r for r in sv.reviews if r.scope == "emergency:tank"]
    assert recur.condition == E.RECURRENCE_THRESHOLD and not recur.suspendable
    assert sorted(recur.signal_ids) == ["c1", "c2", "c3"]
    # --- Another failure mode is counted separately ------------------------
    held_off_envelope(sv, "x1", "dx", mode="valve")
    assert sv.request_execution("dx", GIVER, emergency=justification("best-x1-dx")).permitted


# ===========================================================================
# SCENE 12 — THE REVIEWS STILL PRODUCE THEIR RESOLUTIONS
# Proves: after execution, the suspended review is still resolved by what
# its trigger requires, and the post-event review by a written finding on
# whether every element held; neither by the giver or acceptor.
# ===========================================================================

def test_post_event_and_suspended_reviews_resolve_afterward(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the giver cannot resolve the post-event review, a
             finding without elements_held is refused, BOARD resolves it,
             and the suspended review still needs its reclassification
    """
    # PLAYERS IN THIS SCENE
    #   review   the suspended off-envelope review
    #   post     the post-event review

    review = held_off_envelope(sv)
    sv.request_execution("d", GIVER, emergency=justification())
    [post] = [r for r in sv.reviews if r.condition == E.EMERGENCY_POST_EVENT]
    with pytest.raises(Exception, match="accepted or requested"):
        sv.resolve_review(post.review_id, GIVER, finding="all held", elements_held=True)
    with pytest.raises(Exception, match="every element held"):
        sv.resolve_review(post.review_id, BOARD, finding="reviewed")
    sv.resolve_review(post.review_id, BOARD, finding="each element held; time confirmed",
                      elements_held=True)
    assert post.resolved and post.elements_held is True
    with pytest.raises(Exception, match="reclassified out of off-envelope"):
        sv.resolve_review(review.review_id, BOARD, finding="it worked out", **UPDATE)
    with pytest.raises(Exception, match="accepted or requested"):
        sv.resolve_review(review.review_id, "director", finding="it worked out")
    add_ees(sv, "post-flight-test")
    sv.classify("c", O.ELEVATED_UNCERTAINTY, "test-engineer", ["post-flight-test"])
    sv.resolve_review(review.review_id, BOARD, finding="envelope extended by test")
    assert review.resolved and review.suspended_by == ["EJ1"]


# ===========================================================================
# SCENE 13 — FROM AN EVENT
# Proves: the graph turns an "emergency" JSON object into an
# EmergencyJustification; a consequence of "schedule" cannot be built.
# ===========================================================================

def test_emergency_from_an_event_dict(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the event executes the decision, and a schedule
             consequence raises ValueError
    """
    # PLAYERS IN THIS SCENE
    #   graph   the event pipeline over sv
    #   event   the request_execution event
    #   out     its final state

    held_off_envelope(sv)
    graph = build_graph(sv, Advisor(ask=lambda system, user: ""))
    event = {"op": "request_execution", "decision_id": "d", "by": GIVER,
             "emergency": {"consequence": "life_safety_catastrophic",
                           "time_estimate": "minutes", "options_considered": ["none"],
                           "best_evidence": ["best-c-d"], "on_scene": False,
                           "rationale": "no time"}}
    out = graph.invoke({"event": event})
    assert out["result"].permitted and out["result"].emergency_id == "EJ1"
    event["emergency"] = dict(event["emergency"], consequence="schedule")
    with pytest.raises(ValueError):
        graph.invoke({"event": event})


# ===========================================================================
# SCENE 14 — AN OVERRIDE IS NOT AN EMERGENCY
# Proves: an override cannot pass an off-envelope hold; its refusal points
# to the Emergency Justification as the only way past such a hold.
# ===========================================================================

def test_plain_override_cannot_pass_a_suspendable_hold(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the override is refused, mentioning the Emergency
             Justification, and the review is not suspended
    """
    # PLAYERS IN THIS SCENE
    #   review   the off-envelope review
    #   result   the GateResult

    review = held_off_envelope(sv)
    result = sv.request_execution("d", GIVER, override_rationale="we must go")
    assert not result.permitted
    assert any("only an Emergency Justification can suspend" in f for f in result.failures)
    assert review.suspended_by == []


# ===========================================================================
# SCENE 15 — THE GIVER STEWARDS THE LOOPS BEHIND THE HOLD
# Proves: element 5: the giver "is registered as steward of the off-envelope
# loops for its duration", even a loop the gate counts as resolved (and so
# does not latch).
# ===========================================================================

def test_giver_stewards_loops_behind_the_hold_even_if_resolved(sv):
    """
    Setting the stage: "c" evidence-closed, then classified off-envelope
    (the review names it but it stays closed), then experimental.
    The verdict: nothing is latched, and the giver is c's steward.

    Enter:   sv   fixture
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult

    to_review(sv, "c")
    add_ees(sv, "measured", ["c"])
    sv.attempt_closure("c", "chief-engineer", "technical", ["measured"])
    sv.classify("c", O.OFF_ENVELOPE, "engineer")
    sv.classify("c", O.EXPERIMENTAL, "engineer")
    decision(sv, "d", ["c"])
    add_ees(sv, "best-c-d")
    result = sv.request_execution("d", GIVER, emergency=justification())
    assert result.permitted, result.failures
    assert result.latched_signals == [] and sv.signals["c"].state == S.CLOSED_EVIDENCE
    assert sv.signals["c"].steward == GIVER
    assert entries(sv, "STEWARD_ASSIGNED")[-1].payload["emergency"] == "EJ1"

# EXEUNT — end of file.

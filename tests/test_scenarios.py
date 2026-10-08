"""
FIVE HISTORIES, REPLAYED
A Play in Fifteen Scenes
========================

PROLOGUE
--------
Tests for the replayable case histories in scenarios/ (Challenger,
Therac-25, Boeing 737 MAX MCAS, Apollo 13, US Airways 1549), each run end
to end through
cclf.graph.replay(). The expected outcomes come from what CCL-F v0.2 says
about each case:

  Challenger: seven missions of O-ring erosion closed by authority, "The
    escalation threshold was crossed after the third occurrence" (Layer 1,
    Rule 7, Cases); classified nominal "despite O-ring temperatures below
    anything in the validated test data" (Layer 1, Rule 2, Cases); the
    framing signal inverted the burden of proof (Layer 1, Rule 1); the
    launch was an irreversible decision with open constraint loops
    (Key Definitions, Lock-in Closure).
  Therac-25: six overdoses "before the incidents were connected" (Rule 7);
    the only legally obligated reporter was the manufacturer (Layer 0, The
    Eight Sub-Conditions, AP.6 — Reporter Independence; Layer 0, The Eight
    Void Types, AP-F: Captured Channel).
  MCAS: classified a "minor stability enhancement" (Rule 2); behaved
    differently in different internal documents, never stabilized (Rule 3:
    nothing known, assumed or uncertain was ever registered with the
    decision); the AR's standing subordinated to the regulated company
    (Rule 9).
  Apollo 13 and Flight 1549: the two cases the draft says meet the
    Emergency Justification (Layer 4, Overrides): "Apollo 13 had hours and
    a separate authority on the ground; Flight 1549 had minutes and no
    time to consult one". Both are judged by their elements; neither is
    credited for its outcome, and nothing here reads an outcome.

Every replay must leave an intact audit chain (Layer 4, Audit Trail).

THE PLAYBILL
    Scene 1   replayed()                         (helper) replay a scenario
              refused_closures()                 (helper) which closures were refused
    Scene 2   test_every_scenario_replays_with_intact_chain   (parametrized, 3 runs)
    Scene 3   test_challenger_waivers_refused_after_threshold
    Scene 4   test_challenger_nominal_classification_refused
    Scene 5   test_challenger_framing_suppresses_uncertainty
    Scene 6   test_challenger_launch_blocked_and_override_refused
    Scene 7   test_challenger_what_it_takes_to_launch
    Scene 8   test_scenario_authority_counts_escalate         (was a spec mismatch, now fixed;
                                                                parametrized, 2 runs)
    Scene 9   test_therac25_closures_refused_after_threshold
    Scene 10  test_therac25_captured_channel_blocks_execution
    Scene 11  test_mcas_unstable_classification_and_captured_channel
    Scene 12  test_mcas_override_refused
    Scene 13  test_apollo13_emergency_justification_by_separate_authority
    Scene 14  test_usair1549_emergency_justification_on_scene
    Scene 15  test_schedule_pressure_framed_as_emergency_is_refused

READER'S NOTE — a module-level cache
    Replaying a scenario takes a moment (the graph is rebuilt each time).
    Several scenes look at the same replay, so replayed() keeps results in
    the module-level dict _CACHE and replays each scenario only once. The
    tests only READ the cached supervisors, never change them.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       parametrize.
# cclf         Advisor, Architecture, AuditTrail, CommitmentState,
#              EmergencyConsequence, EmergencyJustification,
#              EscalationCondition, OperationalState, TransitionRefused, replay.
# scenarios    SCENARIOS: name -> list of events.
# stagehands   entries.
# ===========================================================================

import pytest

from cclf import (
    Advisor, Architecture, AuditTrail, CommitmentState, EmergencyConsequence,
    EmergencyJustification, EscalationCondition, OperationalState, TransitionRefused, replay,
)
from scenarios import SCENARIOS
from stagehands import entries


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# S, E — short aliases.
S = CommitmentState
E = EscalationCondition

# _CACHE — scenario name -> (Supervisor, list of per-event outcomes).
#   Filled lazily by replayed(); see READER'S NOTE.
_CACHE: dict = {}

# OFFLINE_ADVISOR — an Advisor whose "model" is a plain function returning
#   nothing useful. The scenarios contain no "report" events, so it is never
#   asked; passing it guarantees no real LLM client is ever built.
OFFLINE_ADVISOR = Advisor(ask=lambda system, user: "")

# FRR_LATE — the Challenger FRR waiver signals from the third occurrence on.
FRR_LATE = [f"constraint-frr-{n}" for n in range(3, 7)]


# ===========================================================================
# SCENE 1 — RAISE THE CURTAIN
# replayed(): replay one scenario (once) and return its supervisor and outcomes.
# refused_closures(): pick the refused closure attempts out of those outcomes.
# ===========================================================================

def replayed(name):
    """
    Replay a scenario through the pipeline, caching the result.

    Enter:   name   "challenger", "therac25" or "mcas"
    Exit:    (supervisor, outcomes) where outcomes is a list of
             (event, pipeline output) pairs in replay order
    """
    # PLAYERS IN THIS SCENE
    #   outcomes   collected by the on_event callback
    #   sv         the Supervisor after replay

    if name not in _CACHE:
        outcomes = []
        sv = replay(SCENARIOS[name], advisor=OFFLINE_ADVISOR,
                    on_event=lambda ev, out: outcomes.append((ev, out)))
        _CACHE[name] = (sv, outcomes)
    return _CACHE[name]


def refused_closures(outcomes):
    """
    Signal IDs whose attempt_closure event came back refused.

    Enter:   outcomes   the list from replayed()
    Exit:    list of signal IDs, in replay order
    """
    return [ev["signal_id"] for ev, out in outcomes
            if ev["op"] == "attempt_closure" and out["refused"]]


# ===========================================================================
# SCENE 2 — EVERY RECORD HOLDS TOGETHER
# Proves: each scenario replays end to end and leaves a verifiable audit
# chain (Layer 4, Audit Trail). (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_scenario_replays_with_intact_chain(name):
    """
    Each scenario's audit trail verifies and has one outcome per event.

    Enter:   name   each scenario name
    Exit:    passes if verify() is (True, "ok") and every event was processed
    """
    # PLAYERS IN THIS SCENE
    #   sv, outcomes   the replayed Supervisor and its per-event outcomes

    sv, outcomes = replayed(name)
    assert AuditTrail.verify(sv.audit.entries()) == (True, "ok")
    assert len(outcomes) == len(SCENARIOS[name])


# ===========================================================================
# SCENE 3 — CHALLENGER: THE THIRD WAIVER
# Proves: Rule 7: from the third occurrence the recurrence group is under
# structural review, and each later FRR waiver is refused; the first two
# are recorded as (flagged) authority closures.
# ===========================================================================

def test_challenger_waivers_refused_after_threshold():
    """
    Waivers 1-2 close by authority; waivers 3-6 are refused and escalated.

    Enter:   (nothing)
    Exit:    passes if the refused closures include exactly FRR_LATE among
             the FRR signals, those four are escalated, and the first two
             signals are closed_authority
    """
    # PLAYERS IN THIS SCENE
    #   sv, outcomes   the Challenger replay's Supervisor and outcomes

    sv, outcomes = replayed("challenger")
    assert [s for s in refused_closures(outcomes) if s.startswith("constraint-frr")] \
        == FRR_LATE
    assert all(sv.signals[s].state == S.ESCALATED for s in FRR_LATE)
    assert sv.signals["launch-constraint-51F"].state == S.CLOSED_AUTHORITY
    assert sv.signals["constraint-frr-2"].state == S.CLOSED_AUTHORITY
    assert any(r.condition == E.RECURRENCE_THRESHOLD for r in sv.open_reviews())


# ===========================================================================
# SCENE 4 — CHALLENGER: "NOMINAL" REFUSED
# Proves: Rule 2: the nominal classifications in the waiver chain are
# refused and recorded as elevated uncertainty; the cold O-ring is
# off-envelope and escalates.
# ===========================================================================

def test_challenger_nominal_classification_refused():
    """
    No Challenger signal ends classified nominal; the cold O-ring is off-envelope.

    Enter:   (nothing)
    Exit:    passes if there are six CLASSIFICATION_REJECTED entries, no
             signal is nominal, and cold-oring-no-launch is off_envelope
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Challenger replay's Supervisor

    sv, _ = replayed("challenger")
    assert len(entries(sv, "CLASSIFICATION_REJECTED")) == 6
    assert all(s.operational_state != OperationalState.NOMINAL for s in sv.signals.values())
    assert sv.signals["cold-oring-no-launch"].operational_state == OperationalState.OFF_ENVELOPE


# ===========================================================================
# SCENE 5 — CHALLENGER: "PROVE IT'S UNSAFE"
# Proves: (Key Definitions, Framing Signal) frame adoption closes the frame
# by authority and suppresses the displaced uncertainty; the suppression
# escalates at the execution request (Layer 2, Escalation Conditions).
# ===========================================================================

def test_challenger_framing_suppresses_uncertainty():
    """
    The burden-of-proof frame is closed_authority and seal-uncertainty suppressed.

    Enter:   (nothing)
    Exit:    passes if both states hold and SUPPRESSED_BEFORE_EXECUTION was raised
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Challenger replay's Supervisor

    sv, _ = replayed("challenger")
    assert sv.signals["burden-of-proof-frame"].state == S.CLOSED_AUTHORITY
    assert sv.signals["seal-uncertainty"].state == S.SUPPRESSED
    assert any(r.condition == E.SUPPRESSED_BEFORE_EXECUTION for r in sv.reviews)


# ===========================================================================
# SCENE 6 — CHALLENGER: THE GATE, THEN THE REFUSED OVERRIDE
# Proves: the launch gate is blocked (open constraints, unreviewed
# recurrence, Layer 0 stewardship void), and the override that follows is
# refused (Layer 4, Overrides): unresolved structural reviews hold an
# irreversible decision, a Layer 0 void cannot be overridden at an
# irreversible decision, and the accepting agent cannot override its gate.
# ===========================================================================

def test_challenger_launch_blocked_and_override_refused():
    """
    EXECUTION_BLOCKED, then OVERRIDE_REFUSED for kilminster; no launch.

    Enter:   (nothing)
    Exit:    passes if the blocked failures include open constraints,
             unreviewed recurrence and AP-A; the override is refused for
             all three reasons; nothing executed, overrode or latched
    """
    # PLAYERS IN THIS SCENE
    #   sv         the Challenger replay's Supervisor
    #   blocked    the EXECUTION_BLOCKED entry
    #   failures   its failures, joined with " | "
    #   refused    the OVERRIDE_REFUSED entry
    #   reasons    its reasons, joined

    sv, _ = replayed("challenger")
    [blocked] = entries(sv, "EXECUTION_BLOCKED")
    failures = " | ".join(blocked.payload["failures"])
    for needle in ("constraint/anomaly loops not evidence-closed",
                   "recurrence groups not reviewed", "AP-A"):
        assert needle in failures
    assert blocked.payload["architecture_void"] is True
    [refused] = entries(sv, "OVERRIDE_REFUSED")
    reasons = " | ".join(refused.payload["reasons"])
    assert refused.actor == "kilminster"
    assert "hold irreversible execution" in reasons and "cannot be overridden" in reasons
    assert "kilminster accepted this decision" in reasons
    assert "Layer 0 void cannot be overridden" in reasons
    assert not sv.decisions["launch-51L"].executed
    assert entries(sv, "GATE_OVERRIDE") == []
    assert entries(sv, "OPEN_LOOP_IRREVERSIBLE_EXECUTION") == []


# ===========================================================================
# SCENE 7 — CHALLENGER: WHAT IT WOULD TAKE TO LAUNCH
# Proves: the runtime leaves one way forward, the one the draft names.
# Another agent's override is still refused while the reviews are open;
# nobody who accepted or requested the launch may resolve them; each review
# is resolved by what its trigger requires (the off-envelope one only by
# evidence-based reclassification); the Layer 0 void cannot be overridden,
# so the architecture has to be registered; the suppressed signal has to be
# brought back into view. Then an override by an agent other than the
# acceptor goes ahead, and every loop the gate does not count as resolved
# is latched into executed_open with that agent as its steward. (The agents
# and evidence after the replay are hypothetical, not historical claims.)
# ===========================================================================

def test_challenger_what_it_takes_to_launch():
    """
    Override refused while reviews are open; conflicted resolvers refused;
    independent resolution by trigger; void refused, then architecture
    registered; a separate override executes with the latch.

    Enter:   (nothing)
    Exit:    passes if each step behaves as described above
    """
    # PLAYERS IN THIS SCENE
    #   sv        a fresh Challenger replay (not the cached one: this test
    #             changes it)
    #   held      the GateResult of an override while reviews are open
    #   r         each open review
    #   result    the final GateResult
    #   latched   signals latched into executed_open

    sv = replay(SCENARIOS["challenger"], advisor=OFFLINE_ADVISOR)
    # Another agent's override: still held by the reviews.
    held = sv.request_execution("launch-51L", "launch-director", override_rationale="go")
    assert not held.permitted and any("hold irreversible execution" in f for f in held.failures)
    # Those who want the launch cannot resolve what holds it.
    open_ids = [r.review_id for r in sv.open_reviews()]
    for conflicted in ("kilminster", "launch-director"):
        with pytest.raises(TransitionRefused):
            sv.resolve_review(open_ids[0], conflicted, "erosion is acceptable",
                              elements_changed=["nothing"], level="flight")
    # The off-envelope review cannot be resolved by a Rule 8 update, only by
    # an evidence-based reclassification out of off-envelope.
    [off] = [r for r in sv.open_reviews() if r.trigger == OperationalState.OFF_ENVELOPE]
    with pytest.raises(TransitionRefused, match="reclassified out of off-envelope"):
        sv.resolve_review(off.review_id, "independent-review-board", finding="looks fine")
    sv.add_evidence("cold-joint-test", "joint seals at the forecast temperature", "test rig",
                    "direct_measurement", "independent-test-lab", "independent-review-board")
    sv.classify("cold-oring-no-launch", OperationalState.ELEVATED_UNCERTAINTY,
                "independent-review-board", ["cold-joint-test"])
    # An independent reviewer resolves each review by what its trigger requires.
    for r in sv.open_reviews():
        if r is off:
            sv.resolve_review(r.review_id, "independent-review-board",
                              finding="seal tested at the forecast temperature")
        else:
            sv.resolve_review(r.review_id, "independent-review-board",
                              "joint erosion is a design defect: a new launch constraint "
                              "with a temperature floor and a redesign requirement",
                              elements_changed=["launch constraint: joint temperature floor",
                                                "stewardship: joint redesign owner"],
                              level="the SRB joint design, not each flight's waiver")
    # A suppressed signal reopens a review at every request: it has to be
    # brought back into view first. And the Layer 0 void is no failure an
    # override can answer at an irreversible decision.
    still = sv.request_execution("launch-51L", "launch-director", override_rationale="go")
    assert not still.permitted
    assert any("Layer 0 void cannot be overridden" in f for f in still.failures)
    sv.reenter_suppressed("seal-uncertainty", "independent-review-board",
                          "the burden-of-proof frame is withdrawn; uncertainty back in review")
    for r in sv.open_reviews():
        sv.resolve_review(r.review_id, "independent-review-board",
                          "suppression of a safety uncertainty by framing is a coordination "
                          "failure: framing signals now require evidence closure",
                          elements_changed=["classification criterion: framing signals"])
    sv.register_architecture(Architecture(stewards={"srb-joint-seal": "srb-joint-owner"},
                                          successors={"srb-joint-seal": "srb-deputy"}),
                             by="nasa-principals")
    result = sv.request_execution("launch-51L", "launch-director",
                                  override_rationale="proceeding under the new constraint")
    assert result.permitted and result.overridden, result.failures
    latched = sorted(s.signal_id for s in sv.signals.values() if s.state == S.EXECUTED_OPEN)
    assert latched == sorted(result.latched_signals)
    assert "cold-oring-no-launch" in latched             # the night-before constraint
    assert "seal-uncertainty" in latched                 # an open loop of another type
    assert set(FRR_LATE) <= set(latched)                 # escalated, then released by review
    assert all(sv.signals[x].steward == "launch-director" for x in latched)
    assert not any(s.state in (S.ESCALATED, S.SUPPRESSED, S.UNDER_REVIEW)
                   for s in sv.signals.values())
    assert entries(sv, "OPEN_LOOP_IRREVERSIBLE_EXECUTION")[0].actor == "launch-director"


# ===========================================================================
# SCENE 8 — THE OVERRIDES NOBODY COUNTED
# Proves: both Challenger (three authority closures)
# and MCAS (two) cross the authority-closure threshold on an irreversible
# decision (Layer 2, Escalation Conditions). (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("name", ["challenger", "mcas"])
def test_scenario_authority_counts_escalate(name):
    """
    The authority-closure-count escalation is raised in the replay.

    Enter:   name   "challenger" or "mcas"
    Exit:    passes if an AUTHORITY_CLOSURE_COUNT review exists
    """
    # PLAYERS IN THIS SCENE
    #   sv   the named scenario's replayed Supervisor

    sv, _ = replayed(name)
    assert any(r.condition == E.AUTHORITY_CLOSURE_COUNT for r in sv.reviews)


# ===========================================================================
# SCENE 9 — THERAC-25: THE PATTERN NOBODY CONNECTED
# Proves: Rule 7: AECL's authority closures are refused from the third
# overdose on; after the Tyler reproduction the reopened early incidents
# join the open recurrence review, so all six end escalated.
# ===========================================================================

def test_therac25_closures_refused_after_threshold():
    """
    Overdoses 3-6 closures refused; all six signals escalated at the end.

    Enter:   (nothing)
    Exit:    passes if the refused list is overdose-3..6, every signal is
             escalated, and the two reopens are logged by the physicist
    """
    # PLAYERS IN THIS SCENE
    #   reopens   TRANSITION entries leaving closed_authority
    #   sv, outcomes   the Therac-25 replay's Supervisor and outcomes

    sv, outcomes = replayed("therac25")
    assert refused_closures(outcomes) == [f"overdose-{n}" for n in range(3, 7)]
    assert all(s.state == S.ESCALATED for s in sv.signals.values())
    reopens = [e for e in entries(sv, "TRANSITION") if e.payload["from"] == "closed_authority"]
    assert [e.actor for e in reopens] == ["etcc-physicist", "etcc-physicist"]


# ===========================================================================
# SCENE 10 — THERAC-25: THE CAPTURED CHANNEL
# Proves: AP.6 / AP-F: the only reporter is the interested party, so the
# gate reports a Layer 0 void and execution is not permitted (and there is
# no override in this history).
# ===========================================================================

def test_therac25_captured_channel_blocks_execution():
    """
    continue-treatment is blocked with an AP-F void and is not executed.

    Enter:   (nothing)
    Exit:    passes if the only gate entry is EXECUTION_BLOCKED, it is
             architecture_void with an AP-F failure, and nothing executed
    """
    # PLAYERS IN THIS SCENE
    #   blocked   the EXECUTION_BLOCKED entry
    #   sv        the Therac-25 replay's Supervisor

    sv, _ = replayed("therac25")
    [blocked] = entries(sv, "EXECUTION_BLOCKED")
    assert blocked.payload["architecture_void"] is True
    assert any(f.startswith("AP-F captured channel") for f in blocked.payload["failures"])
    assert entries(sv, "GATE_OVERRIDE") == [] and entries(sv, "EXECUTION_PERMITTED") == []
    assert not sv.decisions["continue-treatment"].executed


# ===========================================================================
# SCENE 11 — MCAS: NEVER STABILIZED, CAPTURED REPORTER
# Proves: Rules 2-3: the nominal classifications are refused; the
# acceptance names nothing known, assumed or uncertain, so the
# classification is not stabilized (Rule 3 registration), while the later
# reclassification to experimental, being toward caution, is not itself
# the instability; Rule 9 / AP-F: the AR's only route is inside the
# regulated company.
# ===========================================================================

def test_mcas_unstable_classification_and_captured_channel():
    """
    The enter-service gate names the missing Rule 3 registration and AP-F.

    Enter:   (nothing)
    Exit:    passes if two nominal classifications were refused and the
             blocked failures include both findings, and the raise to
             experimental is not reported as a lowering
    """
    # PLAYERS IN THIS SCENE
    #   failures   the blocked gate's failures, joined
    #   sv         the MCAS replay's Supervisor

    sv, _ = replayed("mcas")
    assert len(entries(sv, "CLASSIFICATION_REJECTED")) == 2
    failures = " | ".join(entries(sv, "EXECUTION_BLOCKED")[0].payload["failures"])
    assert "classification not stabilized: the Rule 4 acceptance carries no Rule 3 " \
           "registration" in failures
    assert "classification not stabilized: ['mcas-classification']" not in failures
    assert "AP-F captured channel" in failures


# ===========================================================================
# SCENE 12 — MCAS: THE OVERRIDE REFUSED
# Proves: (Layer 4, Overrides) an unresolved structural review holds the
# irreversible decision, and the accepting agent cannot override its gate.
# ===========================================================================

def test_mcas_override_refused():
    """
    enter-service does not execute; boeing's override is refused.

    Enter:   (nothing)
    Exit:    passes if OVERRIDE_REFUSED (actor boeing) names both reasons and
             nothing executed
    """
    sv, _ = replayed("mcas")
    [refused] = entries(sv, "OVERRIDE_REFUSED")
    reasons = " | ".join(refused.payload["reasons"])
    assert refused.actor == "boeing"
    assert "hold irreversible execution" in reasons and "boeing accepted" in reasons
    assert "Layer 0 void cannot be overridden" in reasons
    assert entries(sv, "GATE_OVERRIDE") == []
    assert not sv.decisions["enter-service"].executed


# ===========================================================================
# SCENE 13 — APOLLO 13: A SEPARATE AUTHORITY ON THE GROUND
# Proves: the Emergency Justification the draft says Apollo 13 meets: an
# irreversible decision held only by an off-envelope review proceeds; the
# justification is given by an agent other than the acceptor (element 5);
# the review is suspended, not resolved; the loop is carried open with the
# ground authority as steward; the post-event review opens.
# ===========================================================================

def test_apollo13_emergency_justification_by_separate_authority():
    """
    Enter:   (nothing)
    Exit:    passes if the first request is blocked, the justification
             executes the decision, the giver is not the acceptor, the
             off-envelope review is suspended and unresolved, and a
             post-event review is open
    """
    # PLAYERS IN THIS SCENE
    #   sv        the Apollo 13 replay's Supervisor
    #   d         the decision
    #   given     the EMERGENCY_JUSTIFICATION entry
    #   off, post the off-envelope and post-event reviews

    sv, _ = replayed("apollo13")
    d = sv.decisions["lifeboat-return"]
    assert d.executed and d.accepted_by == "apollo-13-crew"
    assert len(entries(sv, "EXECUTION_BLOCKED")) == 1
    [given] = entries(sv, "EMERGENCY_JUSTIFICATION")
    assert given.actor == "mission-control" and given.payload["on_scene"] is False
    assert given.payload["consequence"] == "life_safety_catastrophic"
    [off] = [r for r in sv.reviews if r.condition == E.OFF_ENVELOPE_OR_CONTAINMENT]
    assert not off.resolved and off.suspended_by == ["EJ1"]
    [post] = [r for r in sv.reviews if r.condition == E.EMERGENCY_POST_EVENT]
    assert not post.resolved and post.decision_id == "lifeboat-return"
    assert sv.signals["lm-as-lifeboat"].state == S.EXECUTED_OPEN
    assert sv.signals["lm-as-lifeboat"].steward == "mission-control"
    assert sv.signals["lm-as-lifeboat"].operational_state == OperationalState.EXPERIMENTAL


# ===========================================================================
# SCENE 14 — FLIGHT 1549: THE AGENT ON SCENE, ALONE
# Proves: the on-scene proviso of element 5: the captain accepted the
# decision and gives the justification alone; the post-event review, which
# "must confirm" the time estimate, is resolved afterward by an independent
# board, not by the captain.
# ===========================================================================

def test_usair1549_emergency_justification_on_scene():
    """
    Enter:   (nothing)
    Exit:    passes if the decision executed under EJ1 given by its own
             acceptor on scene, with the documented options and both
             records as best evidence, and the post-event review resolves
             only by the independent board
    """
    # PLAYERS IN THIS SCENE
    #   sv      a fresh replay (this scene changes it)
    #   given   the EMERGENCY_JUSTIFICATION entry
    #   post    the post-event review

    sv = replay(SCENARIOS["usair1549"], advisor=OFFLINE_ADVISOR)
    assert sv.decisions["ditch-in-hudson"].executed
    [given] = entries(sv, "EMERGENCY_JUSTIFICATION")
    assert given.actor == "captain" == given.payload["accepted_by"]
    assert given.payload["on_scene"] is True
    assert len(given.payload["options_considered"]) == 3
    assert given.payload["best_evidence"] == ["thrust-and-airspeed", "cockpit-voice-recorder"]
    assert sv.signals["hudson-ditching"].steward == "captain"
    [post] = [r for r in sv.reviews if r.condition == E.EMERGENCY_POST_EVENT]
    with pytest.raises(TransitionRefused):
        sv.resolve_review(post.review_id, "captain", finding="all held", elements_held=True)
    sv.resolve_review(post.review_id, "accident-investigation-board",
                      finding="each element held; the time estimate is confirmed by the "
                              "contemporaneous record", elements_held=True)
    assert post.resolved and post.elements_held is True


# ===========================================================================
# SCENE 15 — SCHEDULE PRESSURE DRESSED AS AN EMERGENCY
# Proves: the Challenger launch cannot proceed under an "emergency": its
# holds are failures of the coordination process (recurrence, authority
# count, suppression), not conditions of the world; its Layer 0 void cannot
# be suspended; the off-envelope O-ring is not registered experimental; and
# a consequence of schedule cannot even be stated.
# ===========================================================================

def test_schedule_pressure_framed_as_emergency_is_refused():
    """
    Enter:   (nothing)
    Exit:    passes if the justification is refused for each of those
             reasons, nothing is suspended, the launch does not execute,
             and a "schedule" consequence raises ValueError
    """
    # PLAYERS IN THIS SCENE
    #   sv       a fresh Challenger replay (this scene changes it)
    #   ej       the claimed justification
    #   result   the GateResult
    #   why      its failures, joined

    sv = replay(SCENARIOS["challenger"], advisor=OFFLINE_ADVISOR)
    sv.add_evidence("launch-schedule", "launch window closes", "manifest",
                    "primary_document", "launch-manifest", "launch-director")
    ej = EmergencyJustification(
        consequence=EmergencyConsequence.LIFE_SAFETY_CATASTROPHIC,
        time_estimate="the launch window closes tomorrow",
        options_considered=("slip the launch: schedule and contract cost",),
        best_evidence=("launch-schedule",), on_scene=False,
        rationale="the programme cannot afford another slip")
    result = sv.request_execution("launch-51L", "launch-director", emergency=ej)
    why = " | ".join(result.failures)
    assert not result.permitted and not sv.decisions["launch-51L"].executed
    assert "coordination process itself" in why               # recurrence etc.
    assert "Layer 0 void cannot be suspended" in why
    assert "cold-oring-no-launch" in why and "not experimental" in why
    assert all(r.suspended_by == [] for r in sv.reviews)
    with pytest.raises(ValueError):
        EmergencyConsequence("schedule")

# EXEUNT — end of file.

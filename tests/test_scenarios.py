"""
THREE HISTORIES, REPLAYED
A Play in Twelve Scenes
=========================

PROLOGUE
--------
Tests for the replayable case histories in scenarios/ (Challenger,
Therac-25, Boeing 737 MAX MCAS), each run end to end through
cclf.graph.replay(). The expected outcomes come from what CCL-F v0.2 says
about each case:

  Challenger: seven missions of O-ring erosion closed by authority, "The
    escalation threshold was crossed after the third occurrence" (Rule 7,
    line 412); classified nominal "despite O-ring temperatures below
    anything in the validated test data" (Rule 2, line 312); the framing
    signal inverted the burden of proof (line 292); the launch was an
    irreversible decision with open constraint loops (lock-in closure,
    line 1216).
  Therac-25: six overdoses "before the incidents were connected" (Rule 7);
    the only legally obligated reporter was the manufacturer (AP.6 /
    AP-F captured channel, lines 211-217, 257).
  MCAS: classified a "minor stability enhancement" (Rule 2); behaved
    differently in different internal documents, never stabilized (Rule 3);
    the AR's standing subordinated to the regulated company (Rule 9).

Every replay must leave an intact audit chain (line 1000).

THE PLAYBILL
    Scene 1   replayed()                         (helper) replay a scenario
              refused_closures()                 (helper) which closures were refused
    Scene 2   test_every_scenario_replays_with_intact_chain   (parametrized, 3 runs)
    Scene 3   test_challenger_waivers_refused_after_threshold
    Scene 4   test_challenger_nominal_classification_refused
    Scene 5   test_challenger_framing_suppresses_uncertainty
    Scene 6   test_challenger_launch_blocked_then_overridden
    Scene 7   test_challenger_open_constraints_are_not_latched  (impl. decision)
    Scene 8   test_scenario_authority_counts_escalate         (was a spec mismatch, now fixed;
                                                                parametrized, 2 runs)
    Scene 9   test_therac25_closures_refused_after_threshold
    Scene 10  test_therac25_captured_channel_blocks_execution
    Scene 11  test_mcas_unstable_classification_and_captured_channel
    Scene 12  test_mcas_override_is_open_loop_execution

READER'S NOTE — a module-level cache
    Replaying a scenario takes a moment (the graph is rebuilt each time).
    Several scenes look at the same replay, so replayed() keeps results in
    the module-level dict _CACHE and replays each scenario only once. The
    tests only READ the cached supervisors, never change them.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       parametrize, xfail.
# cclf         Advisor, AuditTrail, CommitmentState, EscalationCondition,
#              OperationalState, replay.
# scenarios    SCENARIOS: name -> list of events.
# stagehands   entries.
# ===========================================================================

import pytest

from cclf import (
    Advisor, AuditTrail, CommitmentState, EscalationCondition, OperationalState, replay,
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
# chain (line 1000). (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_scenario_replays_with_intact_chain(name):
    """
    Each scenario's audit trail verifies and has one outcome per event.

    Enter:   name   each scenario name
    Exit:    passes if verify() is (True, "ok") and every event was processed
    """
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
    sv, _ = replayed("challenger")
    assert len(entries(sv, "CLASSIFICATION_REJECTED")) == 6
    assert all(s.operational_state != OperationalState.NOMINAL for s in sv.signals.values())
    assert sv.signals["cold-oring-no-launch"].operational_state == OperationalState.OFF_ENVELOPE


# ===========================================================================
# SCENE 5 — CHALLENGER: "PROVE IT'S UNSAFE"
# Proves: line 1212: frame adoption closes the frame by authority and
# suppresses the displaced uncertainty; the suppression escalates at the
# execution request (line 517).
# ===========================================================================

def test_challenger_framing_suppresses_uncertainty():
    """
    The burden-of-proof frame is closed_authority and seal-uncertainty suppressed.

    Enter:   (nothing)
    Exit:    passes if both states hold and SUPPRESSED_BEFORE_EXECUTION was raised
    """
    sv, _ = replayed("challenger")
    assert sv.signals["burden-of-proof-frame"].state == S.CLOSED_AUTHORITY
    assert sv.signals["seal-uncertainty"].state == S.SUPPRESSED
    assert any(r.condition == E.SUPPRESSED_BEFORE_EXECUTION for r in sv.reviews)


# ===========================================================================
# SCENE 6 — CHALLENGER: THE GATE, THEN THE OVERRIDE
# Proves: the launch gate is blocked (open constraints, unreviewed
# recurrence, Layer 0 stewardship void), and then proceeds only through a
# logged override by the accepting agent.
# ===========================================================================

def test_challenger_launch_blocked_then_overridden():
    """
    EXECUTION_BLOCKED, then GATE_OVERRIDE by kilminster; the launch executes.

    Enter:   (nothing)
    Exit:    passes if the blocked entry precedes the override, the blocked
             failures include open constraints, unreviewed recurrence and
             AP-A, the override names kilminster with a rationale, and
             the decision is executed
    """
    # PLAYERS IN THIS SCENE
    #   events     the audit event names in order
    #   blocked    the EXECUTION_BLOCKED entry
    #   override   the GATE_OVERRIDE entry

    sv, _ = replayed("challenger")
    events = sv.audit.events()
    assert events.index("EXECUTION_BLOCKED") < events.index("GATE_OVERRIDE")
    [blocked] = entries(sv, "EXECUTION_BLOCKED")
    failures = " | ".join(blocked.payload["failures"])
    for needle in ("open constraint loops", "recurrence groups not reviewed", "AP-A"):
        assert needle in failures
    assert blocked.payload["architecture_void"] is True
    [override] = entries(sv, "GATE_OVERRIDE")
    assert override.actor == "kilminster" and override.payload["rationale"]
    assert sv.decisions["launch-51L"].executed
    assert "OPEN_LOOP_IRREVERSIBLE_EXECUTION" in events


# ===========================================================================
# SCENE 7 — CHALLENGER: WHAT THE LOCK DOES NOT CATCH
# Proves (implementation decision): at the override every open constraint
# is ESCALATED, not under_review, so none is latched into trajectory_lock;
# the lock-in escalation still lists them as still open.
# ===========================================================================

def test_challenger_open_constraints_are_not_latched():
    """
    Implementation-decision test. The spec's state machine records lock-in
    as under_review -> trajectory_lock (line 946) and lists no
    escalated -> trajectory_lock transition, yet calls trajectory_lock "a
    permanent marker that the loop remained open at the point irreversible
    execution proceeded". The code latches only signals under review, so in
    the Challenger replay no signal reaches trajectory_lock; the five open
    constraints appear only in the LOCK_IN_WITH_OPEN_CONSTRAINTS detail.

    Enter:   (nothing)
    Exit:    passes if nothing is trajectory_lock, the open-loop execution
             entry has locked == [] and still_open naming the five
             constraints, and the lock-in escalation was raised
    """
    # PLAYERS IN THIS SCENE
    #   olie   the OPEN_LOOP_IRREVERSIBLE_EXECUTION entry

    sv, _ = replayed("challenger")
    assert not any(s.state == S.TRAJECTORY_LOCK for s in sv.signals.values())
    [olie] = entries(sv, "OPEN_LOOP_IRREVERSIBLE_EXECUTION")
    assert olie.payload["locked"] == []
    assert sorted(olie.payload["still_open"]) == sorted(FRR_LATE + ["cold-oring-no-launch"])
    assert any(r.condition == E.LOCK_IN_WITH_OPEN_CONSTRAINTS for r in sv.reviews)


# ===========================================================================
# SCENE 8 — THE OVERRIDES NOBODY COUNTED
# Proves: both Challenger (three authority closures)
# and MCAS (two) cross the authority-closure threshold on an irreversible
# decision (line 514). (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("name", ["challenger", "mcas"])
def test_scenario_authority_counts_escalate(name):
    """
    The authority-closure-count escalation is raised in the replay.

    Enter:   name   "challenger" or "mcas"
    Exit:    passes if an AUTHORITY_CLOSURE_COUNT review exists
    """
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

    sv, _ = replayed("therac25")
    [blocked] = entries(sv, "EXECUTION_BLOCKED")
    assert blocked.payload["architecture_void"] is True
    assert any(f.startswith("AP-F captured channel") for f in blocked.payload["failures"])
    assert entries(sv, "GATE_OVERRIDE") == [] and entries(sv, "EXECUTION_PERMITTED") == []
    assert not sv.decisions["continue-treatment"].executed


# ===========================================================================
# SCENE 11 — MCAS: NEVER STABILIZED, CAPTURED REPORTER
# Proves: Rules 2-3: the nominal classifications are refused and the MCAS
# classification is reclassified during review (unstable); Rule 9 / AP-F:
# the AR's only route is inside the regulated company.
# ===========================================================================

def test_mcas_unstable_classification_and_captured_channel():
    """
    The enter-service gate names the unstable classification and AP-F.

    Enter:   (nothing)
    Exit:    passes if two nominal classifications were refused and the
             blocked failures include both findings
    """
    # PLAYERS IN THIS SCENE
    #   failures   the blocked gate's failures, joined

    sv, _ = replayed("mcas")
    assert len(entries(sv, "CLASSIFICATION_REJECTED")) == 2
    failures = " | ".join(entries(sv, "EXECUTION_BLOCKED")[0].payload["failures"])
    assert "classification not stabilized: ['mcas-classification']" in failures
    assert "AP-F captured channel" in failures


# ===========================================================================
# SCENE 12 — MCAS: INTO SERVICE ON AN OVERRIDE
# Proves: line 1236: proceeding is permitted only with explicit, permanently
# logged authorization.
# ===========================================================================

def test_mcas_override_is_open_loop_execution():
    """
    enter-service executes only through a logged override by boeing.

    Enter:   (nothing)
    Exit:    passes if GATE_OVERRIDE (actor boeing) and
             OPEN_LOOP_IRREVERSIBLE_EXECUTION are logged and it executed
    """
    sv, _ = replayed("mcas")
    assert [e.actor for e in entries(sv, "GATE_OVERRIDE")] == ["boeing"]
    assert len(entries(sv, "OPEN_LOOP_IRREVERSIBLE_EXECUTION")) == 1
    assert sv.decisions["enter-service"].executed

# EXEUNT — end of file.

"""
THE GATE DESIGN
A Play in Thirty-Seven Scenes
=============================

PROLOGUE
--------
Acceptance tests for the October 2026 execution-gate design decisions in
the CCL-F v0.2 draft. They were written from the specification text alone
(the Closure Chain subsection, Reversibility Logic, the Execution Gates
table and its operational definitions, the EES and Evidence Novelty
definitions, the Closure Chain Key Definition and the changelog entry),
not from the implementation. Each scene quotes, or closely paraphrases,
the spec sentence it proves.

The decisions under test, in the changelog's own words:
  1. "every constraint loop must be closed by evidence, or proceed under
     logged open-loop authorization" (and anomaly loops alongside them);
  2. "aggregation across a decision's loops is by type" — weakest link for
     constraint and anomaly loops, the minimum evidence closure ratio for
     uncertainty, dissent, classification and framing loops;
  3. irreversible execution requires "at least one External Evidence
     Source for the principal risk claim", cited in the Rule 4 acceptance
     (revised October 2026: evidence in the loops' closures no longer
     substitutes);
  4. Closure Chain: an evidence closure is chain-sound "only if every item
     of evidence it cites has every upstream loop itself resolved ... all
     the way up" (revised October 2026 from "at least one item").

How to read a scene's verdict: GateResult.failures is a list of strings.
Each gate requirement has its own message prefix (see DRAMATIS PERSONAE).
A scene that proves a requirement FAILS checks that its prefix is present;
a scene that proves a requirement is MET checks that its prefix is absent.
The scenes do not require the whole gate to pass, so that an unrelated
requirement (for example the coherence score) cannot make a scene fail.

THE PLAYBILL
    Scenes 1-4    helpers: failures_with(), close_by_evidence(),
                  close_by_authority(), close_by_role_switch()
    Scenes 5-10   constraint and anomaly loops: weakest link
    Scenes 11-17  the other loop types: the minimum evidence closure ratio
    Scenes 16     no other-type signals; an open one counts against the ratio
                  and is "left open"; which exits close one (four tests)
    Scenes 18-20  exits: only a supersession shown by an EES resolves a
                  constraint
    Scenes 21-26  the principal risk claim and its External Evidence Source;
                  the acceptor's own evidence resolves nothing for them
    Scenes 27-35  the Closure Chain (31: every cited item is load-bearing,
                  three tests; 31b: superseded upstream; 34b: late
                  dependency)
    Scene 36      overrides still work
    Scene 37      outside the irreversible gate: the coherence score

READER'S NOTE — pytest.mark.parametrize
    `@pytest.mark.parametrize("name", [a, b, c])` runs the same test once
    per value, passing each value in as the argument `name`. pytest reports
    each run as its own test, e.g. test_x[TERMINAL], so a failure names the
    exact value that broke.

READER'S NOTE — pytest.raises
    `with pytest.raises(SomeError):` passes only if the indented block
    raises SomeError (or a subclass). Code after the raising line inside
    the block never runs, so the follow-up checks sit outside it.

READER'S NOTE — Evidence Novelty in these tests
    Evidence counts as novel for a signal only if it was added after the
    signal was registered. Every scene registers its signals first and adds
    evidence afterwards, so novelty is never the reason a closure fails
    unless a scene says so.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       the test runner; parametrize and raises (see READER'S NOTEs)
# cclf         the runtime under test. From it we use:
#   ClosureType       evidence / authority / role-switch / lock-in closure
#   CommitmentState   lifecycle states such as CLOSED_EVIDENCE
#   EvidenceKind      what kind of process produced an item of evidence
#   ExecutionClass    irreversible / elevated / routine
#   ExitType          the fourteen loop exit types
#   OperationalState  the five operational states (Rule 2)
#   Settings          domain-configured thresholds (ratio, coherence, ...)
#   SignalType        the six signal types (Rule 1)
#   Supervisor        the Layer 4 supervisor that owns all state
#   TransitionRefused the error raised when the runtime refuses a move
# stagehands   shared set-up helpers (see tests/stagehands.py)
# ===========================================================================

import pytest

from cclf import (
    ClosureType, CommitmentState, EvidenceKind, ExecutionClass, ExitType, OperationalState,
    Settings, SignalType, Supervisor, TransitionRefused,
)
from stagehands import (
    CUST, INDEPENDENT_LAB, PROCESS, RULE3, TECH, add_ees, add_non_ees, attest, decision,
    entries, to_review,
)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# CONSTRAINT_MSG — prefix of the irreversible-gate failure for constraint or
#   anomaly loops that are not evidence-closed (from the API notes).
CONSTRAINT_MSG = "constraint/anomaly loops not evidence-closed"

# RATIO_MSG — prefix of the failure for the minimum evidence closure ratio
#   (which now covers uncertainty, dissent, classification, framing only).
RATIO_MSG = "evidence closure ratio "

# EES_MSG — the failure when the Rule 4 acceptance names a principal risk
#   claim but cites no External Evidence Source for it (October 2026).
EES_MSG = "no External Evidence Source for the principal risk claim"

# RISK_MSG — the failure when the Rule 4 acceptance names no principal risk
#   claim at all.
RISK_MSG = "no principal risk claim named in the Rule 4 acceptance"

# OPEN_MSG — prefix of the failure when a loop of the other types is left
#   open ("none left open").
OPEN_MSG = "other loops left open"

# NEW_MSGS — the gate-design prefixes, for the override scene's check that a
#   decision fails only these requirements.
NEW_MSGS = (CONSTRAINT_MSG, RATIO_MSG, EES_MSG, RISK_MSG, OPEN_MSG)

# RISK — a principal risk claim and Rule 3 registration, as accept_decision
#   keywords, for scenes that accept by hand.
RISK = dict(risk_claim="the joint seals at launch temperature", **RULE3)

# REVIEWER — an agent who is neither the registrant ("engineer") nor the
#   evaluated process, so a closure by them with no EES is an authority closure.
REVIEWER = "reviewer"

# DIRECTOR — the agent stagehands.decision() uses to register and accept.
DIRECTOR = "director"

# OTHER_TYPES — the "remaining loop types" held to the ratio. FRAMING is
#   left out of the closure scenes: its authority closure goes through the
#   separate frame-adoption route (adopt_frame), so a plain attempt_closure
#   is not a fair way to stage it.
OTHER_TYPES = [SignalType.UNCERTAINTY, SignalType.DISSENT, SignalType.CLASSIFICATION]

# CLOSED_EXITS — exit types whose Loop State After is closed. They close a
#   loop of the other types; of them, only a superseded exit with an
#   External Evidence Source resolves a constraint or anomaly loop.
CLOSED_EXITS = [ExitType.TERMINAL, ExitType.SUPERSEDED]

# OPEN_EXITS — exit types the spec names as Loop State After open, plus
#   TIMEOUT (not in the spec's open list, but not in the closed list either).
OPEN_EXITS = [
    ExitType.CONTAINMENT, ExitType.RECOVERABLE, ExitType.DELEGATED, ExitType.DEFERRED,
    ExitType.FORCED, ExitType.EXHAUSTION, ExitType.BOUNDARY, ExitType.AMBIGUITY,
    ExitType.KEY_PERSON, ExitType.TIMEOUT,
]


# ===========================================================================
# SCENE 1 — READING THE VERDICT
# Which gate failures start with a given prefix?
# ===========================================================================

def failures_with(result, prefix):
    """
    Return the failure strings of a GateResult that start with `prefix`.

    Enter:   result   a GateResult from request_execution
             prefix   one of the message prefixes in DRAMATIS PERSONAE
    Exit:    a list of matching strings (empty when the requirement is met)
    """
    return [f for f in result.failures if f.startswith(prefix)]


# ===========================================================================
# SCENE 2 — CLOSING WITH OUTSIDE EVIDENCE
# Close a signal by evidence closure, optionally with upstream loops.
# ===========================================================================

def close_by_evidence(sv, signal_id, evidence_id, depends_on=()):
    """
    Add one EES item (from INDEPENDENT_LAB) and close the signal citing it.

    Enter:   sv            the Supervisor
             signal_id     a signal under review
             evidence_id   ID for the new evidence
             depends_on    upstream loop IDs the evidence depends on
    Exit:    the ClosureRecord. The evidence is novel (added after the
             signal was registered) and EES (an eligible kind, produced by
             neither PROCESS nor the registrant), so the closure is an
             evidence closure; whether it is chain-sound depends on
             `depends_on`.
    """
    sv.add_evidence(evidence_id, f"evidence {evidence_id}", "test",
                    EvidenceKind.DIRECT_MEASUREMENT, INDEPENDENT_LAB, "evidence-clerk",
                    signal_ids=(signal_id,), depends_on=depends_on)
    return sv.attempt_closure(signal_id, REVIEWER, TECH, [evidence_id], "measured")


# ===========================================================================
# SCENE 3 — CLOSING BY SAY-SO
# Close a signal by authority: a non-registrant, no evidence.
# ===========================================================================

def close_by_authority(sv, signal_id):
    """
    Close a signal with no evidence, by REVIEWER: an authority closure.

    Enter:   sv, signal_id   the Supervisor and a signal under review
    Exit:    the ClosureRecord (closure type AUTHORITY)
    """
    return sv.attempt_closure(signal_id, REVIEWER, TECH, [], "I say it is fine")


# ===========================================================================
# SCENE 4 — CHANGING HATS
# Close a signal by role switch: the registrant, consulting the other referent.
# ===========================================================================

def close_by_role_switch(sv, signal_id):
    """
    Close a signal with no evidence, by its registrant using the customer referent.

    Enter:   sv, signal_id   the Supervisor and a signal registered by
                             "engineer" under the technical referent
    Exit:    the ClosureRecord (closure type ROLE_SWITCH)
    """
    return sv.attempt_closure(signal_id, "engineer", CUST, [], "the customer view says ok")


# ===========================================================================
# SCENE 5 — ONE WEAK LINK BREAKS THE CHAIN
# Proves: an authority-closed constraint fails the irreversible gate even
# when another constraint is evidence-closed.
# ===========================================================================

def test_authority_closed_constraint_fails_despite_evidence_closed_sibling():
    """
    Spec: "A constraint or anomaly loop closed by authority or role switch is
    not resolved for this purpose, however final its closure looks" and
    "Weakest link applies: one loop that fails this test fails the gate,
    whatever the others show."

    Setting the stage: two constraints; one evidence-closed, one closed by
    authority. The action: request irreversible execution. The verdict: the
    constraint failure is present and names the authority-closed loop only.
    """
    # PLAYERS IN THIS SCENE
    #   sv       the Supervisor
    #   result   the GateResult
    #   msgs     the constraint/anomaly failure strings
    sv = Supervisor()
    to_review(sv, "c-ev")
    to_review(sv, "c-auth")
    close_by_evidence(sv, "c-ev", "e1")
    close_by_authority(sv, "c-auth")
    decision(sv, "d1", ["c-ev", "c-auth"])
    result = sv.request_execution("d1", DIRECTOR)
    msgs = failures_with(result, CONSTRAINT_MSG)
    assert not result.permitted
    assert len(msgs) == 1
    assert "c-auth" in msgs[0]
    assert "c-ev" not in msgs[0]


# ===========================================================================
# SCENE 6 — THE ANOMALY IS HELD TO THE SAME STANDARD
# Proves: an authority-closed anomaly fails the irreversible gate too.
# ===========================================================================

def test_authority_closed_anomaly_fails_despite_evidence_closed_sibling():
    """
    Spec: "Irreversible decisions require evidence-based closure for all
    constraint and anomaly loops" — "every constraint and anomaly signal the
    decision depends on is closed by a chain-sound evidence closure".

    Setting the stage: two anomalies; one evidence-closed, one closed by
    authority. The verdict: the failure names only the authority-closed one.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result, msgs   as in Scene 5
    sv = Supervisor()
    to_review(sv, "a-ev", SignalType.ANOMALY)
    to_review(sv, "a-auth", SignalType.ANOMALY)
    close_by_evidence(sv, "a-ev", "e1")
    close_by_authority(sv, "a-auth")
    decision(sv, "d1", ["a-ev", "a-auth"])
    result = sv.request_execution("d1", DIRECTOR)
    msgs = failures_with(result, CONSTRAINT_MSG)
    assert not result.permitted
    assert len(msgs) == 1
    assert "a-auth" in msgs[0]
    assert "a-ev" not in msgs[0]


# ===========================================================================
# SCENE 7 — A CHANGE OF HATS IS NOT EVIDENCE
# Proves: a role-switch-closed constraint fails the irreversible gate.
# ===========================================================================

def test_role_switch_closed_constraint_fails():
    """
    Spec: "A constraint or anomaly loop closed by authority or role switch is
    not resolved for this purpose".

    Setting the stage: one constraint closed by its registrant consulting the
    customer referent. The verdict: the constraint failure names it.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result, msgs   as in Scene 5
    #   rec                the role-switch closure record
    sv = Supervisor()
    to_review(sv, "c1")
    rec = close_by_role_switch(sv, "c1")
    # --- Make sure the stage is what we think it is -------------------------
    assert rec.closure_type is ClosureType.ROLE_SWITCH
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    msgs = failures_with(result, CONSTRAINT_MSG)
    assert not result.permitted
    assert len(msgs) == 1 and "c1" in msgs[0]


# ===========================================================================
# SCENE 8 — A ROLE-SWITCH ANOMALY
# Proves: a role-switch-closed anomaly also fails.
# ===========================================================================

def test_role_switch_closed_anomaly_fails():
    """
    Spec: "A constraint or anomaly loop closed by authority or role switch is
    not resolved for this purpose".
    """
    # PLAYERS IN THIS SCENE
    #   sv, result, msgs   as in Scene 5
    sv = Supervisor()
    to_review(sv, "a1", SignalType.ANOMALY)
    close_by_role_switch(sv, "a1")
    decision(sv, "d1", ["a1"])
    result = sv.request_execution("d1", DIRECTOR)
    msgs = failures_with(result, CONSTRAINT_MSG)
    assert len(msgs) == 1 and "a1" in msgs[0]


# ===========================================================================
# SCENE 9 — AN OPEN LOOP
# Proves: a constraint still under review fails the requirement.
# ===========================================================================

def test_open_constraint_fails():
    """
    Spec: "A loop that is open, closed by authority or role switch, ...
    does not meet it."
    """
    # PLAYERS IN THIS SCENE
    #   sv, result, msgs   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    msgs = failures_with(result, CONSTRAINT_MSG)
    assert len(msgs) == 1 and "c1" in msgs[0]


# ===========================================================================
# SCENE 10 — EVERY LINK HOLDS
# Proves: evidence-closed constraint and anomaly loops meet the requirement.
# ===========================================================================

def test_all_constraint_and_anomaly_loops_evidence_closed_meet_requirement():
    """
    Spec: "every constraint and anomaly signal the decision depends on is
    closed by a chain-sound evidence closure" — the requirement is met.

    Setting the stage: one constraint and one anomaly, both evidence-closed
    with independent evidence and no upstream loops. The verdict: neither the
    constraint failure nor the EES failure appears.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    to_review(sv, "a1", SignalType.ANOMALY)
    close_by_evidence(sv, "c1", "e1")
    close_by_evidence(sv, "a1", "e2")
    decision(sv, "d1", ["c1", "a1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, CONSTRAINT_MSG) == []
    assert failures_with(result, EES_MSG) == []


# ===========================================================================
# SCENE 11 — A BUDGET, NOT A LIST
# Proves: one authority-closed "other" loop among enough evidence closures
# meets the ratio and does not trip the weakest-link rule.
# ===========================================================================

@pytest.mark.parametrize("weak_type", OTHER_TYPES, ids=lambda t: t.name)
def test_one_authority_closed_other_loop_passes_the_ratio(weak_type):
    """
    Spec (Reversibility Logic): "The remaining loop types — uncertainty,
    dissent, classification, framing — may be closed by any closure type,
    but enough of them by evidence to meet a minimum evidence closure
    ratio" and (Execution Gates) "These loop types are closer to a budget
    than to a list of distinct failure modes, so a ratio is the right test
    of how they were closed."

    Setting the stage: one loop of `weak_type` closed by authority, two
    uncertainty loops evidence-closed: 2 of 3 is at least the default 0.5.
    The verdict: no ratio failure, and no constraint/anomaly failure either.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "weak", weak_type)
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    to_review(sv, "u2", SignalType.UNCERTAINTY)
    close_by_authority(sv, "weak")
    close_by_evidence(sv, "u1", "e1")
    close_by_evidence(sv, "u2", "e2")
    decision(sv, "d1", ["weak", "u1", "u2"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, RATIO_MSG) == []
    assert failures_with(result, CONSTRAINT_MSG) == []


# ===========================================================================
# SCENE 12 — OVER BUDGET
# Proves: below the ratio, the gate fails with the ratio message.
# ===========================================================================

def test_below_ratio_fails_with_ratio_message():
    """
    Spec: "among the decision's uncertainty, dissent, classification, and
    framing signals, the share closed by chain-sound evidence closure meets
    the domain-configured minimum (one half by default)".

    Setting the stage: two uncertainty loops closed by authority and one by
    evidence: 1 of 3 is below 0.5. The verdict: the ratio failure appears.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    #   sid          each uncertainty signal id
    sv = Supervisor()
    for sid in ("u1", "u2", "u3"):
        to_review(sv, sid, SignalType.UNCERTAINTY)
    close_by_authority(sv, "u1")
    close_by_authority(sv, "u2")
    close_by_evidence(sv, "u3", "e3")
    decision(sv, "d1", ["u1", "u2", "u3"])
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert len(failures_with(result, RATIO_MSG)) == 1


# ===========================================================================
# SCENE 13 — EXACTLY ON BUDGET
# Proves: a share equal to the minimum meets the requirement.
# ===========================================================================

def test_ratio_exactly_at_minimum_is_met():
    """
    Spec: "the share closed by chain-sound evidence closure meets the
    domain-configured minimum". Read literally, "meets" includes equality.

    Setting the stage: one authority and one evidence closure of uncertainty
    loops: 1 of 2 = 0.5, the default minimum. The verdict: no ratio failure.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    to_review(sv, "u2", SignalType.UNCERTAINTY)
    close_by_authority(sv, "u1")
    close_by_evidence(sv, "u2", "e2")
    decision(sv, "d1", ["u1", "u2"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, RATIO_MSG) == []


# ===========================================================================
# SCENE 14 — CONSTRAINTS DO NOT PAD THE BUDGET
# Proves: evidence closures of constraint/anomaly loops do not count
# toward the ratio.
# ===========================================================================

def test_constraint_and_anomaly_evidence_closures_do_not_count_toward_ratio():
    """
    Spec (changelog): "Uncertainty, dissent, classification, and framing loops
    are held to the minimum evidence closure ratio, which now applies to those
    types only."

    Setting the stage: a constraint and an anomaly evidence-closed, one
    uncertainty closed by authority. Counting every closure would give 2 of 3
    (passes); counting only the uncertainty gives 0 of 1. The verdict: the
    ratio failure appears.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    to_review(sv, "a1", SignalType.ANOMALY)
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    close_by_evidence(sv, "c1", "e1")
    close_by_evidence(sv, "a1", "e2")
    close_by_authority(sv, "u1")
    decision(sv, "d1", ["c1", "a1", "u1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert len(failures_with(result, RATIO_MSG)) == 1


# ===========================================================================
# SCENE 15 — CONSTRAINTS DO NOT DRAIN THE BUDGET EITHER
# Proves: an authority closure of a constraint does not lower the ratio.
# ===========================================================================

def test_constraint_authority_closure_does_not_count_against_ratio():
    """
    Spec (changelog): the ratio "now applies to those types only."

    Setting the stage: two constraints closed by authority, one uncertainty
    evidence-closed. Counting every closure gives 1 of 3 (fails); counting
    only the uncertainty gives 1 of 1. The verdict: no ratio failure (the
    constraint failure is expected and is not what this scene checks).
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    to_review(sv, "c2")
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    close_by_authority(sv, "c1")
    close_by_authority(sv, "c2")
    close_by_evidence(sv, "u1", "e1")
    decision(sv, "d1", ["c1", "c2", "u1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, RATIO_MSG) == []
    assert len(failures_with(result, CONSTRAINT_MSG)) == 1


# ===========================================================================
# SCENE 16 — NOTHING TO MEASURE, AND AN OPEN LOOP IS NOT NOTHING
# Proves: with no signals of the other loop types, the requirement is met;
# an uncertainty loop still under review counts against the ratio and is
# "left open".
# ===========================================================================

def test_no_other_type_signals_means_requirement_met():
    """
    Spec: "With no such signals, the requirement is met."

    Setting the stage: one evidence-closed constraint and nothing else.
    The verdict: neither the ratio nor the left-open failure.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    close_by_evidence(sv, "c1", "e1")
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, RATIO_MSG) == []
    assert failures_with(result, OPEN_MSG) == []


def test_open_other_loop_counts_against_ratio_and_is_left_open():
    """
    Spec: "A loop left open counts against the ratio, so leaving loops
    unclosed never improves it" and "none remains open: each is closed, by
    whatever closure type, or has exited as superseded."

    Setting the stage: "u1" evidence-closed; "u2" and "u3" still under
    review. Counting only closures would give 1 of 1; counting every signal
    gives 1 of 3. The verdict: the ratio failure (0.33) and the left-open
    failure naming u2 and u3.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    #   sid          each uncertainty signal id
    #   msgs         the left-open failure strings
    sv = Supervisor()
    for sid in ("u1", "u2", "u3"):
        to_review(sv, sid, SignalType.UNCERTAINTY)
    close_by_evidence(sv, "u1", "e1")
    decision(sv, "d1", ["u1", "u2", "u3"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, RATIO_MSG) == ["evidence closure ratio 0.33 below 0.50"]
    msgs = failures_with(result, OPEN_MSG)
    assert len(msgs) == 1 and "u2" in msgs[0] and "u3" in msgs[0] and "u1" not in msgs[0]


def test_ratio_met_but_one_loop_open_still_fails():
    """
    Spec: the ratio and "none left open" are separate conditions.

    Setting the stage: "u1" evidence-closed, "u2" under review: 1 of 2
    meets 0.5. The verdict: no ratio failure, but u2 is left open.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    to_review(sv, "u2", SignalType.UNCERTAINTY)
    close_by_evidence(sv, "u1", "e1")
    decision(sv, "d1", ["u1", "u2"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, RATIO_MSG) == []
    assert failures_with(result, OPEN_MSG) == ["other loops left open: ['u2']"]


@pytest.mark.parametrize("exit_type, closes", [
    (ExitType.TERMINAL, False), (ExitType.SUPERSEDED, True),
    (ExitType.TIMEOUT, False), (ExitType.DEFERRED, False), (ExitType.AMBIGUITY, False),
], ids=lambda v: v.name if isinstance(v, ExitType) else str(v))
def test_other_loop_exits_that_close_it(exit_type, closes):
    """
    Spec: "each is closed, by whatever closure type, or has exited as
    superseded. A loop exited as terminal counts as open for this test,
    since the exit records the loop's open state rather than resolving
    it." A terminal, timed-out, deferred or ambiguity exit leaves it open.

    Setting the stage: "u1" evidence-closed, "u2" exited by `exit_type`.
    The verdict: the left-open failure appears exactly when the exit does
    not close the loop.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    to_review(sv, "u2", SignalType.UNCERTAINTY)
    close_by_evidence(sv, "u1", "e1")
    sv.exit("u2", exit_type, "steward", "leaving", open_loop_state="noted")
    decision(sv, "d1", ["u1", "u2"])
    result = sv.request_execution("d1", DIRECTOR)
    assert (failures_with(result, OPEN_MSG) == []) is closes


# ===========================================================================
# SCENE 17 — A HOLLOW EVIDENCE CLOSURE IN THE BUDGET
# Proves: an evidence closure that is not chain-sound counts as a
# non-evidence closure in the ratio.
# ===========================================================================

def test_chain_unsound_evidence_closure_counts_as_non_evidence_in_ratio():
    """
    Spec: an evidence closure that is not chain-sound "counts as a
    non-evidence closure wherever closure quality matters: at the execution
    gates, in the evidence closure ratio, and in the coherence score."

    Setting the stage: upstream constraint "rig" closed by authority (it is
    not part of the decision). Uncertainty "u1" is evidence-closed with
    evidence that depends on "rig". The ratio is therefore 0 of 1.
    The verdict: the ratio failure appears.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "rig")
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    close_by_authority(sv, "rig")
    close_by_evidence(sv, "u1", "e1", depends_on=["rig"])
    decision(sv, "d1", ["u1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert len(failures_with(result, RATIO_MSG)) == 1


# ===========================================================================
# SCENE 18 — THE ONE EXIT THAT RESOLVES A CONSTRAINT
# Proves: a constraint superseded with an External Evidence Source meets
# the requirement; a terminal exit, or a supersession without such
# evidence, does not.
# ===========================================================================

@pytest.mark.parametrize("exit_type, evidence_by, meets", [
    (ExitType.SUPERSEDED, INDEPENDENT_LAB, True),   # supersession shown by an EES
    (ExitType.SUPERSEDED, None, False),             # no evidence cited
    (ExitType.SUPERSEDED, "steward", False),        # the exiting agent's own evidence
    (ExitType.TERMINAL, INDEPENDENT_LAB, False),    # terminal never resolves it
], ids=["superseded-ees", "superseded-bare", "superseded-own-evidence", "terminal"])
def test_constraint_exit_meets_requirement_only_superseded_with_ees(exit_type, evidence_by,
                                                                    meets):
    """
    Spec: "every constraint and anomaly signal the decision depends on is
    closed by a chain-sound evidence closure, or has exited as superseded
    with an External Evidence Source showing that the context that
    generated it no longer exists ... That includes the terminal, timeout,
    whistleblower, and legal exits: each ends a loop without resolving the
    hazard it named, and a terminal exit needs no evidence at all."

    Setting the stage: "c1" exits by `exit_type`, citing evidence produced
    by `evidence_by` (none if None); the exiting agent is "steward", the
    claimant. The verdict: the constraint failure is absent exactly when
    the exit is a supersession with an EES.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    #   cited        the evidence ids cited with the exit
    sv = Supervisor()
    to_review(sv, "c1")
    cited = []
    if evidence_by:
        add_ees(sv, "context-gone", produced_by=evidence_by)
        cited = ["context-gone"]
    sv.exit("c1", exit_type, "steward", "the context no longer exists",
            open_loop_state="no open work remains", evidence_ids=cited)
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert (failures_with(result, CONSTRAINT_MSG) == []) is meets


# ===========================================================================
# SCENE 19 — EXITS THAT LEAVE THE LOOP OPEN
# Proves: a constraint that exited by an open-state type, or by TIMEOUT,
# does not meet the requirement (nor does TERMINAL: Scene 18).
# ===========================================================================

@pytest.mark.parametrize("exit_type", OPEN_EXITS, ids=lambda t: t.name)
def test_constraint_exited_with_open_loop_state_fails(exit_type):
    """
    Spec: "A loop that is open, closed by authority or role switch,
    latched, closed by evidence that is not chain-sound, or exited by any
    other type does not meet it. That includes the terminal, timeout,
    whistleblower, and legal exits". Every exit but a supersession shown by
    an External Evidence Source fails, so each of these does.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result, msgs   as in Scene 5
    #   extra              keyword arguments some exit types require
    sv = Supervisor()
    to_review(sv, "c1")
    # --- Delegated exits must name the new steward --------------------------
    extra = {"successor": "new-steward"} if exit_type is ExitType.DELEGATED else {}
    sv.exit("c1", exit_type, "steward", "leaving the loop for now",
            open_loop_state="hazard still present", **extra)
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    msgs = failures_with(result, CONSTRAINT_MSG)
    assert len(msgs) == 1 and "c1" in msgs[0]


# ===========================================================================
# SCENE 20 — AN ANOMALY DEFERRED
# Proves: the exit rule applies to anomaly loops too.
# ===========================================================================

def test_anomaly_exited_deferred_fails():
    """
    Spec: "Constraint and anomaly loops evidence-closed" covers "every
    constraint and anomaly signal the decision depends on"; a deferred
    exit is not a supersession shown by an External Evidence Source.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result, msgs   as in Scene 5
    sv = Supervisor()
    to_review(sv, "a1", SignalType.ANOMALY)
    sv.exit("a1", ExitType.DEFERRED, "steward", "later", open_loop_state="open")
    decision(sv, "d1", ["a1"])
    result = sv.request_execution("d1", DIRECTOR)
    msgs = failures_with(result, CONSTRAINT_MSG)
    assert len(msgs) == 1 and "a1" in msgs[0]


# ===========================================================================
# SCENE 21 — NO CLAIM, NO CHECK
# Proves: an acceptance that names no principal risk claim fails the
# requirement, whatever else the decision has.
# ===========================================================================

def test_acceptance_without_risk_claim_fails():
    """
    Spec: "the Rule 4 acceptance names the decision's principal risk claim,
    what must be true for the decision to be safe to execute, and cites at
    least one External Evidence Source bearing on it".

    Setting the stage: an evidence-closed constraint; the acceptance cites
    an independent measurement but names no risk claim. The verdict: the
    risk-claim failure appears.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    close_by_evidence(sv, "c1", "e1")
    decision(sv, "d1", ["c1"], accept=False)
    add_ees(sv, "acc-ev")
    sv.accept_decision("d1", DIRECTOR, "accepted", evidence_ids=["acc-ev"], **RULE3)
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert failures_with(result, RISK_MSG) == [RISK_MSG]


# ===========================================================================
# SCENE 22 — THE LOOPS' EVIDENCE DOES NOT SUBSTITUTE
# Proves: EES evidence in the loops' closures does not meet the
# requirement; only the acceptance's own citation does.
# ===========================================================================

def test_closure_evidence_does_not_substitute_for_risk_claim_ees():
    """
    Spec: "Evidence elsewhere in the decision's support, in its loops'
    closures, does not substitute: it shows that individual loops were
    resolved, not that the risk the acceptor is taking on was checked by
    anything outside the process that proposed it."

    Setting the stage: two loops evidence-closed with independent lab
    evidence; the acceptance names a risk claim but cites nothing. The
    verdict: the EES failure appears, and the loops themselves pass.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    close_by_evidence(sv, "c1", "e1")
    close_by_evidence(sv, "u1", "e2")
    decision(sv, "d1", ["c1", "u1"], accept=False)
    sv.accept_decision("d1", DIRECTOR, "the loops are closed", **RISK)
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, EES_MSG) == [EES_MSG]
    assert failures_with(result, CONSTRAINT_MSG) == []
    assert failures_with(result, RATIO_MSG) == []


# ===========================================================================
# SCENE 23 — A WITNESS AT THE SIGNING
# Proves: an EES cited in the Rule 4 acceptance, with a named risk claim,
# meets the requirement.
# ===========================================================================

def test_ees_cited_in_acceptance_satisfies_requirement():
    """
    Spec: "the Rule 4 acceptance names the decision's principal risk claim
    ... and cites at least one External Evidence Source bearing on it".

    Setting the stage: an evidence-closed constraint; the director names
    the risk claim and cites an independent lab measurement. The verdict:
    neither failure, the decision executes, and the claim is recorded.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    close_by_evidence(sv, "c1", "e1")
    decision(sv, "d1", ["c1"], accept=False)
    add_ees(sv, "acc-ev")
    sv.accept_decision("d1", DIRECTOR, "accepted on the lab's measurement",
                       evidence_ids=["acc-ev"], **RISK)
    attest(sv, "d1")
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, EES_MSG) == []
    assert failures_with(result, RISK_MSG) == []
    assert result.permitted, result.failures
    assert sv.decisions["d1"].risk_claim == RISK["risk_claim"]
    assert entries(sv, "DECISION_ACCEPTED")[-1].payload["risk_claim"] == RISK["risk_claim"]


# ===========================================================================
# SCENE 24 — WITNESSES WHO DO NOT COUNT
# Proves: acceptance evidence produced by the accepting agent, by the
# process under evaluation, or of a non-eligible kind gives no EES.
# ===========================================================================

@pytest.mark.parametrize("kind, producer", [
    (EvidenceKind.DIRECT_MEASUREMENT, DIRECTOR),
    (EvidenceKind.DIRECT_MEASUREMENT, PROCESS),
    (EvidenceKind.MODEL_OUTPUT, INDEPENDENT_LAB),
    (EvidenceKind.ASSERTION, INDEPENDENT_LAB),
    (EvidenceKind.INTERNAL_ANALYSIS, INDEPENDENT_LAB),
], ids=["by-acceptor", "by-evaluated-process", "model-output", "assertion",
        "internal-analysis"])
def test_non_qualifying_acceptance_evidence_does_not_satisfy_ees(kind, producer):
    """
    Spec (Layer 2, EES): the producer is none of "the agent making the
    claim it is offered for (... the accepting agent, for a Rule 4
    acceptance); the agent accepting the decision it supports; or any
    process whose output the claim evaluates", and the kind is eligible.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    close_by_evidence(sv, "c1", "e1")
    decision(sv, "d1", ["c1"], accept=False)
    sv.add_evidence("acc-ev", "acceptance evidence", "test", kind, producer,
                    "evidence-clerk")
    sv.accept_decision("d1", DIRECTOR, "accepted", evidence_ids=["acc-ev"], **RISK)
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, EES_MSG) == [EES_MSG]


# ===========================================================================
# SCENE 25 — A PROCESS FROM ANOTHER OF THE DECISION'S LOOPS
# Proves: evidence produced by the evaluated process of any of the
# decision's loops is refused, not just the first loop's.
# ===========================================================================

def test_acceptance_evidence_from_another_loops_process_is_not_ees():
    """
    Spec: the producer is not "any process whose output the claim
    evaluates", and the risk claim is about the whole decision.

    Setting the stage: two constraints, the second about
    "second-process". The acceptance cites a measurement produced by
    "second-process". The verdict: the EES failure appears.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    # --- A loop about a different process, built by hand --------------------
    sv.register_signal("c2", SignalType.CONSTRAINT, "signal c2", "engineer", TECH,
                       "second-process", steward="steward", successor="successor")
    sv.classify("c2", OperationalState.ELEVATED_UNCERTAINTY, "engineer")
    sv.open_review("c2", "engineer")
    decision(sv, "d1", ["c1", "c2"], accept=False)
    add_ees(sv, "acc-ev", produced_by="second-process")
    sv.accept_decision("d1", DIRECTOR, "accepted", evidence_ids=["acc-ev"], **RISK)
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, EES_MSG) == [EES_MSG]


# ===========================================================================
# SCENE 26 — THE ACCEPTOR'S OWN MEASUREMENT CLOSES NOTHING FOR THEM
# Proves: a loop closed by evidence the accepting agent produced is not
# resolved for that agent's decision (Layer 2, EES: the producer is not
# "the agent accepting the decision it supports"); the same closure still
# stands as an evidence closure on its own.
# ===========================================================================

def test_closure_on_acceptor_evidence_is_not_resolved_for_that_decision():
    """
    Setting the stage: "c1" closed by REVIEWER citing a measurement that
    DIRECTOR produced. The closure is an evidence closure (REVIEWER is the
    claimant). The action: DIRECTOR accepts the decision over c1 and asks
    to execute. The verdict: the constraint failure names c1; chain_sound
    still reports the closure as sound outside the decision.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result, msgs   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    add_ees(sv, "director-reading", ["c1"], produced_by=DIRECTOR)
    rec = sv.attempt_closure("c1", REVIEWER, TECH, ["director-reading"], "measured")
    assert rec.closure_type is ClosureType.EVIDENCE
    assert sv.chain_sound("c1")
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    msgs = failures_with(result, CONSTRAINT_MSG)
    assert len(msgs) == 1 and "c1" in msgs[0]


# ===========================================================================
# SCENE 27 — THE UNCALIBRATED RIG
# Proves: evidence depending on an authority-closed upstream loop leaves
# the downstream closure recorded as evidence but not chain-sound, and the
# irreversible gate fails for the downstream constraint.
# ===========================================================================

def test_authority_closed_upstream_makes_downstream_not_chain_sound():
    """
    Spec: "if the loop that would have validated the instrument was closed by
    authority, the measurement inherits that closure's weakness" and "An
    evidence closure that is not chain-sound is recorded as an evidence
    closure, with the broken link shown in the record, but it counts as a
    non-evidence closure ... at the execution gates".
    """
    # PLAYERS IN THIS SCENE
    #   sv, result, msgs   as in Scene 5
    #   rec                the downstream closure record
    #   sig                the downstream Signal "c1"
    sv = Supervisor()
    to_review(sv, "rig")
    sig = to_review(sv, "c1")
    close_by_authority(sv, "rig")
    rec = close_by_evidence(sv, "c1", "e1", depends_on=["rig"])
    # --- Still recorded as an evidence closure ------------------------------
    assert rec.closure_type is ClosureType.EVIDENCE
    assert sig.state is CommitmentState.CLOSED_EVIDENCE
    # --- But it has no standing ---------------------------------------------
    assert sv.chain_sound("c1") is False
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    msgs = failures_with(result, CONSTRAINT_MSG)
    assert not result.permitted
    assert len(msgs) == 1 and "c1" in msgs[0]


# ===========================================================================
# SCENE 28 — THE RIG NOT YET CHECKED, THEN CHECKED
# Proves: an open upstream loop leaves the downstream closure unsound;
# soundness is assessed when needed, so closing the upstream by evidence
# later restores it.
# ===========================================================================

def test_open_upstream_then_evidence_closed_upstream():
    """
    Spec: "Chain soundness is assessed at the time it is needed, not fixed at
    closure: if an upstream loop ... was never evidence-closed, every
    closure downstream of it loses its standing".
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "rig")
    to_review(sv, "c1")
    close_by_evidence(sv, "c1", "e1", depends_on=["rig"])
    # --- Upstream still open: no standing -----------------------------------
    assert sv.chain_sound("c1") is False
    decision(sv, "d1", ["c1"])
    # --- Now validate the rig with independent evidence ---------------------
    close_by_evidence(sv, "rig", "e-rig")
    assert sv.chain_sound("c1") is True
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, CONSTRAINT_MSG) == []


# ===========================================================================
# SCENE 29 — A SOUND CHAIN
# Proves: with the upstream evidence-closed first, the downstream closure
# counts.
# ===========================================================================

def test_evidence_closed_upstream_makes_downstream_count():
    """
    Spec: "An evidence closure is chain-sound only if every item of
    evidence it cites has every upstream loop itself resolved — closed by
    chain-sound evidence closure, or exited as superseded with an External
    Evidence Source — all the way up."
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "rig")
    to_review(sv, "c1")
    close_by_evidence(sv, "rig", "e-rig")
    close_by_evidence(sv, "c1", "e1", depends_on=["rig"])
    assert sv.chain_sound("rig") is True
    assert sv.chain_sound("c1") is True
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, CONSTRAINT_MSG) == []
    assert failures_with(result, EES_MSG) == []


# ===========================================================================
# SCENE 30 — ALL THE WAY UP
# Proves: chain soundness is transitive over two levels, both ways.
# ===========================================================================

@pytest.mark.parametrize("top_by_evidence", [True, False], ids=["top-evidence",
                                                                "top-authority"])
def test_chain_soundness_is_transitive(top_by_evidence):
    """
    Spec: "has every upstream loop itself resolved — closed by chain-sound
    evidence closure ... — all the way up."

    Setting the stage: "top" <- "mid" <- "c1" (each one's closing evidence
    depends on the loop to its left). The verdict: "c1" is chain-sound only
    when "top" was evidence-closed; "mid" follows the same rule.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    #   sid  each signal id, put under review in turn
    sv = Supervisor()
    for sid in ("top", "mid", "c1"):
        to_review(sv, sid)
    if top_by_evidence:
        close_by_evidence(sv, "top", "e-top")
    else:
        close_by_authority(sv, "top")
    close_by_evidence(sv, "mid", "e-mid", depends_on=["top"])
    close_by_evidence(sv, "c1", "e1", depends_on=["mid"])
    assert sv.chain_sound("mid") is top_by_evidence
    assert sv.chain_sound("c1") is top_by_evidence


# ===========================================================================
# SCENE 31 — EVERY CITED ITEM IS LOAD-BEARING
# Proves: a closure cannot pass by pairing one clean item with another that
# rests on an unresolved loop, whatever the clean item's kind; a cited item
# that rests on nothing does no harm.
# ===========================================================================

@pytest.mark.parametrize("second_is_ees", [True, False], ids=["second-ees",
                                                              "second-model-output"])
def test_every_cited_item_is_load_bearing(second_is_ees):
    """
    Spec: "Citing an item is relying on it, so every cited item is
    load-bearing: a closure cannot pass by pairing one clean item with
    others that rest on unresolved loops."

    Setting the stage: "c1" is closed citing e-bad (EES, depends on an
    authority-closed "rig") and e-free (no upstream loops; EES or model
    output). The verdict: the closure is never chain-sound.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    to_review(sv, "rig")
    to_review(sv, "c1")
    close_by_authority(sv, "rig")
    sv.add_evidence("e-bad", "measured on the rig", "test", EvidenceKind.DIRECT_MEASUREMENT,
                    INDEPENDENT_LAB, "evidence-clerk", signal_ids=("c1",),
                    depends_on=["rig"])
    if second_is_ees:
        add_ees(sv, "e-free", ["c1"])
    else:
        add_non_ees(sv, "e-free", EvidenceKind.MODEL_OUTPUT, ["c1"])
    sv.attempt_closure("c1", REVIEWER, TECH, ["e-bad", "e-free"], "measured twice")
    assert sv.chain_sound("c1") is False


def test_non_qualifying_item_resting_on_an_unresolved_loop_also_breaks_it():
    """
    Spec: "every item of evidence it cites" — not every qualifying item.

    Setting the stage: "c1" is closed citing a clean EES item and a model
    output that depends on an authority-closed "rig". The verdict: not
    chain-sound. Without the model output it would be.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    to_review(sv, "rig")
    to_review(sv, "c1")
    close_by_authority(sv, "rig")
    add_ees(sv, "e-clean", ["c1"])
    sv.add_evidence("e-model", "simulated on the rig", "test", EvidenceKind.MODEL_OUTPUT,
                    INDEPENDENT_LAB, "evidence-clerk", signal_ids=("c1",),
                    depends_on=["rig"])
    sv.attempt_closure("c1", REVIEWER, TECH, ["e-clean", "e-model"], "measured and simulated")
    assert sv.chain_sound("c1") is False


def test_harmless_extra_item_does_not_break_a_sound_closure():
    """
    Setting the stage: "c1" closed citing a clean EES item and a model
    output with no upstream loops. The verdict: chain-sound (the model
    output is not evidence, but it rests on nothing unresolved).
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    to_review(sv, "c1")
    add_ees(sv, "e-clean", ["c1"])
    add_non_ees(sv, "e-model", EvidenceKind.MODEL_OUTPUT, ["c1"])
    sv.attempt_closure("c1", REVIEWER, TECH, ["e-clean", "e-model"], "measured")
    assert sv.chain_sound("c1") is True


# ===========================================================================
# SCENE 31b — AN UPSTREAM LOOP SUPERSEDED
# Proves: an upstream loop "exited as superseded with an External Evidence
# Source" counts as resolved in the chain; superseded without one does not.
# ===========================================================================

@pytest.mark.parametrize("with_ees", [True, False], ids=["superseded-ees", "superseded-bare"])
def test_upstream_superseded_with_ees_resolves_the_chain(with_ees):
    """
    Spec (Closure Chain): every upstream loop "itself resolved — closed by
    chain-sound evidence closure, or exited as superseded with an External
    Evidence Source".

    Setting the stage: "rig" exits superseded (the old rig was retired),
    citing an independent record or nothing; "c1" is evidence-closed with
    evidence depending on "rig". The verdict: c1 is chain-sound exactly
    when the supersession was shown by an EES.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    to_review(sv, "rig")
    to_review(sv, "c1")
    if with_ees:
        add_ees(sv, "retirement-record", kind=EvidenceKind.PRIMARY_DOCUMENT)
    sv.exit("rig", ExitType.SUPERSEDED, "steward", "the old rig was retired",
            evidence_ids=["retirement-record"] if with_ees else [])
    close_by_evidence(sv, "c1", "e1", depends_on=["rig"])
    assert sv.chain_sound("c1") is with_ees


# ===========================================================================
# SCENE 32 — CHASING ONE'S OWN TAIL
# Proves: evidence caught in a dependency cycle never makes a closure
# chain-sound (two-loop cycle and self-loop).
# ===========================================================================

def test_dependency_cycle_never_counts():
    """
    Spec: "A loop cannot be its own upstream, directly or through others;
    evidence caught in such a cycle does not make a closure chain-sound."

    Setting the stage: "x" is closed with evidence depending on "y", and "y"
    with evidence depending on "x". Separately, "z" is closed with evidence
    depending on "z" itself. The verdict: none is chain-sound.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    #   sid  each signal id, put under review in turn
    sv = Supervisor()
    for sid in ("x", "y", "z"):
        to_review(sv, sid)
    close_by_evidence(sv, "x", "e-x", depends_on=["y"])
    close_by_evidence(sv, "y", "e-y", depends_on=["x"])
    close_by_evidence(sv, "z", "e-z", depends_on=["z"])
    assert sv.chain_sound("x") is False
    assert sv.chain_sound("y") is False
    assert sv.chain_sound("z") is False


# ===========================================================================
# SCENE 33 — THE RIG REOPENED
# Proves: reopening an upstream loop after the downstream closure removes
# the downstream's standing and logs CHAIN_WEAKENED.
# ===========================================================================

def test_reopening_upstream_weakens_downstream_and_is_logged():
    """
    Spec: "if an upstream loop is later reopened ..., every closure
    downstream of it loses its standing, and the weakened link is logged."
    API: CHAIN_WEAKENED with payload "signal" (downstream) and "upstream"
    (the reopened signal).
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    #   logged       the CHAIN_WEAKENED entries
    sv = Supervisor()
    to_review(sv, "rig")
    to_review(sv, "c1")
    close_by_evidence(sv, "rig", "e-rig")
    close_by_evidence(sv, "c1", "e1", depends_on=["rig"])
    assert sv.chain_sound("c1") is True
    assert entries(sv, "CHAIN_WEAKENED") == []
    # --- The action: the rig's calibration is questioned --------------------
    sv.reopen("rig", "auditor", "calibration certificate was for another rig")
    # --- The verdict --------------------------------------------------------
    assert sv.chain_sound("c1") is False
    logged = entries(sv, "CHAIN_WEAKENED")
    assert len(logged) == 1
    assert logged[0].payload["signal"] == "c1"
    assert logged[0].payload["upstream"] == "rig"
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert len(failures_with(result, CONSTRAINT_MSG)) == 1


# ===========================================================================
# SCENE 34 — A DEPENDENCY ON NOTHING
# Proves: an unknown id in depends_on is refused and nothing is stored.
# ===========================================================================

def test_unknown_upstream_id_is_refused_and_nothing_stored():
    """
    Spec: "Dependencies are registered by the agent who adds the evidence".
    API: "Unknown ids are refused (TransitionRefused) and nothing is stored."

    The verdict: the refusal is raised; the evidence is not attached to the
    signal; the same evidence id can then be added cleanly (it was never
    stored).
    """
    # PLAYERS IN THIS SCENE
    #   sv    the Supervisor
    #   sig   the Signal the evidence was meant for
    sv = Supervisor()
    sig = to_review(sv, "c1")
    with pytest.raises(TransitionRefused):
        sv.add_evidence("e1", "measured", "test", EvidenceKind.DIRECT_MEASUREMENT,
                        INDEPENDENT_LAB, "evidence-clerk", signal_ids=("c1",),
                        depends_on=["no-such-loop"])
    assert "e1" not in sig.evidence_ids
    # --- Nothing stored: the id is still free -------------------------------
    sv.add_evidence("e1", "measured", "test", EvidenceKind.DIRECT_MEASUREMENT,
                    INDEPENDENT_LAB, "evidence-clerk", signal_ids=("c1",))
    assert "e1" in sig.evidence_ids


# ===========================================================================
# SCENE 34b — A DEPENDENCY FOUND LATER
# Proves: "A dependency registered after the closure it affects, because it
# was discovered later, is logged as late, and the closure loses its
# standing from that point".
# ===========================================================================

def test_late_dependency_is_logged_and_weakens_the_closure():
    """
    Setting the stage: "c1" closed by chain-sound evidence e1; "rig" was
    closed by authority. The action: e1 is found to depend on "rig"
    (add_dependency). The verdict: LATE_DEPENDENCY names the closure,
    CHAIN_WEAKENED names c1, c1 is no longer chain-sound, and a dependency
    added to uncited evidence is logged only as DEPENDENCY_ADDED.
    """
    # PLAYERS IN THIS SCENE
    #   sv     the Supervisor
    #   rec    c1's closure record
    #   late   the LATE_DEPENDENCY entries
    sv = Supervisor()
    to_review(sv, "rig")
    to_review(sv, "c1")
    close_by_authority(sv, "rig")
    rec = close_by_evidence(sv, "c1", "e1")
    assert sv.chain_sound("c1") is True
    sv.add_dependency("e1", "rig", "auditor")
    late = entries(sv, "LATE_DEPENDENCY")
    assert len(late) == 1 and late[0].payload["closures"] == [rec.record_id]
    assert [e.payload["signal"] for e in entries(sv, "CHAIN_WEAKENED")] == ["c1"]
    assert sv.chain_sound("c1") is False
    assert sv.evidence["e1"].depends_on == ("rig",)
    # --- Evidence nobody has cited yet: not late -----------------------------
    add_ees(sv, "e-spare")
    sv.add_dependency("e-spare", "rig", "auditor")
    assert len(entries(sv, "LATE_DEPENDENCY")) == 1
    assert len(entries(sv, "DEPENDENCY_ADDED")) == 2
    with pytest.raises(TransitionRefused):
        sv.add_dependency("e-spare", "no-such-loop", "auditor")


# ===========================================================================
# SCENE 35 — ONLY EVIDENCE CLOSURES ARE CHAIN-SOUND
# Proves: chain_sound is False for an open or authority-closed signal, and
# an unknown acceptance evidence id is refused.
# ===========================================================================

def test_chain_sound_false_for_non_evidence_states_and_unknown_acceptance_id():
    """
    Spec Key Definition: "An evidence closure is chain-sound only if ...";
    a loop that is not closed by evidence closure is not chain-sound.
    API: accept_decision evidence_ids "Unknown ids are refused."
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    to_review(sv, "open")
    to_review(sv, "auth")
    close_by_authority(sv, "auth")
    assert sv.chain_sound("open") is False
    assert sv.chain_sound("auth") is False
    decision(sv, "d1", ["auth"], accept=False)
    with pytest.raises(TransitionRefused):
        sv.accept_decision("d1", DIRECTOR, "accepted", evidence_ids=["no-such-evidence"])


# ===========================================================================
# SCENE 36 — THE DIRECTOR OVERRULES
# Proves: an irreversible decision failing only the new requirements can be
# overridden, and the override is logged.
# ===========================================================================

def test_override_of_new_requirements_is_logged():
    """
    Spec: "Irreversible decisions require evidence-based closure for all
    constraint and anomaly loops, or an explicit open-loop authorization
    with permanent audit logging" and "Gates can be overridden. Every
    override is permanently logged with the agent's identity, rationale, and
    timestamp."

    Setting the stage: a constraint evidence-closed with evidence depending on
    an authority-closed rig (fails the constraint and EES requirements). The
    coherence threshold is set to 0 so that only the new requirements fail.
    The action: request execution without, then with, an override rationale.
    """
    # PLAYERS IN THIS SCENE
    #   sv         the Supervisor (coherence threshold 0)
    #   blocked    the GateResult without override
    #   overruled  the GateResult with override
    sv = Supervisor(Settings(coherence_threshold=0.0))
    to_review(sv, "rig")
    to_review(sv, "c1")
    close_by_authority(sv, "rig")
    close_by_evidence(sv, "c1", "e1", depends_on=["rig"])
    decision(sv, "d1", ["c1"])
    # --- Without override: blocked, and only by new requirements ------------
    blocked = sv.request_execution("d1", DIRECTOR)
    assert not blocked.permitted
    assert blocked.failures
    assert all(f.startswith(NEW_MSGS) for f in blocked.failures)
    assert entries(sv, "GATE_OVERRIDE") == []
    # --- With override: proceeds, failures stay visible, override logged ----
    overruled = sv.request_execution("d1", "risk-officer",
                                     override_rationale="launch window; rig risk accepted")
    assert overruled.overridden
    assert overruled.permitted
    assert failures_with(overruled, CONSTRAINT_MSG)
    assert len(entries(sv, "GATE_OVERRIDE")) == 1


# ===========================================================================
# SCENE 37 — OUTSIDE THE IRREVERSIBLE GATE: THE COHERENCE SCORE
# Proves: a chain-unsound evidence closure scores lower in coherence than
# the same closure with a sound chain.
# ===========================================================================

def test_chain_unsound_closure_lowers_coherence():
    """
    Spec: an evidence closure that is not chain-sound "counts as a
    non-evidence closure wherever closure quality matters: at the execution
    gates, in the evidence closure ratio, and in the coherence score."

    Setting the stage: two identical worlds where "c1" is evidence-closed with
    evidence depending on "rig"; in one the rig is evidence-closed, in the
    other authority-closed. The decision is ELEVATED (coherence applies to
    every decision node). The verdict: the unsound world's coherence is lower.
    """
    # PLAYERS IN THIS SCENE
    #   scores        coherence of the decision in each world
    #   rig_sound     True for the world whose rig is evidence-closed
    #   sv            each world's Supervisor
    scores = {}
    for rig_sound in (True, False):
        sv = Supervisor()
        to_review(sv, "rig")
        to_review(sv, "c1")
        if rig_sound:
            close_by_evidence(sv, "rig", "e-rig")
        else:
            close_by_authority(sv, "rig")
        close_by_evidence(sv, "c1", "e1", depends_on=["rig"])
        decision(sv, "d1", ["c1"], execution_class=ExecutionClass.ELEVATED)
        scores[rig_sound] = sv.coherence("d1")[0]
    assert scores[False] < scores[True]


# EXEUNT — end of file.

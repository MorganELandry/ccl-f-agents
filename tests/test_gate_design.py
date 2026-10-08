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
  3. "irreversible execution requires at least one External Evidence Source
     somewhere in the decision's support, including evidence cited in its
     Rule 4 acceptance";
  4. Closure Chain: "an evidence closure counts as evidence only if its
     evidence chain is evidence-closed all the way up".

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
    Scenes 18-20  exits: which exit types count as resolved
    Scenes 21-26  decision-level External Evidence Source
    Scenes 27-35  the Closure Chain
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
    CUST, INDEPENDENT_LAB, PROCESS, TECH, add_ees, add_non_ees, decision, entries, to_review,
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

# EES_MSG — the failure when the decision's support holds no EES.
EES_MSG = "no External Evidence Source in the decision's support"

# NEW_MSGS — all three new prefixes, for the override scene's check that a
#   decision fails only the new requirements.
NEW_MSGS = (CONSTRAINT_MSG, RATIO_MSG, EES_MSG)

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

# CLOSED_EXITS — exit types whose Loop State After is closed.
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
    Spec: "The remaining loop types — uncertainty, dissent, classification,
    framing — are held to a minimum evidence closure ratio instead" and
    "These loop types are closer to a budget than to a list of distinct
    failure modes, so a ratio is the right test."

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
    Spec: "among the closures of the decision's uncertainty, dissent,
    classification, and framing signals, the share that are chain-sound
    evidence closures meets the domain-configured minimum."

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
    Spec: "the share that are chain-sound evidence closures meets the
    domain-configured minimum." Read literally, "meets" includes equality.

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
# SCENE 16 — NOTHING TO MEASURE
# Proves: with no closures of the other loop types, the ratio is met.
# ===========================================================================

def test_no_other_type_closures_means_ratio_met():
    """
    Spec: "With no such closures, there is nothing to measure and the
    requirement is met."

    Setting the stage: an evidence-closed constraint plus an uncertainty
    loop still under review (so it has no closure). The verdict: no ratio
    failure.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    close_by_evidence(sv, "c1", "e1")
    decision(sv, "d1", ["c1", "u1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, RATIO_MSG) == []


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
# SCENE 18 — EXITS THAT CLOSE THE LOOP
# Proves: a constraint that exited TERMINAL or SUPERSEDED meets the
# requirement.
# ===========================================================================

@pytest.mark.parametrize("exit_type", CLOSED_EXITS, ids=lambda t: t.name)
def test_constraint_exited_with_closed_loop_state_meets_requirement(exit_type):
    """
    Spec: "every constraint and anomaly signal the decision depends on is
    closed by a chain-sound evidence closure, or has exited by a type whose
    Loop State After is closed (terminal, superseded)."

    The decision's support still holds no EES here, so the EES failure is
    expected; this scene checks only the constraint requirement.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    sv.exit("c1", exit_type, "steward", "the loop is finished",
            open_loop_state="no open work remains")
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, CONSTRAINT_MSG) == []


# ===========================================================================
# SCENE 19 — EXITS THAT LEAVE THE LOOP OPEN
# Proves: a constraint that exited by an open-state type, or by TIMEOUT,
# does not meet the requirement.
# ===========================================================================

@pytest.mark.parametrize("exit_type", OPEN_EXITS, ids=lambda t: t.name)
def test_constraint_exited_with_open_loop_state_fails(exit_type):
    """
    Spec: a loop "exited by a type whose Loop State After is open
    (containment, recoverable, delegated, deferred, forced, exhaustion,
    boundary, ambiguity, key person) does not meet it." TIMEOUT is in
    neither list; it is not one of the closed types "(terminal,
    superseded)", so by the positive definition it does not meet it either.
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
    Spec: "every constraint and anomaly signal ... has exited by a type
    whose Loop State After is closed"; deferred is listed as open.
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
# SCENE 21 — REASONED ENTIRELY INDOORS
# Proves: a decision whose support holds no EES fails with the EES message.
# ===========================================================================

def test_decision_without_any_ees_fails():
    """
    Spec: "A decision reasoned through entirely inside one process, however
    many loops it closed or reviews it passed, does not meet this
    requirement."

    Setting the stage: the only constraint exited TERMINAL (it meets the
    constraint requirement without evidence), and the acceptance cites no
    evidence. The verdict: the EES failure appears; the constraint failure
    does not.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    sv.exit("c1", ExitType.TERMINAL, "steward", "done", open_loop_state="none")
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert failures_with(result, EES_MSG) == [EES_MSG]
    assert failures_with(result, CONSTRAINT_MSG) == []


# ===========================================================================
# SCENE 22 — ONLY NON-EES CLOSURES
# Proves: loops closed only by authority give no EES.
# ===========================================================================

def test_decision_closed_only_by_authority_fails_ees():
    """
    Spec: the support is "the qualifying evidence of its loops' chain-sound
    evidence closures, or evidence cited in its Rule 4 acceptance"; an
    authority closure has no qualifying evidence.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "u1", SignalType.UNCERTAINTY)
    close_by_authority(sv, "u1")
    decision(sv, "d1", ["u1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, EES_MSG) == [EES_MSG]


# ===========================================================================
# SCENE 23 — A WITNESS AT THE SIGNING
# Proves: EES evidence cited in the Rule 4 acceptance satisfies the
# requirement.
# ===========================================================================

def test_ees_cited_in_acceptance_satisfies_requirement():
    """
    Spec (changelog): "irreversible execution requires at least one External
    Evidence Source somewhere in the decision's support, including evidence
    cited in its Rule 4 acceptance."

    Setting the stage: as in Scene 21, but the director cites an independent
    lab measurement when accepting. The verdict: no EES failure.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    sv.exit("c1", ExitType.TERMINAL, "steward", "done", open_loop_state="none")
    decision(sv, "d1", ["c1"], accept=False)
    add_ees(sv, "acc-ev")
    sv.accept_decision("d1", DIRECTOR, "accepted on the lab's measurement",
                       evidence_ids=["acc-ev"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, EES_MSG) == []


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
    Spec: "at least one EES: evidence of an eligible kind produced by neither
    a process under evaluation in the decision's loops nor the agent
    accepting the decision."
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "c1")
    sv.exit("c1", ExitType.TERMINAL, "steward", "done", open_loop_state="none")
    decision(sv, "d1", ["c1"], accept=False)
    sv.add_evidence("acc-ev", "acceptance evidence", "test", kind, producer,
                    "evidence-clerk")
    sv.accept_decision("d1", DIRECTOR, "accepted", evidence_ids=["acc-ev"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, EES_MSG) == [EES_MSG]


# ===========================================================================
# SCENE 25 — A PROCESS FROM ANOTHER OF THE DECISION'S LOOPS
# Proves: evidence produced by the evaluated process of any of the
# decision's loops is refused, not just the first loop's.
# ===========================================================================

def test_acceptance_evidence_from_another_loops_process_is_not_ees():
    """
    Spec: "produced by neither a process under evaluation in the decision's
    loops nor the agent accepting the decision."

    Setting the stage: two constraints, both exited TERMINAL; the second is
    about "second-process". The acceptance cites a measurement produced by
    "second-process". The verdict: the EES failure appears.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    #   sid          each constraint, exited TERMINAL in turn
    sv = Supervisor()
    to_review(sv, "c1")
    # --- A loop about a different process, built by hand --------------------
    sv.register_signal("c2", SignalType.CONSTRAINT, "signal c2", "engineer", TECH,
                       "second-process", steward="steward", successor="successor")
    sv.classify("c2", OperationalState.ELEVATED_UNCERTAINTY, "engineer")
    sv.open_review("c2", "engineer")
    for sid in ("c1", "c2"):
        sv.exit(sid, ExitType.TERMINAL, "steward", "done", open_loop_state="none")
    decision(sv, "d1", ["c1", "c2"], accept=False)
    add_ees(sv, "acc-ev", produced_by="second-process")
    sv.accept_decision("d1", DIRECTOR, "accepted", evidence_ids=["acc-ev"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, EES_MSG) == [EES_MSG]


# ===========================================================================
# SCENE 26 — HOLLOW EVIDENCE GIVES NO EES
# Proves: EES evidence inside a closure that is not chain-sound does not
# put an EES in the decision's support.
# ===========================================================================

def test_ees_only_inside_chain_unsound_closure_does_not_count():
    """
    Spec: the support is "the qualifying evidence of its loops' chain-sound
    evidence closures, or evidence cited in its Rule 4 acceptance".

    Setting the stage: "rig" authority-closed (outside the decision); "c1"
    evidence-closed with lab evidence depending on "rig". The acceptance
    cites nothing. The verdict: the EES failure appears.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 5
    sv = Supervisor()
    to_review(sv, "rig")
    to_review(sv, "c1")
    close_by_authority(sv, "rig")
    close_by_evidence(sv, "c1", "e1", depends_on=["rig"])
    decision(sv, "d1", ["c1"])
    result = sv.request_execution("d1", DIRECTOR)
    assert failures_with(result, EES_MSG) == [EES_MSG]


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
    Spec: "An evidence closure is chain-sound only if at least one item of
    qualifying evidence it cites has every upstream loop itself chain-sound:
    closed by evidence closure, all the way up."
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
    Spec: "has every upstream loop itself chain-sound: closed by evidence
    closure, all the way up."

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
# SCENE 31 — ONE GOOD WITNESS IS ENOUGH; A BAD-KIND ONE IS NOT
# Proves: "at least one item of qualifying evidence" with a sound chain
# makes the closure sound; non-qualifying evidence cannot supply it.
# ===========================================================================

@pytest.mark.parametrize("second_is_ees", [True, False], ids=["second-ees",
                                                              "second-model-output"])
def test_at_least_one_qualifying_item_with_sound_chain(second_is_ees):
    """
    Spec: "An evidence closure is chain-sound only if at least one item of
    qualifying evidence it cites has every upstream loop itself
    chain-sound".

    Setting the stage: "c1" is closed citing two items: e-bad (EES, depends
    on an authority-closed "rig") and e-free (no upstream loops). When e-free
    is EES it is qualifying evidence with a sound (empty) chain, so the
    closure is sound. When e-free is model output it is not qualifying, so
    only e-bad qualifies and the closure is not sound.
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
    assert sv.chain_sound("c1") is second_is_ees


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
    overruled = sv.request_execution("d1", DIRECTOR,
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

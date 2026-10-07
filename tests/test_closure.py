"""
HOW A LOOP IS SAID TO CLOSE
A Play in Eighteen Scenes
=========================

PROLOGUE
--------
Tests for closure typing in cclf/supervisor.py (attempt_closure, reopen,
adopt_frame), derived from CCL-F v0.2:

  Closure Quality table (spec lines 461-466): evidence closure is valid;
    authority, role-switch and lock-in closure are flagged.
  Role-Switch Closure (Key Definitions, line 1214): the registrant closes
    their own signal by consulting the other referent, with nothing new.
  Evidence Novelty (line 484) and External Evidence Source (lines 486-498):
    evidence closure needs evidence that is BOTH new since registration AND
    causally independent of the process under evaluation. Model output
    never qualifies (line 494).
  Autonomy-Bounded Closure (lines 563-575): a closer outside the closure
    authority produces "attempted closure", recorded but not a resolution.
  Reopen (line 940): "A closed loop cannot be silently reopened — every
    reopen transition is permanently logged with rationale, the identity of
    the reopening agent, and the closure record it supersedes."
  Framing Signal (line 1212): frame adoption is "an authority closure of the
    framing signal combined with a suppression event on the signals it
    displaced".

THE PLAYBILL
    Scene 1   test_novel_ees_evidence_gives_evidence_closure
    Scene 2   test_non_ees_kinds_never_qualify              (parametrized, 3 runs)
    Scene 3   test_evidence_from_evaluated_process_does_not_qualify
    Scene 4   test_evidence_from_registrant_does_not_qualify
    Scene 5   test_evidence_present_at_registration_is_not_novel
    Scene 6   test_evidence_existing_before_registration_is_not_novel
    Scene 7   test_one_qualifying_item_among_many_is_enough
    Scene 8   test_role_switch_same_agent_other_referent_nothing_new
    Scene 9   test_same_agent_with_new_evidence_is_not_role_switch
    Scene 10  test_different_agent_without_evidence_is_authority
    Scene 11  test_same_agent_same_referent_is_authority  (implementation decision)
    Scene 12  test_closure_flags_follow_the_quality_table
    Scene 13  test_closer_outside_authority_leaves_state_unchanged
    Scene 14  test_closer_inside_authority_closes
    Scene 15  test_reopen_is_logged_with_rationale_agent_and_superseded_record
    Scene 16  test_role_switch_reopen_needs_independent_reviewer
    Scene 17  test_open_review_cannot_silently_reopen      (was a spec mismatch; now fixed)
    Scene 18  test_frame_adoption_is_authority_closure     (was a spec mismatch; now fixed)

READER'S NOTE — pytest.raises
    `with pytest.raises(SomeError):` passes only if the indented block
    raises SomeError (or a subclass). If nothing is raised, the test fails.

READER'S NOTE — tests written from the spec
    These tests were written from the CCL-F v0.2 text, not from the code.
    Scenes marked "was a spec mismatch; now fixed" first ran as expected
    failures (pytest's @pytest.mark.xfail(strict=True)) where the code
    disagreed with the spec. Once the code was corrected the marks were
    removed, so each of those scenes now guards its fix.

READER'S NOTE — a fixture, `sv`
    A function decorated with @pytest.fixture is a "fixture". Any test that
    names it as a parameter gets the function's return value, freshly
    built for that test. Here `sv` is a new, empty Supervisor every time,
    so no test can leak state into another.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       fixtures, parametrize, raises.
# cclf         ClosureType, CommitmentState, EvidenceKind, SignalType,
#              Supervisor, TransitionRefused.
# stagehands   shared set-up helpers (see tests/stagehands.py):
#              to_review, add_ees, add_non_ees, entries, TECH, CUST, PROCESS.
# ===========================================================================

import pytest

from cclf import (
    ClosureType, CommitmentState, EvidenceKind, SignalType, Supervisor, TransitionRefused,
)
from stagehands import CUST, PROCESS, TECH, add_ees, add_non_ees, entries, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# S — short alias for CommitmentState, used in every verdict.
S = CommitmentState

# NON_EES_KINDS — the three evidence kinds the spec never accepts as an
#   External Evidence Source: model output (line 494), and restated
#   assertion / internal analysis by the same reasoning process (line 490).
NON_EES_KINDS = [EvidenceKind.MODEL_OUTPUT, EvidenceKind.ASSERTION,
                 EvidenceKind.INTERNAL_ANALYSIS]


# ===========================================================================
# THE FIXTURE — a fresh supervisor for every scene
# ===========================================================================

@pytest.fixture
def sv():
    """
    A new, empty Supervisor.

    Enter:   (nothing)
    Exit:    Supervisor() with default settings
    """
    return Supervisor()


# ===========================================================================
# SCENE 1 — THE VALID READING
# Proves: novel + EES evidence makes an evidence closure (lines 463, 498).
# ===========================================================================

def test_novel_ees_evidence_gives_evidence_closure(sv):
    """
    A closure citing new, independent evidence is typed EVIDENCE.

    Enter:   sv   fixture
    Exit:    passes if the record is EVIDENCE and the signal is closed_evidence
    """
    # --- Setting the stage -------------------------------------------------
    to_review(sv, "c")
    add_ees(sv, "e1", ["c"])
    # --- The action --------------------------------------------------------
    rec = sv.attempt_closure("c", "manager", CUST, ["e1"], "test passed")
    # --- The verdict -------------------------------------------------------
    assert rec.closure_type == ClosureType.EVIDENCE
    assert sv.signals["c"].state == S.CLOSED_EVIDENCE


# ===========================================================================
# SCENE 2 — VOICES THAT DO NOT COUNT
# Proves: model output, assertion and internal analysis never make evidence
# closure, however new they are (lines 490-494). (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("kind", NON_EES_KINDS, ids=lambda k: k.value)
def test_non_ees_kinds_never_qualify(sv, kind):
    """
    New evidence of a non-EES kind gives authority closure, not evidence.

    Enter:   sv     fixture
             kind   one of NON_EES_KINDS
    Exit:    passes if the closure is typed AUTHORITY
    """
    to_review(sv, "c")
    add_non_ees(sv, "e1", kind, ["c"])
    rec = sv.attempt_closure("c", "manager", CUST, ["e1"])
    assert rec.closure_type == ClosureType.AUTHORITY
    assert sv.signals["c"].state == S.CLOSED_AUTHORITY


# ===========================================================================
# SCENE 3 — THE PROCESS MAY NOT VOUCH FOR ITSELF
# Proves: evidence produced by the evaluated process is common-mode, not
# EES (line 496: "does the evidence-generating process share a causal
# ancestry with the process under evaluation").
# ===========================================================================

def test_evidence_from_evaluated_process_does_not_qualify(sv):
    """
    A direct measurement produced BY the evaluated process does not qualify.

    Enter:   sv   fixture
    Exit:    passes if the closure is AUTHORITY
    """
    to_review(sv, "c")
    add_ees(sv, "e1", ["c"], produced_by=PROCESS)
    assert sv.attempt_closure("c", "manager", CUST, ["e1"]).closure_type \
        == ClosureType.AUTHORITY


# ===========================================================================
# SCENE 4 — NOR MAY THE REGISTRANT
# Proves: evidence produced by the signal's own registrant is not causally
# independent of "the reasoning process that produced the signal" (line 490).
# ===========================================================================

def test_evidence_from_registrant_does_not_qualify(sv):
    """
    Evidence produced by the registrant does not qualify as EES.

    Enter:   sv   fixture
    Exit:    passes if the closure is AUTHORITY
    """
    to_review(sv, "c", by="engineer")
    add_ees(sv, "e1", ["c"], produced_by="engineer")
    assert sv.attempt_closure("c", "manager", CUST, ["e1"]).closure_type \
        == ClosureType.AUTHORITY


# ===========================================================================
# SCENE 5 — OLD NEWS, PART ONE
# Proves: evidence cited at registration is not novel (line 484).
# ===========================================================================

def test_evidence_present_at_registration_is_not_novel(sv):
    """
    Re-citing the registration evidence gives authority closure.

    Enter:   sv   fixture
    Exit:    passes if the closure is AUTHORITY even though the evidence is EES
    """
    add_ees(sv, "e0")
    to_review(sv, "c", evidence_ids=["e0"])
    assert sv.attempt_closure("c", "manager", CUST, ["e0"]).closure_type \
        == ClosureType.AUTHORITY


# ===========================================================================
# SCENE 6 — OLD NEWS, PART TWO
# Proves: evidence that existed before registration is not novel even when
# it was not cited then ("not present when the signal was registered").
# ===========================================================================

def test_evidence_existing_before_registration_is_not_novel(sv):
    """
    EES evidence added before the signal was registered is not novel.

    Enter:   sv   fixture
    Exit:    passes if the closure is AUTHORITY
    """
    add_ees(sv, "e-old")
    to_review(sv, "c")
    assert sv.attempt_closure("c", "manager", CUST, ["e-old"]).closure_type \
        == ClosureType.AUTHORITY


# ===========================================================================
# SCENE 7 — ONE TRUE WITNESS IS ENOUGH
# Proves: line 492, "at least one External Evidence Source supporting the
# closing claim"; non-qualifying company does not spoil it.
# ===========================================================================

def test_one_qualifying_item_among_many_is_enough(sv):
    """
    Model output plus one novel EES item is still evidence closure.

    Enter:   sv   fixture
    Exit:    passes if the closure is EVIDENCE
    """
    to_review(sv, "c")
    add_non_ees(sv, "m1", EvidenceKind.MODEL_OUTPUT, ["c"])
    add_ees(sv, "e1", ["c"])
    assert sv.attempt_closure("c", "manager", CUST, ["m1", "e1"]).closure_type \
        == ClosureType.EVIDENCE


# ===========================================================================
# SCENE 8 — "TAKE OFF YOUR ENGINEERING HAT"
# Proves: line 1214, same agent, different referent, nothing new from
# either -> role-switch closure. (The Lund pattern, with no pending
# escalation in the way.)
# ===========================================================================

def test_role_switch_same_agent_other_referent_nothing_new(sv):
    """
    The registrant closing their own technical signal from the customer
    referent, citing nothing, is role-switch closure.

    Enter:   sv   fixture
    Exit:    passes if the record is ROLE_SWITCH and the state closed_role_switch
    """
    to_review(sv, "no-launch", signal_type=SignalType.UNCERTAINTY, by="lund",
              referent=TECH)
    rec = sv.attempt_closure("no-launch", "lund", CUST, (), "management perspective")
    assert rec.closure_type == ClosureType.ROLE_SWITCH
    assert sv.signals["no-launch"].state == S.CLOSED_ROLE_SWITCH


# ===========================================================================
# SCENE 9 — A HAT CHANGE WITH NEWS IS NOT A ROLE SWITCH
# Proves: the role-switch test needs "without that referent supplying
# anything new"; with novel EES evidence the closure is evidence closure.
# ===========================================================================

def test_same_agent_with_new_evidence_is_not_role_switch(sv):
    """
    Same agent, other referent, but novel EES evidence: EVIDENCE closure.

    Enter:   sv   fixture
    Exit:    passes if the closure is EVIDENCE
    """
    to_review(sv, "c", by="lund")
    add_ees(sv, "e1", ["c"])
    assert sv.attempt_closure("c", "lund", CUST, ["e1"]).closure_type \
        == ClosureType.EVIDENCE


# ===========================================================================
# SCENE 10 — THE SENIOR OVERRIDE
# Proves: line 464, "A senior agent overrides without new evidence" ->
# authority closure; a different agent is never a role switch (line 468).
# ===========================================================================

def test_different_agent_without_evidence_is_authority(sv):
    """
    A different agent from the other referent, no evidence: AUTHORITY.

    Enter:   sv   fixture
    Exit:    passes if the closure is AUTHORITY
    """
    to_review(sv, "c", by="engineer")
    assert sv.attempt_closure("c", "vp", CUST).closure_type == ClosureType.AUTHORITY


# ===========================================================================
# SCENE 11 — WITHDRAWING ONE'S OWN SIGNAL
# Proves (implementation decision): the registrant closing their own
# signal from the SAME referent with nothing new is typed authority.
# ===========================================================================

def test_same_agent_same_referent_is_authority(sv):
    """
    Implementation-decision test: the spec names no closure type for a
    registrant who closes their own signal without changing referent or
    adding evidence (it is not role-switch per line 1214, and line 492 says
    a closure without EES is authority, role-switch or false closure). The
    code types it AUTHORITY, which is the flagged default.

    Enter:   sv   fixture
    Exit:    passes if the closure is AUTHORITY
    """
    to_review(sv, "c", by="engineer", referent=TECH)
    assert sv.attempt_closure("c", "engineer", TECH).closure_type == ClosureType.AUTHORITY


# ===========================================================================
# SCENE 12 — FLAGGED AND UNFLAGGED
# Proves: the Closure Quality table's status column: evidence "Valid",
# authority and role-switch "Flagged".
# ===========================================================================

def test_closure_flags_follow_the_quality_table(sv):
    """
    The logged TRANSITION for each closure carries flagged = not evidence.

    Enter:   sv   fixture
    Exit:    passes if evidence -> flagged False; authority and role-switch
             -> flagged True
    """
    # PLAYERS IN THIS SCENE
    #   flags   closure_type value -> flagged, read off the audit trail

    # --- Setting the stage: one closure of each kind ------------------------
    for sid in ("ev", "au", "rs"):
        to_review(sv, sid, signal_type=SignalType.UNCERTAINTY, by="eng")
    add_ees(sv, "e1", ["ev"])
    sv.attempt_closure("ev", "mgr", CUST, ["e1"])
    sv.attempt_closure("au", "mgr", CUST)
    sv.attempt_closure("rs", "eng", CUST)
    # --- The action: read the flags back from the log ----------------------
    flags = {e.payload["closure_type"]: e.payload["flagged"]
             for e in entries(sv, "TRANSITION") if "closure_type" in e.payload}
    # --- The verdict -------------------------------------------------------
    assert flags == {"evidence": False, "authority": True, "role_switch": True}


# ===========================================================================
# SCENE 13 — A MESSAGE ACROSS THE BOUNDARY
# Proves: lines 567 and 573: beyond the closure-authority boundary closure
# "can be attempted but not enforced"; attempted closure "is recorded as a
# coordination event but does not constitute loop resolution".
# ===========================================================================

def test_closer_outside_authority_leaves_state_unchanged(sv):
    """
    A closer outside closure_authority makes an attempted-only record.

    Enter:   sv   fixture
    Exit:    passes if the state stays under_review, the record is marked
             attempted_only and kept on the signal, and ATTEMPTED_CLOSURE
             is logged with the closer as actor
    """
    to_review(sv, "c", closure_authority=["chief-engineer"])
    add_ees(sv, "e1", ["c"])
    rec = sv.attempt_closure("c", "outside-agency", CUST, ["e1"])
    assert sv.signals["c"].state == S.UNDER_REVIEW
    assert rec.attempted_only and rec in sv.signals["c"].closures
    assert [e.actor for e in entries(sv, "ATTEMPTED_CLOSURE")] == ["outside-agency"]


# ===========================================================================
# SCENE 14 — INSIDE THE BOUNDARY
# Proves: local closure is valid within the closer's scope (line 571).
# ===========================================================================

def test_closer_inside_authority_closes(sv):
    """
    A closer listed in closure_authority actually closes the loop.

    Enter:   sv   fixture
    Exit:    passes if the record is not attempted-only and the state is closed
    """
    to_review(sv, "c", closure_authority=["chief-engineer"])
    add_ees(sv, "e1", ["c"])
    rec = sv.attempt_closure("c", "chief-engineer", CUST, ["e1"])
    assert not rec.attempted_only
    assert sv.signals["c"].state == S.CLOSED_EVIDENCE


# ===========================================================================
# SCENE 15 — NO SILENT REOPENING
# Proves: line 940, every reopen is logged with rationale, the reopening
# agent and the superseded closure record; line 942, the original closure
# record is retained and the reopen count is kept.
# ===========================================================================

def test_reopen_is_logged_with_rationale_agent_and_superseded_record(sv):
    """
    reopen() needs a rationale and logs who, why and what it supersedes.

    Enter:   sv   fixture
    Exit:    passes if a blank rationale is refused; a real reopen logs
             actor, rationale and supersedes=<the closure record id>; the
             closure record is still on the signal; reopen_count is 1
    """
    # PLAYERS IN THIS SCENE
    #   rec    the original authority closure record
    #   last   the last TRANSITION entry (the reopen)

    to_review(sv, "c")
    rec = sv.attempt_closure("c", "vp", CUST)
    # --- A silent reopen is refused ----------------------------------------
    with pytest.raises(TransitionRefused):
        sv.reopen("c", "auditor", "")
    assert sv.signals["c"].state == S.CLOSED_AUTHORITY
    # --- A logged reopen ---------------------------------------------------
    sv.reopen("c", "auditor", "new failure data")
    last = entries(sv, "TRANSITION")[-1]
    assert (last.payload["from"], last.payload["to"]) == ("closed_authority", "under_review")
    assert last.actor == "auditor"
    assert last.payload["rationale"] == "new failure data"
    assert last.payload["supersedes"] == rec.record_id
    assert rec in sv.signals["c"].closures
    assert sv.signals["c"].reopen_count == 1


# ===========================================================================
# SCENE 16 — THE ROLE-SWITCH REOPEN NEEDS FRESH EYES
# Proves: line 892, "closed_role_switch -> under_review (mandatory
# independent review; L2 flag)"; line 468, "requiring independent review".
# ===========================================================================

def test_role_switch_reopen_needs_independent_reviewer(sv):
    """
    The registrant/closer cannot reopen their own role-switch closure.

    Enter:   sv   fixture
    Exit:    passes if the registrant's reopen is refused and an independent
             reviewer's reopen succeeds, logged independent_review_required
    """
    to_review(sv, "u", signal_type=SignalType.UNCERTAINTY, by="lund")
    sv.attempt_closure("u", "lund", CUST)
    with pytest.raises(TransitionRefused):
        sv.reopen("u", "lund", "I changed my mind again")
    sv.reopen("u", "independent-reviewer", "independent review")
    assert sv.signals["u"].state == S.UNDER_REVIEW
    assert entries(sv, "TRANSITION")[-1].payload["independent_review_required"] is True


# ===========================================================================
# SCENE 17 — THE BACK DOOR INTO REVIEW
# Proves: open_review() on a closed signal should not
# perform a reopen that skips Scene 15's obligations.
# ===========================================================================

def test_open_review_cannot_silently_reopen(sv):
    """
    open_review must refuse a signal that is closed; reopen() is the only door.

    Enter:   sv   fixture
    Exit:    passes if open_review raises TransitionRefused on a role-switch
             closed signal, even when called by the registrant
    """
    to_review(sv, "u", signal_type=SignalType.UNCERTAINTY, by="lund")
    sv.attempt_closure("u", "lund", CUST)
    with pytest.raises(TransitionRefused):
        sv.open_review("u", "lund")


# ===========================================================================
# SCENE 18 — FRAME ADOPTION IS AUTHORITY CLOSURE
# Proves: line 1212 types frame adoption as authority
# closure regardless of who adopts it.
# ===========================================================================

def test_frame_adoption_is_authority_closure(sv):
    """
    A framing signal adopted by its own registrant is still authority closure.

    Enter:   sv   fixture
    Exit:    passes if the framing signal ends closed_authority
    """
    to_review(sv, "frame", signal_type=SignalType.FRAMING, by="manager", referent=TECH)
    sv.adopt_frame("frame", "manager", [], "burden of proof inverted")
    assert sv.signals["frame"].state == S.CLOSED_AUTHORITY

# EXEUNT — end of file.

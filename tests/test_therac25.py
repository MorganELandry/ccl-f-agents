"""
THE THERAC-25 INQUIRY
A Play in Four Acts
====================

PROLOGUE
--------
Tests for Therac-25 scenario structure and CCL-F core logic.
No LLM calls required.

The Therac-25 was a radiation-therapy machine that overdosed six patients
between 1985 and 1987. scenarios/therac25.py retells that history as CCL-F
evidence in two "passes":

    PASS_1_INCIDENTS     six batches, one per incident, as hospitals saw them
    PASS_2_SUPPRESSION   the manufacturer's (AECL's) internal documents that
                         were never shared: the race-condition memo, the
                         "no fault found" letters, the recall notice

This file checks that the scenario data is shaped the way the demo needs it,
that the guard behaves the same here as in any other domain, that the CCL-F
types can express the three ACO conditions, and that the audit chain holds
over a full two-pass run. Nothing here calls a language model.

Run: pytest tests/ -v

THE PLAYBILL
    Act I    TestTherac25ScenarioStructure   is the scenario data well-formed?
      Scene 1  test_pass1_has_six_incident_batches
      Scene 2  test_each_incident_has_at_least_one_evidence_item
      Scene 3  test_pass2_has_suppression_documents
      Scene 4  test_all_evidence_ids_unique_across_passes
      Scene 5  test_all_evidence_has_required_fields
      Scene 6  test_pass2_contains_race_condition_evidence
      Scene 7  test_pass2_contains_no_fault_found_reference
      Scene 8  test_incident_4_contains_proceed_keypress
      Scene 9  test_incident_6_triggers_regulatory_action
    Act II   TestGuards                      the guard, re-checked for this domain
      Scene 1  test_valid_forward_chain
      Scene 2  test_all_blocked_transitions
      Scene 3  test_next_valid_state_sequence
    Act III  TestACOConditions               can the types express C1, C2, C3?
      Scene 1  test_c1_state_divergence_is_modelable
      Scene 2  test_c2_suppressed_evidence_is_present
      Scene 3  test_c3_authority_inaccessible_while_trajectory_locked
    Act IV   TestAuditChain                  the hash chain over two passes
      Scene 1  test_chain_integrity_across_two_passes

READER'S NOTE — the sys.path line at the top of the imports
    This file adds the repo root to `sys.path` itself, at import time, before
    importing `cclf` and `scenarios`. `sys.path` is the list of folders Python
    searches on `import`. The expression

        os.path.dirname(os.path.dirname(__file__))

    starts from this file's own path (tests/test_therac25.py), strips the
    file name to get tests/, then strips again to get the repo root.
    `insert(0, ...)` puts it at the front of the list so it is searched first.

    With pytest this is now redundant: pytest.ini's `pythonpath = . tests`
    already puts the repo root on sys.path for every test file. The line is
    left exactly as it is (this commenting pass changes no code); it is
    harmless, and it would still let the imports work if the file were run
    by some other tool that ignores pytest.ini.

READER'S NOTE — test discovery, assert, and test classes
    See the notes at the top of tests/test_guards.py. In short: pytest
    collects `test_*` functions and the `test_*` methods of `Test*` classes,
    and a bare `assert` that fails turns into a readable test failure. A
    failing assert's optional message (after the comma) is printed with it.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# sys, os      used only by the sys.path line below (see READER'S NOTE).
# pytest       the test runner; imported but no `pytest.` helper is called.
# cclf.types   CommitmentState, ACSEstimate and CCLFAgentState are used below;
#              Evidence and AuditEntry are imported but not used in this file.
# cclf.guards  the deterministic transition guard.
# scenarios.therac25  the two evidence passes under test.
# ===========================================================================

import sys
import os
# Put the repo root at the front of the import search path, so that
# `cclf` and `scenarios` below can be found. Computed from this file's own
# location: tests/test_therac25.py → tests/ → repo root. (Redundant under
# pytest thanks to pytest.ini, but kept unchanged.)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from cclf.types import CommitmentState, Evidence, ACSEstimate, CCLFAgentState, AuditEntry
from cclf.guards import check_transition, next_valid_state
from scenarios.therac25 import PASS_1_INCIDENTS, PASS_2_SUPPRESSION


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# (none) — this file defines only test classes. The scenario data it checks
# (PASS_1_INCIDENTS, PASS_2_SUPPRESSION) is imported, not defined here.
# Each item in that data is a plain dict with at least the keys
# "evidence_id", "content" and "source".
# ===========================================================================


# ===========================================================================
# ACT I — THE SCENARIO ON THE PAGE
# Is the Therac-25 evidence data complete and well-formed?
# ===========================================================================

class TestTherac25ScenarioStructure:
    """Checks on the shape and content of scenarios/therac25.py."""

    # -----------------------------------------------------------------------
    # ACT I, SCENE 1 — SIX INCIDENTS
    # Proves: pass 1 has exactly six batches, one per historical overdose.
    # -----------------------------------------------------------------------
    def test_pass1_has_six_incident_batches(self):
        """
        PASS_1_INCIDENTS holds six batches.

        Enter:   self   unused (pytest supplies it because this is a method)
        Exit:    passes if there are exactly six
        """
        # --- Setting the stage / The action / The verdict ------------------
        # The text after the comma is the failure message; the parentheses
        # only let it wrap onto its own line.
        assert len(PASS_1_INCIDENTS) == 6, (
            "Therac-25 had six confirmed overdose incidents"
        )

    # -----------------------------------------------------------------------
    # ACT I, SCENE 2 — NO EMPTY BATCHES
    # Proves: every incident batch contains at least one evidence item.
    # -----------------------------------------------------------------------
    def test_each_incident_has_at_least_one_evidence_item(self):
        """
        Every batch in PASS_1_INCIDENTS is non-empty.

        Enter:   self   unused
        Exit:    passes, or fails naming the (1-based) empty batch
        """
        # PLAYERS IN THIS SCENE
        #   idx     0-based position of the batch (from enumerate)
        #   batch   one incident's list of evidence dicts

        # --- The action and the verdict, once per batch --------------------
        # enumerate() yields (index, item) pairs; idx+1 turns the 0-based
        # index into the human "Incident 1..6" numbering for the message.
        for idx, batch in enumerate(PASS_1_INCIDENTS):
            assert len(batch) >= 1, f"Incident batch {idx+1} is empty"

    # -----------------------------------------------------------------------
    # ACT I, SCENE 3 — THE HIDDEN DOCUMENTS
    # Proves: pass 2 holds at least four suppression documents.
    # -----------------------------------------------------------------------
    def test_pass2_has_suppression_documents(self):
        """
        PASS_2_SUPPRESSION has at least four items.

        Enter:   self   unused
        Exit:    passes if len(PASS_2_SUPPRESSION) >= 4
        """
        # --- Setting the stage / The action / The verdict ------------------
        # Two adjacent string literals inside parentheses are joined by
        # Python into one string, which is how the long message is wrapped.
        assert len(PASS_2_SUPPRESSION) >= 4, (
            "Pass 2 should include race condition memo, 'no fault' letters, "
            "engineering analysis, and recall notice"
        )

    # -----------------------------------------------------------------------
    # ACT I, SCENE 4 — ONE NAME PER WITNESS
    # Proves: no evidence_id is used twice anywhere across both passes.
    # -----------------------------------------------------------------------
    def test_all_evidence_ids_unique_across_passes(self):
        """
        Every evidence_id in both passes is unique.

        Enter:   self   unused
        Exit:    passes if there are no duplicate IDs

        Unique IDs matter because the agent and the audit log refer to
        evidence by ID; a duplicate would make two items indistinguishable.
        """
        # PLAYERS IN THIS SCENE
        #   all_ids   every evidence_id collected from both passes, in order
        #   batch     one pass-1 incident batch
        #   ev        one evidence dict

        # --- Setting the stage: gather every ID ----------------------------
        all_ids = []
        for batch in PASS_1_INCIDENTS:
            for ev in batch:
                all_ids.append(ev["evidence_id"])
        for ev in PASS_2_SUPPRESSION:
            all_ids.append(ev["evidence_id"])

        # --- The verdict ---------------------------------------------------
        # A set keeps only one copy of each value, so if the set is shorter
        # than the list, some ID appeared more than once.
        assert len(all_ids) == len(set(all_ids)), "Duplicate evidence IDs detected"

    # -----------------------------------------------------------------------
    # ACT I, SCENE 5 — EVERY WITNESS FULLY NAMED
    # Proves: each evidence dict has the keys Evidence(**item) needs.
    # -----------------------------------------------------------------------
    def test_all_evidence_has_required_fields(self):
        """
        Every evidence dict has evidence_id, content and source.

        Enter:   self   unused
        Exit:    passes, or fails naming the item and its missing keys
        """
        # PLAYERS IN THIS SCENE
        #   required   the set of keys every evidence dict must have
        #   batch      one pass-1 incident batch
        #   ev         one evidence dict
        #   missing    required keys that `ev` lacks (empty set when all present)

        # --- Setting the stage ---------------------------------------------
        required = {"evidence_id", "content", "source"}

        # --- The action and the verdict: pass 1 ----------------------------
        # `required - set(ev.keys())` is set difference: the keys in
        # `required` that are not in `ev`. An empty set is falsy, so
        # `assert not missing` passes when nothing is missing.
        # `ev.get('evidence_id')` returns None instead of crashing if the ID
        # itself is the missing key.
        for batch in PASS_1_INCIDENTS:
            for ev in batch:
                missing = required - set(ev.keys())
                assert not missing, f"Evidence {ev.get('evidence_id')} missing: {missing}"

        # --- The action and the verdict: pass 2 ----------------------------
        for ev in PASS_2_SUPPRESSION:
            missing = required - set(ev.keys())
            assert not missing, f"Evidence {ev.get('evidence_id')} missing: {missing}"

    # -----------------------------------------------------------------------
    # ACT I, SCENE 6 — THE RACE CONDITION
    # Proves: the words "race condition" appear somewhere in pass 2.
    # -----------------------------------------------------------------------
    def test_pass2_contains_race_condition_evidence(self):
        """
        The race condition finding must be present — it's the core ACO signal.

        Enter:   self   unused
        Exit:    passes if any pass-2 content mentions "race condition"
        """
        # PLAYERS IN THIS SCENE
        #   combined   all pass-2 content joined into one lower-case string

        # --- Setting the stage ---------------------------------------------
        # `" ".join(... for ev in ...)` glues every content string together
        # with spaces; `.lower()` makes the search case-insensitive.
        combined = " ".join(ev["content"] for ev in PASS_2_SUPPRESSION).lower()
        # --- The action and the verdict ------------------------------------
        assert "race condition" in combined

    # -----------------------------------------------------------------------
    # ACT I, SCENE 7 — "NO FAULT FOUND"
    # Proves: pass 2 refers to the "no fault" letters (or "no hardware").
    # -----------------------------------------------------------------------
    def test_pass2_contains_no_fault_found_reference(self):
        """
        'No fault found' letters are the ACO mechanism.

        Enter:   self   unused
        Exit:    passes if pass-2 content mentions "no fault" or "no hardware"
        """
        # PLAYERS IN THIS SCENE
        #   combined   all pass-2 content joined into one lower-case string

        # --- Setting the stage ---------------------------------------------
        combined = " ".join(ev["content"] for ev in PASS_2_SUPPRESSION).lower()
        # --- The action and the verdict ------------------------------------
        assert "no fault" in combined or "no hardware" in combined

    # -----------------------------------------------------------------------
    # ACT I, SCENE 8 — THE "P" KEY
    # Proves: incident 4's evidence mentions the operator pressing on through
    # a treatment pause.
    # -----------------------------------------------------------------------
    def test_incident_4_contains_proceed_keypress(self):
        """
        The 'proceed through pause' operator behaviour in Incident 4 is
        CCL-F-relevant: trained procedure converted a safety pause into a hazard.

        Enter:   self   unused
        Exit:    passes if incident 4 mentions "proceed", "keypress" or 'p'
        """
        # PLAYERS IN THIS SCENE
        #   batch      the evidence list for incident 4
        #   combined   that batch's content joined into one lower-case string

        # --- Setting the stage ---------------------------------------------
        batch = PASS_1_INCIDENTS[3]  # 0-indexed, Incident 4
        combined = " ".join(ev["content"] for ev in batch).lower()
        # --- The action and the verdict ------------------------------------
        # Any one of the three phrasings is enough. (`combined` is already
        # lower-case, so the final `.lower()` is a harmless repeat.)
        assert "proceed" in combined or "keypress" in combined or "'p'" in combined.lower()

    # -----------------------------------------------------------------------
    # ACT I, SCENE 9 — THE REGULATOR ARRIVES
    # Proves: incident 6's evidence mentions the NRC, a recall, or regulators.
    # -----------------------------------------------------------------------
    def test_incident_6_triggers_regulatory_action(self):
        """
        Incident 6 should reference NRC — the first external authority closure.

        Enter:   self   unused
        Exit:    passes if incident 6 mentions NRC, RECALL or REGULATORY
        """
        # PLAYERS IN THIS SCENE
        #   batch      the evidence list for incident 6
        #   combined   that batch's content joined into one UPPER-case string

        # --- Setting the stage ---------------------------------------------
        # Upper-case this time, so the acronym "NRC" can be matched as-is.
        batch = PASS_1_INCIDENTS[5]
        combined = " ".join(ev["content"] for ev in batch).upper()
        # --- The action and the verdict ------------------------------------
        assert "NRC" in combined or "RECALL" in combined or "REGULATORY" in combined


# ===========================================================================
# ACT II — THE GUARD, AGAIN
# Guard tests (identical to MCAS repo — guards are domain-agnostic)
# The guard knows nothing about radiation machines or aircraft; these checks
# repeat a subset of tests/test_guards.py to show it behaves the same here.
# ===========================================================================

class TestGuards:
    """Domain-agnostic checks on check_transition() and next_valid_state()."""

    # -----------------------------------------------------------------------
    # ACT II, SCENE 1 — FORWARD, ONE STEP AT A TIME
    # Proves: all three single forward steps are allowed.
    # -----------------------------------------------------------------------
    def test_valid_forward_chain(self):
        """
        OPEN→TRAJECTORY, TRAJECTORY→AUTHORITY and AUTHORITY→EXECUTION pass.

        Enter:   self   unused
        Exit:    passes if the guard allows all three
        """
        # PLAYERS IN THIS SCENE
        #   chain      the three legal (current, next) pairs
        #   cur, nxt   one pair, unpacked per loop pass
        #   allowed    the guard's verdict (`_` discards the reason text)

        # --- Setting the stage ---------------------------------------------
        chain = [
            (CommitmentState.OPEN,       CommitmentState.TRAJECTORY),
            (CommitmentState.TRAJECTORY, CommitmentState.AUTHORITY),
            (CommitmentState.AUTHORITY,  CommitmentState.EXECUTION),
        ]
        # --- The action and the verdict, once per pair ---------------------
        for cur, nxt in chain:
            allowed, _ = check_transition(cur, nxt)
            assert allowed

    # -----------------------------------------------------------------------
    # ACT II, SCENE 2 — EVERY FORBIDDEN DOOR
    # Proves: the three named backward moves and one skip are all refused.
    # -----------------------------------------------------------------------
    def test_all_blocked_transitions(self):
        """
        Four illegal moves are all refused by the guard.

        Enter:   self   unused
        Exit:    passes, or fails naming the move that was wrongly allowed
        """
        # PLAYERS IN THIS SCENE
        #   blocked           the four illegal (current, proposed) pairs
        #   cur, prop         one pair, unpacked per loop pass
        #   allowed, reason   the guard's verdict (reason is not checked here)

        # --- Setting the stage ---------------------------------------------
        blocked = [
            (CommitmentState.EXECUTION,  CommitmentState.TRAJECTORY),
            (CommitmentState.AUTHORITY,  CommitmentState.OPEN),
            (CommitmentState.TRAJECTORY, CommitmentState.OPEN),
            (CommitmentState.OPEN,       CommitmentState.AUTHORITY),  # skip
        ]
        # --- The action and the verdict, once per pair ---------------------
        for cur, prop in blocked:
            allowed, reason = check_transition(cur, prop)
            assert not allowed, f"Expected {cur}→{prop} to be blocked"

    # -----------------------------------------------------------------------
    # ACT II, SCENE 3 — THE ORDER OF THINGS
    # Proves: next_valid_state() steps through the four states, then None.
    # -----------------------------------------------------------------------
    def test_next_valid_state_sequence(self):
        """
        next_valid_state() returns the following state, or None at the end.

        Enter:   self   unused
        Exit:    passes if all four answers match the fixed state order
        """
        # --- Setting the stage / The action / The verdict, in one go -------
        assert next_valid_state(CommitmentState.OPEN)       == CommitmentState.TRAJECTORY
        assert next_valid_state(CommitmentState.TRAJECTORY) == CommitmentState.AUTHORITY
        assert next_valid_state(CommitmentState.AUTHORITY)  == CommitmentState.EXECUTION
        assert next_valid_state(CommitmentState.EXECUTION)  is None


# ===========================================================================
# ACT III — THE THREE CONDITIONS
# Can CCL-F's types express the three ACO (Adversarial Commitment Opacity)
# conditions using the Therac-25 facts?
#   C1  the formal state differs from the inferred (hidden) state
#   C2  important evidence existed but was suppressed
#   C3  the authority that could act was out of reach while a path was locked
# ===========================================================================

class TestACOConditions:
    """
    Tests that model the three ACO conditions against Therac-25 evidence.
    These do not call the LLM — they test the structural setup of the
    scenario to verify that conditions are present in the evidence record.
    """

    # -----------------------------------------------------------------------
    # ACT III, SCENE 1 — C1: SAYING ONE THING, DOING ANOTHER
    # Proves: an ACSEstimate can point to TRAJECTORY with high confidence
    # while the formal state is still OPEN.
    # -----------------------------------------------------------------------
    def test_c1_state_divergence_is_modelable(self):
        """
        C1: Formal state = OPEN (investigating); ACS inferred = TRAJECTORY
        (AECL committed to 'software is sufficient').
        ACSEstimate can represent this divergence.

        Enter:   self   unused
        Exit:    passes if the estimate's top state is TRAJECTORY, its
                 confidence is at least 0.7, and it differs from the formal state
        """
        # PLAYERS IN THIS SCENE
        #   formal_state   what AECL said publicly: still OPEN (investigating)
        #   acs            the hand-written estimate of AECL's real posture

        # --- Setting the stage ---------------------------------------------
        # These numbers are written by hand to represent the situation; no
        # model inferred them.
        formal_state = CommitmentState.OPEN
        acs = ACSEstimate(
            p_open=0.1,
            p_trajectory=0.75,   # AECL's actual internal posture
            p_authority=0.1,
            p_execution=0.05,
            confidence=0.8,
            reasoning=(
                "AECL's repeated 'no fault found' responses, combined with removal "
                "of hardware interlocks, indicate a committed trajectory that "
                "software-only interlocks are sufficient — despite public posture "
                "of ongoing investigation."
            ),
        )
        # --- The action and the verdict ------------------------------------
        assert acs.most_likely() == CommitmentState.TRAJECTORY
        assert acs.confidence >= 0.7  # C1 requires high confidence
        assert formal_state != acs.most_likely()  # Divergence present

    # -----------------------------------------------------------------------
    # ACT III, SCENE 2 — C2: THE MEMO IN THE DRAWER
    # Proves: the key suppressed documents t25-s1, -s2 and -s3 are in pass 2.
    # -----------------------------------------------------------------------
    def test_c2_suppressed_evidence_is_present(self):
        """
        C2: High-novelty, high-independence evidence exists (race condition memo)
        but was not disclosed. Evidence in Pass 2 includes items that were
        simultaneously available to AECL during Pass 1.

        Enter:   self   unused
        Exit:    passes if t25-s1, t25-s2 and t25-s3 are all in pass 2
        """
        # PLAYERS IN THIS SCENE
        #   suppression_ids   the set of every evidence_id in pass 2

        # --- Setting the stage ---------------------------------------------
        # The race condition finding (t25-s1) should have been disclosed
        # during Pass 1 incident responses — its presence in Pass 2 alone
        # is the C2 signal.
        # `{... for ev in ...}` with no colon is a *set* comprehension.
        suppression_ids = {ev["evidence_id"] for ev in PASS_2_SUPPRESSION}

        # --- The action and the verdict ------------------------------------
        assert "t25-s1" in suppression_ids, "Race condition memo must be in Pass 2"
        assert "t25-s2" in suppression_ids, "Engineering analysis must be in Pass 2"
        assert "t25-s3" in suppression_ids, "Contradiction with 'no fault' letters must be in Pass 2"

    # -----------------------------------------------------------------------
    # ACT III, SCENE 3 — C3: NOBODY TO APPEAL TO
    # Proves: an agent state can hold "trajectory locked, no approval
    # pathway" at the same time.
    # -----------------------------------------------------------------------
    def test_c3_authority_inaccessible_while_trajectory_locked(self):
        """
        C3: Hospitals had no access to AECL's internal review process.
        The authority that could have halted operations (AECL engineering)
        was inaccessible to the operators reporting incidents.
        Modelled as: ACS_TRAJECTORY high confidence + no human_approval pathway.

        Enter:   self   unused
        Exit:    passes if the state reads back as TRAJECTORY with no approval

        Note: this sets the fields by hand and reads them back. It shows the
        state can represent C3; it does not run any detection logic.
        """
        # PLAYERS IN THIS SCENE
        #   state                 a fresh agent state, edited by hand
        #   trajectory_locked     True if the state is TRAJECTORY
        #   no_approval_pathway   True if no human approval has been recorded

        # --- Setting the stage ---------------------------------------------
        state = CCLFAgentState()
        state.commitment_state = CommitmentState.TRAJECTORY
        state.human_approval   = None   # No approval pathway established
        state.aco_detected     = False  # Not yet detected

        # --- The action ----------------------------------------------------
        # Simulate the C3 condition: trajectory locked, no authority accessible
        trajectory_locked     = state.commitment_state == CommitmentState.TRAJECTORY
        no_approval_pathway   = state.human_approval is None

        # --- The verdict ---------------------------------------------------
        assert trajectory_locked
        assert no_approval_pathway


# ===========================================================================
# ACT IV — THE RECORD
# Does the hash-chained audit log stay unbroken across a full two-pass run?
# ===========================================================================

class TestAuditChain:
    """End-to-end check of the audit hash chain using Therac-25 events."""

    # -----------------------------------------------------------------------
    # ACT IV, SCENE 1 — TWO PASSES, ONE CHAIN
    # Proves: after logging every pass-1 incident, every pass-2 document and
    # two closing events, every entry links to the one before it.
    # -----------------------------------------------------------------------
    def test_chain_integrity_across_two_passes(self):
        """
        Simulate adding audit entries across a two-pass run and verify
        the chain remains intact end-to-end.

        Enter:   self   unused
        Exit:    passes if the entry count is right and no link is broken
        """
        # PLAYERS IN THIS SCENE
        #   state   a fresh agent state whose audit log we fill
        #   i       loop counter (first for incidents, later for log positions)
        #   ev      one pass-2 evidence dict
        #   n       total number of audit entries written

        # --- Setting the stage ---------------------------------------------
        state = CCLFAgentState()

        # --- The action: write the events of a whole run -------------------
        # Pass 1 events
        for i in range(6):
            state.append_audit(f"INCIDENT_{i+1}_PROCESSED", {"batch": i+1})

        # Pass 2 events
        for ev in PASS_2_SUPPRESSION:
            state.append_audit("SUPPRESSION_EVIDENCE_SCORED", {
                "evidence_id": ev["evidence_id"]
            })

        state.append_audit("ACO_DETECTED", {"conditions": ["C1", "C2", "C3"]})
        state.append_audit("SESSION_END",  {"final_state": "TRAJECTORY"})

        # --- The verdict: the right number of entries ----------------------
        # 6 incidents + one per pass-2 document + the 2 closing events.
        n = len(state.audit_log)
        assert n == 6 + len(PASS_2_SUPPRESSION) + 2

        # --- The verdict: every link holds ---------------------------------
        # Verify full chain
        assert state.audit_log[0].prev_hash == "GENESIS"
        for i in range(1, n):
            assert state.audit_log[i].prev_hash == state.audit_log[i-1].entry_hash, (
                f"Chain broken at entry {i}"
            )

# EXEUNT — end of file.

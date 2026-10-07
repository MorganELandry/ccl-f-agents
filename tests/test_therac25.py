"""
Tests for Therac-25 scenario structure and CCL-F core logic.
No LLM calls required.

Run: pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from cclf.types import CommitmentState, Evidence, ACSEstimate, CCLFAgentState, AuditEntry
from cclf.guards import check_transition, next_valid_state
from scenarios.therac25 import PASS_1_INCIDENTS, PASS_2_SUPPRESSION


# ---------------------------------------------------------------------------
# Scenario structure
# ---------------------------------------------------------------------------

class TestTherac25ScenarioStructure:

    def test_pass1_has_six_incident_batches(self):
        assert len(PASS_1_INCIDENTS) == 6, (
            "Therac-25 had six confirmed overdose incidents"
        )

    def test_each_incident_has_at_least_one_evidence_item(self):
        for idx, batch in enumerate(PASS_1_INCIDENTS):
            assert len(batch) >= 1, f"Incident batch {idx+1} is empty"

    def test_pass2_has_suppression_documents(self):
        assert len(PASS_2_SUPPRESSION) >= 4, (
            "Pass 2 should include race condition memo, 'no fault' letters, "
            "engineering analysis, and recall notice"
        )

    def test_all_evidence_ids_unique_across_passes(self):
        all_ids = []
        for batch in PASS_1_INCIDENTS:
            for ev in batch:
                all_ids.append(ev["evidence_id"])
        for ev in PASS_2_SUPPRESSION:
            all_ids.append(ev["evidence_id"])
        assert len(all_ids) == len(set(all_ids)), "Duplicate evidence IDs detected"

    def test_all_evidence_has_required_fields(self):
        required = {"evidence_id", "content", "source"}
        for batch in PASS_1_INCIDENTS:
            for ev in batch:
                missing = required - set(ev.keys())
                assert not missing, f"Evidence {ev.get('evidence_id')} missing: {missing}"
        for ev in PASS_2_SUPPRESSION:
            missing = required - set(ev.keys())
            assert not missing, f"Evidence {ev.get('evidence_id')} missing: {missing}"

    def test_pass2_contains_race_condition_evidence(self):
        """The race condition finding must be present — it's the core ACO signal."""
        combined = " ".join(ev["content"] for ev in PASS_2_SUPPRESSION).lower()
        assert "race condition" in combined

    def test_pass2_contains_no_fault_found_reference(self):
        """'No fault found' letters are the ACO mechanism."""
        combined = " ".join(ev["content"] for ev in PASS_2_SUPPRESSION).lower()
        assert "no fault" in combined or "no hardware" in combined

    def test_incident_4_contains_proceed_keypress(self):
        """
        The 'proceed through pause' operator behaviour in Incident 4 is
        CCL-F-relevant: trained procedure converted a safety pause into a hazard.
        """
        batch = PASS_1_INCIDENTS[3]  # 0-indexed, Incident 4
        combined = " ".join(ev["content"] for ev in batch).lower()
        assert "proceed" in combined or "keypress" in combined or "'p'" in combined.lower()

    def test_incident_6_triggers_regulatory_action(self):
        """Incident 6 should reference NRC — the first external authority closure."""
        batch = PASS_1_INCIDENTS[5]
        combined = " ".join(ev["content"] for ev in batch).upper()
        assert "NRC" in combined or "RECALL" in combined or "REGULATORY" in combined


# ---------------------------------------------------------------------------
# Guard tests (identical to MCAS repo — guards are domain-agnostic)
# ---------------------------------------------------------------------------

class TestGuards:

    def test_valid_forward_chain(self):
        chain = [
            (CommitmentState.OPEN,       CommitmentState.TRAJECTORY),
            (CommitmentState.TRAJECTORY, CommitmentState.AUTHORITY),
            (CommitmentState.AUTHORITY,  CommitmentState.EXECUTION),
        ]
        for cur, nxt in chain:
            allowed, _ = check_transition(cur, nxt)
            assert allowed

    def test_all_blocked_transitions(self):
        blocked = [
            (CommitmentState.EXECUTION,  CommitmentState.TRAJECTORY),
            (CommitmentState.AUTHORITY,  CommitmentState.OPEN),
            (CommitmentState.TRAJECTORY, CommitmentState.OPEN),
            (CommitmentState.OPEN,       CommitmentState.AUTHORITY),  # skip
        ]
        for cur, prop in blocked:
            allowed, reason = check_transition(cur, prop)
            assert not allowed, f"Expected {cur}→{prop} to be blocked"

    def test_next_valid_state_sequence(self):
        assert next_valid_state(CommitmentState.OPEN)       == CommitmentState.TRAJECTORY
        assert next_valid_state(CommitmentState.TRAJECTORY) == CommitmentState.AUTHORITY
        assert next_valid_state(CommitmentState.AUTHORITY)  == CommitmentState.EXECUTION
        assert next_valid_state(CommitmentState.EXECUTION)  is None


# ---------------------------------------------------------------------------
# ACO condition modelling
# ---------------------------------------------------------------------------

class TestACOConditions:
    """
    Tests that model the three ACO conditions against Therac-25 evidence.
    These do not call the LLM — they test the structural setup of the
    scenario to verify that conditions are present in the evidence record.
    """

    def test_c1_state_divergence_is_modelable(self):
        """
        C1: Formal state = OPEN (investigating); ACS inferred = TRAJECTORY
        (AECL committed to 'software is sufficient').
        ACSEstimate can represent this divergence.
        """
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
        assert acs.most_likely() == CommitmentState.TRAJECTORY
        assert acs.confidence >= 0.7  # C1 requires high confidence
        assert formal_state != acs.most_likely()  # Divergence present

    def test_c2_suppressed_evidence_is_present(self):
        """
        C2: High-novelty, high-independence evidence exists (race condition memo)
        but was not disclosed. Evidence in Pass 2 includes items that were
        simultaneously available to AECL during Pass 1.
        """
        # The race condition finding (t25-s1) should have been disclosed
        # during Pass 1 incident responses — its presence in Pass 2 alone
        # is the C2 signal.
        suppression_ids = {ev["evidence_id"] for ev in PASS_2_SUPPRESSION}
        assert "t25-s1" in suppression_ids, "Race condition memo must be in Pass 2"
        assert "t25-s2" in suppression_ids, "Engineering analysis must be in Pass 2"
        assert "t25-s3" in suppression_ids, "Contradiction with 'no fault' letters must be in Pass 2"

    def test_c3_authority_inaccessible_while_trajectory_locked(self):
        """
        C3: Hospitals had no access to AECL's internal review process.
        The authority that could have halted operations (AECL engineering)
        was inaccessible to the operators reporting incidents.
        Modelled as: ACS_TRAJECTORY high confidence + no human_approval pathway.
        """
        state = CCLFAgentState()
        state.commitment_state = CommitmentState.TRAJECTORY
        state.human_approval   = None   # No approval pathway established
        state.aco_detected     = False  # Not yet detected

        # Simulate the C3 condition: trajectory locked, no authority accessible
        trajectory_locked     = state.commitment_state == CommitmentState.TRAJECTORY
        no_approval_pathway   = state.human_approval is None

        assert trajectory_locked
        assert no_approval_pathway


# ---------------------------------------------------------------------------
# Audit chain
# ---------------------------------------------------------------------------

class TestAuditChain:

    def test_chain_integrity_across_two_passes(self):
        """
        Simulate adding audit entries across a two-pass run and verify
        the chain remains intact end-to-end.
        """
        state = CCLFAgentState()

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

        n = len(state.audit_log)
        assert n == 6 + len(PASS_2_SUPPRESSION) + 2

        # Verify full chain
        assert state.audit_log[0].prev_hash == "GENESIS"
        for i in range(1, n):
            assert state.audit_log[i].prev_hash == state.audit_log[i-1].entry_hash, (
                f"Chain broken at entry {i}"
            )

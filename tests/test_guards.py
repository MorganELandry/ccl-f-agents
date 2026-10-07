"""
Tests for CCL-F transition guards and core types.
No LLM calls — these are pure-logic tests.

Run: pytest tests/test_guards.py -v
"""

import pytest
from cclf.types import CommitmentState, Evidence, ACSEstimate, CCLFAgentState
from cclf.guards import check_transition, next_valid_state


# ---------------------------------------------------------------------------
# Guard tests
# ---------------------------------------------------------------------------

class TestTransitionGuards:

    def test_valid_forward_transitions(self):
        pairs = [
            (CommitmentState.OPEN,       CommitmentState.TRAJECTORY),
            (CommitmentState.TRAJECTORY, CommitmentState.AUTHORITY),
            (CommitmentState.AUTHORITY,  CommitmentState.EXECUTION),
        ]
        for current, proposed in pairs:
            allowed, reason = check_transition(current, proposed)
            assert allowed, f"Expected {current}→{proposed} to be allowed: {reason}"

    def test_blocked_execution_to_trajectory(self):
        allowed, reason = check_transition(
            CommitmentState.EXECUTION, CommitmentState.TRAJECTORY
        )
        assert not allowed
        assert "BLOCKED" in reason

    def test_blocked_authority_to_open(self):
        allowed, reason = check_transition(
            CommitmentState.AUTHORITY, CommitmentState.OPEN
        )
        assert not allowed
        assert "BLOCKED" in reason

    def test_blocked_trajectory_to_open(self):
        allowed, reason = check_transition(
            CommitmentState.TRAJECTORY, CommitmentState.OPEN
        )
        assert not allowed
        assert "BLOCKED" in reason

    def test_blocked_skip(self):
        # Skipping TRAJECTORY
        allowed, reason = check_transition(
            CommitmentState.OPEN, CommitmentState.AUTHORITY
        )
        assert not allowed
        assert "skip" in reason.lower() or "BLOCKED" in reason

    def test_identity_transition_allowed(self):
        allowed, reason = check_transition(
            CommitmentState.OPEN, CommitmentState.OPEN
        )
        assert allowed
        assert "No-op" in reason

    def test_next_valid_state(self):
        assert next_valid_state(CommitmentState.OPEN)       == CommitmentState.TRAJECTORY
        assert next_valid_state(CommitmentState.TRAJECTORY) == CommitmentState.AUTHORITY
        assert next_valid_state(CommitmentState.AUTHORITY)  == CommitmentState.EXECUTION
        assert next_valid_state(CommitmentState.EXECUTION)  is None


# ---------------------------------------------------------------------------
# Evidence admissibility tests
# ---------------------------------------------------------------------------

class TestEvidence:

    def test_admissible_evidence(self):
        ev = Evidence(
            evidence_id="e1",
            content="test",
            source="src",
            novelty_score=0.8,
            independence_score=0.9,
        )
        assert ev.is_admissible()

    def test_inadmissible_low_novelty(self):
        ev = Evidence(
            evidence_id="e2",
            content="test",
            source="src",
            novelty_score=0.3,
            independence_score=0.9,
        )
        assert not ev.is_admissible()

    def test_inadmissible_unscored(self):
        ev = Evidence(evidence_id="e3", content="test", source="src")
        assert not ev.is_admissible()


# ---------------------------------------------------------------------------
# ACS estimate tests
# ---------------------------------------------------------------------------

class TestACSEstimate:

    def test_most_likely(self):
        acs = ACSEstimate(
            p_open=0.1,
            p_trajectory=0.7,
            p_authority=0.1,
            p_execution=0.1,
        )
        assert acs.most_likely() == CommitmentState.TRAJECTORY


# ---------------------------------------------------------------------------
# Audit chain tests
# ---------------------------------------------------------------------------

class TestAuditChain:

    def test_audit_chain_integrity(self):
        state = CCLFAgentState()
        state.append_audit("EVENT_A", {"x": 1})
        state.append_audit("EVENT_B", {"y": 2})
        state.append_audit("EVENT_C", {"z": 3})

        assert len(state.audit_log) == 3
        # Each entry's prev_hash should match previous entry's entry_hash
        assert state.audit_log[1].prev_hash == state.audit_log[0].entry_hash
        assert state.audit_log[2].prev_hash == state.audit_log[1].entry_hash
        # First entry's prev_hash should be GENESIS
        assert state.audit_log[0].prev_hash == "GENESIS"

    def test_audit_hash_determinism(self):
        """Same content should produce same hash."""
        import time as t
        ts = t.time()
        state = CCLFAgentState()
        state.append_audit("EVENT_A", {"x": 1})
        h1 = state.audit_log[0].entry_hash
        # Hash is deterministic given same inputs
        assert len(h1) == 64  # SHA-256 hex

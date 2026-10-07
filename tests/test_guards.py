"""
THE GUARD ON TRIAL
A Play in Four Acts
===================

PROLOGUE
--------
Tests for CCL-F transition guards and core types.
No LLM calls — these are pure-logic tests.

This file checks the smallest, most important pieces of the system, one at a
time, with no language model, no network and no graph involved:

  - the transition guard in cclf/guards.py (which state moves are legal),
  - the Evidence admissibility rule in cclf/types.py,
  - the ACSEstimate "which state is most likely?" helper,
  - the hash-chained audit log kept by CCLFAgentState.

Because everything here is deterministic, a failure in this file always
means the code changed behaviour, never that a model had a bad day.

Run: pytest tests/test_guards.py -v

THE PLAYBILL
    Act I    TestTransitionGuards   which commitment-state moves are allowed
      Scene 1  test_valid_forward_transitions   each single forward step passes
      Scene 2  test_blocked_execution_to_trajectory   EXECUTION → TRAJECTORY refused
      Scene 3  test_blocked_authority_to_open         AUTHORITY → OPEN refused
      Scene 4  test_blocked_trajectory_to_open        TRAJECTORY → OPEN refused
      Scene 5  test_blocked_skip                      OPEN → AUTHORITY refused
      Scene 6  test_identity_transition_allowed       staying put is a no-op
      Scene 7  test_next_valid_state                  the "next step" helper
    Act II   TestEvidence           when a piece of evidence counts
      Scene 1  test_admissible_evidence
      Scene 2  test_inadmissible_low_novelty
      Scene 3  test_inadmissible_unscored
    Act III  TestACSEstimate        picking the most probable state
      Scene 1  test_most_likely
    Act IV   TestAuditChain         the tamper-evident audit log
      Scene 1  test_audit_chain_integrity
      Scene 2  test_audit_hash_determinism

READER'S NOTE — how pytest finds and runs these tests ("test discovery")
    You never call these functions yourself. When you run `pytest`, it walks
    the tests/ folder and collects, by naming convention:
      - files whose names start with `test_`        (test_guards.py)
      - inside them, functions named `test_*`
      - and classes named `Test*` (with no __init__ method); every method
        named `test_*` inside such a class is a separate test.
    pytest creates a fresh instance of the class for each test method, so
    tests inside one class do not share data. Here the classes are only a way
    of grouping related tests under one heading: that is why every method
    takes `self` but never uses it.

READER'S NOTE — `assert`
    `assert <condition>` is plain Python: if the condition is false it raises
    AssertionError. pytest catches that, marks the test as failed, and
    rewrites the assert so the failure report shows the actual values on
    both sides (for example `assert 2 == 3`). An optional message after a
    comma (`assert ok, "why it failed"`) is printed too. A test passes if it
    finishes without any exception.

READER'S NOTE — how `from cclf...` works inside tests/
    These files live in tests/, but they import the `cclf` package that lives
    one folder up. That works because of pytest.ini at the repo root:

        [pytest]
        pythonpath = . tests

    pytest adds each listed folder (relative to pytest.ini) to `sys.path`,
    the list of places Python searches when you write `import something`.
    "." (the repo root) makes `cclf`, `scenarios` and `evals` importable;
    "tests" lets one test file import a helper from another (see
    test_checkpoint.py, which borrows `scripted_llm` from test_end_to_end.py).
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       the test runner. Imported here by habit; nothing in this file
#              actually calls a `pytest.` helper.
# cclf.types   the data classes under test: the four CommitmentStates,
#              Evidence, ACSEstimate, and the agent state with its audit log.
# cclf.guards  the deterministic transition guard under test (the model
#              file for this repo's commenting style).
# ===========================================================================

import pytest
from cclf.types import CommitmentState, Evidence, ACSEstimate, CCLFAgentState
from cclf.guards import check_transition, next_valid_state


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# (none) — this file defines only test classes; each test builds the data it
# needs inside its own body, so no test can leak state into another.
# ===========================================================================


# ===========================================================================
# ACT I — THE TRANSITION GUARDS
# Does check_transition() allow exactly the moves CCL-F permits, and no others?
# ===========================================================================

class TestTransitionGuards:
    """
    Group of tests for cclf.guards.check_transition() and next_valid_state().

    Each method calls the guard with a (current, proposed) pair and checks
    both halves of its answer: the True/False verdict and the reason text.
    """

    # -----------------------------------------------------------------------
    # ACT I, SCENE 1 — THE HAPPY PATH
    # Proves: every single forward step (OPEN→TRAJECTORY→AUTHORITY→EXECUTION)
    # is allowed.
    # -----------------------------------------------------------------------
    def test_valid_forward_transitions(self):
        """
        Each of the three legal one-step forward moves is allowed.

        Enter:   self   unused (pytest supplies it because this is a method)
        Exit:    passes silently, or fails naming the move that was refused
        """
        # PLAYERS IN THIS SCENE
        #   pairs              the three legal (current, proposed) moves
        #   current, proposed  one pair, unpacked on each loop pass
        #   allowed, reason    the guard's verdict for that pair

        # --- Setting the stage ---------------------------------------------
        # The full list of legal moves; there are only three.
        pairs = [
            (CommitmentState.OPEN,       CommitmentState.TRAJECTORY),
            (CommitmentState.TRAJECTORY, CommitmentState.AUTHORITY),
            (CommitmentState.AUTHORITY,  CommitmentState.EXECUTION),
        ]
        # --- The action and the verdict, once per pair ---------------------
        # `for current, proposed in pairs` unpacks each 2-tuple into two names.
        # The f-string message is only shown if the assert fails, and it
        # includes the guard's own reason so the failure explains itself.
        for current, proposed in pairs:
            allowed, reason = check_transition(current, proposed)
            assert allowed, f"Expected {current}→{proposed} to be allowed: {reason}"

    # -----------------------------------------------------------------------
    # ACT I, SCENE 2 — NO UN-SPENDING
    # Proves: EXECUTION → TRAJECTORY is refused, with a "BLOCKED" reason.
    # -----------------------------------------------------------------------
    def test_blocked_execution_to_trajectory(self):
        """
        Moving from EXECUTION back to TRAJECTORY is refused.

        Enter:   self   unused
        Exit:    passes if the guard says no and the reason says "BLOCKED"
        """
        # PLAYERS IN THIS SCENE
        #   allowed, reason   the guard's verdict and its explanation

        # --- Setting the stage / The action --------------------------------
        # One of the three named pairs in guards._BLOCKED.
        allowed, reason = check_transition(
            CommitmentState.EXECUTION, CommitmentState.TRAJECTORY
        )
        # --- The verdict ---------------------------------------------------
        assert not allowed
        assert "BLOCKED" in reason

    # -----------------------------------------------------------------------
    # ACT I, SCENE 3 — A DECISION STAYS MADE
    # Proves: AUTHORITY → OPEN is refused, with a "BLOCKED" reason.
    # -----------------------------------------------------------------------
    def test_blocked_authority_to_open(self):
        """
        Moving from AUTHORITY back to OPEN is refused.

        Enter:   self   unused
        Exit:    passes if the guard says no and the reason says "BLOCKED"
        """
        # PLAYERS IN THIS SCENE
        #   allowed, reason   the guard's verdict and its explanation

        # --- Setting the stage / The action --------------------------------
        allowed, reason = check_transition(
            CommitmentState.AUTHORITY, CommitmentState.OPEN
        )
        # --- The verdict ---------------------------------------------------
        assert not allowed
        assert "BLOCKED" in reason

    # -----------------------------------------------------------------------
    # ACT I, SCENE 4 — A LOCKED PATH STAYS LOCKED
    # Proves: TRAJECTORY → OPEN is refused, with a "BLOCKED" reason.
    # -----------------------------------------------------------------------
    def test_blocked_trajectory_to_open(self):
        """
        Moving from TRAJECTORY back to OPEN is refused.

        Enter:   self   unused
        Exit:    passes if the guard says no and the reason says "BLOCKED"
        """
        # PLAYERS IN THIS SCENE
        #   allowed, reason   the guard's verdict and its explanation

        # --- Setting the stage / The action --------------------------------
        allowed, reason = check_transition(
            CommitmentState.TRAJECTORY, CommitmentState.OPEN
        )
        # --- The verdict ---------------------------------------------------
        assert not allowed
        assert "BLOCKED" in reason

    # -----------------------------------------------------------------------
    # ACT I, SCENE 5 — NO JUMPING THE QUEUE
    # Proves: OPEN → AUTHORITY (skipping TRAJECTORY) is refused.
    # -----------------------------------------------------------------------
    def test_blocked_skip(self):
        """
        Jumping two states forward in one move is refused.

        Enter:   self   unused
        Exit:    passes if the guard says no and the reason mentions a skip
                 (or says "BLOCKED")
        """
        # PLAYERS IN THIS SCENE
        #   allowed, reason   the guard's verdict and its explanation

        # --- Setting the stage / The action --------------------------------
        # Skipping TRAJECTORY
        allowed, reason = check_transition(
            CommitmentState.OPEN, CommitmentState.AUTHORITY
        )
        # --- The verdict ---------------------------------------------------
        # The guard's skip message contains both "BLOCKED" and "skips", so
        # either check would pass; `.lower()` makes the "skip" check
        # case-insensitive.
        assert not allowed
        assert "skip" in reason.lower() or "BLOCKED" in reason

    # -----------------------------------------------------------------------
    # ACT I, SCENE 6 — STANDING STILL
    # Proves: proposing the state you are already in is allowed as a no-op.
    # -----------------------------------------------------------------------
    def test_identity_transition_allowed(self):
        """
        A "move" from a state to itself is allowed and labelled a no-op.

        Enter:   self   unused
        Exit:    passes if the guard says yes and the reason says "No-op"
        """
        # PLAYERS IN THIS SCENE
        #   allowed, reason   the guard's verdict and its explanation

        # --- Setting the stage / The action --------------------------------
        allowed, reason = check_transition(
            CommitmentState.OPEN, CommitmentState.OPEN
        )
        # --- The verdict ---------------------------------------------------
        assert allowed
        assert "No-op" in reason

    # -----------------------------------------------------------------------
    # ACT I, SCENE 7 — WHAT COMES NEXT
    # Proves: next_valid_state() walks the four states in order and returns
    # None after the last one.
    # -----------------------------------------------------------------------
    def test_next_valid_state(self):
        """
        next_valid_state() returns the following state, or None at the end.

        Enter:   self   unused
        Exit:    passes if all four answers match the fixed state order
        """
        # --- Setting the stage / The action / The verdict, in one go -------
        # Each line calls the helper and checks its answer. `is None` (rather
        # than `== None`) is the Python idiom for testing for None.
        assert next_valid_state(CommitmentState.OPEN)       == CommitmentState.TRAJECTORY
        assert next_valid_state(CommitmentState.TRAJECTORY) == CommitmentState.AUTHORITY
        assert next_valid_state(CommitmentState.AUTHORITY)  == CommitmentState.EXECUTION
        assert next_valid_state(CommitmentState.EXECUTION)  is None


# ===========================================================================
# ACT II — THE EVIDENCE
# When does a piece of evidence count (is it "admissible")?
# Evidence.is_admissible() requires BOTH novelty_score and independence_score
# to be set and to be at least 0.5.
# ===========================================================================

class TestEvidence:
    """Group of tests for Evidence.is_admissible() in cclf/types.py."""

    # -----------------------------------------------------------------------
    # ACT II, SCENE 1 — A GOOD WITNESS
    # Proves: evidence with both scores above 0.5 is admissible.
    # -----------------------------------------------------------------------
    def test_admissible_evidence(self):
        """
        Evidence scored 0.8 novelty / 0.9 independence is admissible.

        Enter:   self   unused
        Exit:    passes if is_admissible() returns True
        """
        # PLAYERS IN THIS SCENE
        #   ev   the Evidence object under test

        # --- Setting the stage ---------------------------------------------
        # Keyword arguments name each dataclass field explicitly; the
        # timestamp field is left to its default (the current time).
        ev = Evidence(
            evidence_id="e1",
            content="test",
            source="src",
            novelty_score=0.8,
            independence_score=0.9,
        )
        # --- The action and the verdict ------------------------------------
        assert ev.is_admissible()

    # -----------------------------------------------------------------------
    # ACT II, SCENE 2 — OLD NEWS
    # Proves: one low score (novelty 0.3) is enough to reject evidence, even
    # when the other score is high.
    # -----------------------------------------------------------------------
    def test_inadmissible_low_novelty(self):
        """
        Evidence with novelty below 0.5 is not admissible.

        Enter:   self   unused
        Exit:    passes if is_admissible() returns False
        """
        # PLAYERS IN THIS SCENE
        #   ev   the Evidence object under test

        # --- Setting the stage ---------------------------------------------
        ev = Evidence(
            evidence_id="e2",
            content="test",
            source="src",
            novelty_score=0.3,
            independence_score=0.9,
        )
        # --- The action and the verdict ------------------------------------
        assert not ev.is_admissible()

    # -----------------------------------------------------------------------
    # ACT II, SCENE 3 — NOT YET HEARD
    # Proves: evidence that has never been scored is not admissible.
    # -----------------------------------------------------------------------
    def test_inadmissible_unscored(self):
        """
        Evidence with no scores at all is not admissible.

        Enter:   self   unused
        Exit:    passes if is_admissible() returns False

        Both scores default to None ("not yet evaluated by the LLM"), and
        is_admissible() treats None as a failure rather than crashing.
        """
        # PLAYERS IN THIS SCENE
        #   ev   the Evidence object under test

        # --- Setting the stage ---------------------------------------------
        ev = Evidence(evidence_id="e3", content="test", source="src")
        # --- The action and the verdict ------------------------------------
        assert not ev.is_admissible()


# ===========================================================================
# ACT III — THE ESTIMATE
# Does ACSEstimate.most_likely() pick the state with the highest probability?
# ===========================================================================

class TestACSEstimate:
    """Group of tests for ACSEstimate in cclf/types.py."""

    # -----------------------------------------------------------------------
    # ACT III, SCENE 1 — THE FRONT-RUNNER
    # Proves: with TRAJECTORY at 0.7 and the rest at 0.1, TRAJECTORY wins.
    # -----------------------------------------------------------------------
    def test_most_likely(self):
        """
        most_likely() returns the state with the largest probability.

        Enter:   self   unused
        Exit:    passes if the answer is CommitmentState.TRAJECTORY
        """
        # PLAYERS IN THIS SCENE
        #   acs   the probability distribution under test

        # --- Setting the stage ---------------------------------------------
        acs = ACSEstimate(
            p_open=0.1,
            p_trajectory=0.7,
            p_authority=0.1,
            p_execution=0.1,
        )
        # --- The action and the verdict ------------------------------------
        assert acs.most_likely() == CommitmentState.TRAJECTORY


# ===========================================================================
# ACT IV — THE AUDIT CHAIN
# Is the audit log a proper hash chain?
# Each AuditEntry stores the previous entry's hash (prev_hash) and a SHA-256
# hash of its own contents (entry_hash). Linking them this way means editing
# any old entry would break every link after it: "tamper-evident".
# ===========================================================================

class TestAuditChain:
    """Group of tests for CCLFAgentState.append_audit() and AuditEntry hashing."""

    # -----------------------------------------------------------------------
    # ACT IV, SCENE 1 — THE LINKS HOLD
    # Proves: each entry's prev_hash equals the entry_hash before it, and the
    # first entry points at the fixed marker "GENESIS".
    # -----------------------------------------------------------------------
    def test_audit_chain_integrity(self):
        """
        Three appended audit entries form an unbroken hash chain.

        Enter:   self   unused
        Exit:    passes if the log has 3 entries linked in order
        """
        # PLAYERS IN THIS SCENE
        #   state   a fresh agent state whose audit log we fill

        # --- Setting the stage / The action --------------------------------
        # A brand-new state has an empty log; append three events to it.
        state = CCLFAgentState()
        state.append_audit("EVENT_A", {"x": 1})
        state.append_audit("EVENT_B", {"y": 2})
        state.append_audit("EVENT_C", {"z": 3})

        # --- The verdict ---------------------------------------------------
        assert len(state.audit_log) == 3
        # Each entry's prev_hash should match previous entry's entry_hash
        assert state.audit_log[1].prev_hash == state.audit_log[0].entry_hash
        assert state.audit_log[2].prev_hash == state.audit_log[1].entry_hash
        # First entry's prev_hash should be GENESIS
        assert state.audit_log[0].prev_hash == "GENESIS"

    # -----------------------------------------------------------------------
    # ACT IV, SCENE 2 — THE SHAPE OF A HASH
    # Proves (as written): an entry's hash is a 64-character SHA-256 hex string.
    # -----------------------------------------------------------------------
    def test_audit_hash_determinism(self):
        """
        Same content should produce same hash.

        Enter:   self   unused
        Exit:    passes if the first entry's hash is 64 characters long

        Note for the reader: despite its name, this test does not build two
        entries and compare their hashes. It only checks the hash's length.
        The variable `ts` is created but never used. Determinism itself is
        exercised in test_checkpoint.py, where an entry rebuilt from its own
        fields must reproduce the same hash.
        """
        # PLAYERS IN THIS SCENE
        #   t       the standard `time` module, imported under a short alias
        #   ts      the current time in seconds (unused by the checks below)
        #   state   a fresh agent state with one audit entry
        #   h1      that entry's SHA-256 hash, as a hex string

        # --- Setting the stage ---------------------------------------------
        # `import time as t` inside a function is legal Python; the name `t`
        # exists only within this function.
        import time as t
        ts = t.time()
        state = CCLFAgentState()

        # --- The action ----------------------------------------------------
        state.append_audit("EVENT_A", {"x": 1})
        h1 = state.audit_log[0].entry_hash

        # --- The verdict ---------------------------------------------------
        # SHA-256 produces 32 bytes; written in hexadecimal, that is 64 chars.
        # Hash is deterministic given same inputs
        assert len(h1) == 64  # SHA-256 hex

# EXEUNT — end of file.

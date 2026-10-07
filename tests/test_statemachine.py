"""
THE MACHINE THAT SAYS NO
A Play in Nine Scenes
=====================

PROLOGUE
--------
Tests for cclf/statemachine.py, the commitment state machine of CCL-F v0.2
Layer 4 (spec lines ~870-946). Every expected value below is read off the
spec's transition listing, not off the code. The code's table is checked
against a copy of the spec listing typed out by hand in this file.

The spec says the machine's "blocked transitions are the supervisor's
forbidden-event set, enforced structurally rather than by convention"
(line 868). So these tests ask two kinds of question: is every listed
transition allowed, and is everything else (in particular the four
transitions the spec singles out, lines 935-940) refused?

THE PLAYBILL
    Scene 1   test_table_matches_spec_listing_exactly
    Scene 2   test_every_listed_transition_is_allowed
    Scene 3   test_cannot_close_before_classified           (parametrized, 2 runs)
    Scene 4   test_classified_cannot_close_before_review    (parametrized, 3 runs)
    Scene 5   test_suppressed_cannot_be_silently_closed     (parametrized, 3 runs)
    Scene 6   test_closed_loop_reopens_only_into_review
    Scene 7   test_review_cannot_open_before_classification
    Scene 8   test_trajectory_lock_is_terminal
    Scene 9   test_exit_allowed_only_from_open_states

READER'S NOTE — @pytest.mark.parametrize
    `@pytest.mark.parametrize("name", [a, b, c])` runs the test once for
    each value in the list, passing it in as the argument `name`. Each run
    is reported as its own test, so one failing value does not hide the
    others.

READER'S NOTE — itertools.product
    `product(A, B)` yields every pair (a, b) with a from A and b from B. It
    is used in Scene 1 to walk every possible (from, to) state pair.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# itertools.product   every (from, to) pair of states (Scene 1).
# pytest              for @pytest.mark.parametrize.
# cclf.statemachine   the module under test:
#   TRANSITIONS        the code's (from, to) -> reason table
#   check_transition   (current, target) -> (allowed, reason)
#   exit_allowed       may a signal in this state exit?
# cclf.types          CommitmentState (aliased S) and CLOSED_STATES.
# ===========================================================================

from itertools import product

import pytest

from cclf.statemachine import TRANSITIONS, check_transition, exit_allowed
from cclf.types import CLOSED_STATES, CommitmentState as S


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# SPEC_LISTING — the transition listing of spec lines 875-892, typed out by
#   hand: the nine forward transitions, two recovery transitions and three
#   reopen transitions. Exits are listed separately in the spec (line 895)
#   and are tested in test_exits.py.
SPEC_LISTING = {
    (S.UNREGISTERED, S.REGISTERED),
    (S.REGISTERED, S.CLASSIFIED),
    (S.CLASSIFIED, S.UNDER_REVIEW),
    (S.UNDER_REVIEW, S.CLOSED_EVIDENCE),
    (S.UNDER_REVIEW, S.CLOSED_AUTHORITY),
    (S.UNDER_REVIEW, S.CLOSED_ROLE_SWITCH),
    (S.UNDER_REVIEW, S.SUPPRESSED),
    (S.UNDER_REVIEW, S.ESCALATED),
    (S.UNDER_REVIEW, S.TRAJECTORY_LOCK),
    (S.ESCALATED, S.UNDER_REVIEW),
    (S.SUPPRESSED, S.UNDER_REVIEW),
    (S.CLOSED_EVIDENCE, S.UNDER_REVIEW),
    (S.CLOSED_AUTHORITY, S.UNDER_REVIEW),
    (S.CLOSED_ROLE_SWITCH, S.UNDER_REVIEW),
}

# CLOSED — the three closed states as a sorted list, so parametrize gets a
#   stable order (sets have none).
CLOSED = sorted(CLOSED_STATES, key=lambda s: s.value)

# OPEN_STATES_PER_SPEC — states a signal is "open" in for exit purposes
#   (line 895 "any open state"): entered the system, not closed, not latched.
OPEN_STATES_PER_SPEC = [S.REGISTERED, S.CLASSIFIED, S.UNDER_REVIEW, S.SUPPRESSED,
                        S.ESCALATED]


# ===========================================================================
# SCENE 1 — THE SCRIPT AND THE PERFORMANCE AGREE
# Proves: the code's table is exactly the spec's listing; nothing added,
# nothing missing; and check_transition refuses every pair outside it.
# ===========================================================================

def test_table_matches_spec_listing_exactly():
    """
    TRANSITIONS has exactly the spec's fourteen non-exit transitions.

    Enter:   (nothing)
    Exit:    passes if the key set equals SPEC_LISTING and every other pair
             of states is refused by check_transition with a BLOCKED reason
    """
    # PLAYERS IN THIS SCENE
    #   a, b       one (from, to) pair of states
    #   ok, why    check_transition's answer for that pair

    # --- The verdict on the table itself -----------------------------------
    assert set(TRANSITIONS) == SPEC_LISTING
    # --- The verdict on everything not in it -------------------------------
    for a, b in product(S, S):
        ok, why = check_transition(a, b)
        assert ok == ((a, b) in SPEC_LISTING), (a, b)
        if not ok:
            assert why.startswith("BLOCKED")


# ===========================================================================
# SCENE 2 — EVERY LISTED LINE MAY BE SPOKEN
# Proves: each listed transition is allowed and carries the spec's condition.
# ===========================================================================

def test_every_listed_transition_is_allowed():
    """
    check_transition allows each transition in the spec listing, with a reason.

    Enter:   (nothing)
    Exit:    passes if allowed is True and a non-empty reason is given for
             every pair in SPEC_LISTING
    """
    # PLAYERS IN THIS SCENE
    #   pair      one (from, to) tuple from SPEC_LISTING
    #   ok, why   check_transition's answer

    for pair in SPEC_LISTING:
        ok, why = check_transition(*pair)
        assert ok and why, pair


# ===========================================================================
# SCENE 3 — BLOCKED: CLOSED BEFORE CLASSIFIED
# Proves: spec line 937, "A signal cannot be closed before it is classified".
# ===========================================================================

@pytest.mark.parametrize("before", [S.UNREGISTERED, S.REGISTERED])
def test_cannot_close_before_classified(before):
    """
    No closed state is reachable from unregistered or registered.

    Enter:   before   a pre-classification state
    Exit:    passes if the transition to each closed state is refused
    """
    # PLAYERS IN THIS SCENE
    #   closed    one of the three closed states
    #   ok, why   check_transition's answer

    for closed in CLOSED:
        ok, why = check_transition(before, closed)
        assert not ok and "BLOCKED" in why


# ===========================================================================
# SCENE 4 — BLOCKED: CLOSED BEFORE REVIEW
# Proves: spec line 938, "A classified signal cannot be closed before review
# opens".
# ===========================================================================

@pytest.mark.parametrize("closed", CLOSED)
def test_classified_cannot_close_before_review(closed):
    """
    classified -> any closed state is refused.

    Enter:   closed   one of the three closed states
    Exit:    passes if refused
    """
    ok, _ = check_transition(S.CLASSIFIED, closed)
    assert not ok


# ===========================================================================
# SCENE 5 — BLOCKED: THE SILENT CLOSE OF A SUPPRESSED SIGNAL
# Proves: spec line 939, "A suppressed signal cannot be silently closed";
# the only way on is the recovery transition back into review (line 887).
# ===========================================================================

@pytest.mark.parametrize("closed", CLOSED)
def test_suppressed_cannot_be_silently_closed(closed):
    """
    suppressed -> closed is refused; suppressed -> under_review is allowed.

    Enter:   closed   one of the three closed states
    Exit:    passes if the close is refused and re-entry to review allowed
    """
    assert not check_transition(S.SUPPRESSED, closed)[0]
    assert check_transition(S.SUPPRESSED, S.UNDER_REVIEW)[0]


# ===========================================================================
# SCENE 6 — A CLOSED LOOP HAS ONE DOOR
# Proves: lines 889-892 and 942: closed states are stable but not terminal;
# the only way out of any closed state is back into under_review.
# ===========================================================================

def test_closed_loop_reopens_only_into_review():
    """
    From each closed state, under_review is the one allowed target.

    Enter:   (nothing)
    Exit:    passes if, for every closed state, the allowed targets are
             exactly {under_review}
    """
    # PLAYERS IN THIS SCENE
    #   closed    one closed state
    #   allowed   the set of targets check_transition allows from it

    for closed in CLOSED:
        allowed = {t for t in S if check_transition(closed, t)[0]}
        assert allowed == {S.UNDER_REVIEW}


# ===========================================================================
# SCENE 7 — RULE 2 GUARDS THE REVIEW-ROOM DOOR
# Proves: line 876, "registered -> classified (Rule 2: required before
# review opens)": review cannot open straight from registered.
# ===========================================================================

def test_review_cannot_open_before_classification():
    """
    registered -> under_review is refused.

    Enter:   (nothing)
    Exit:    passes if refused
    """
    assert not check_transition(S.REGISTERED, S.UNDER_REVIEW)[0]


# ===========================================================================
# SCENE 8 — TRAJECTORY LOCK IS THE LAST STOP
# Proves: line 946, "The trajectory_lock state is terminal and distinct from
# closure": no transition leaves it and it is not a closed state.
# ===========================================================================

def test_trajectory_lock_is_terminal():
    """
    Nothing leaves trajectory_lock, and it is not one of the closed states.

    Enter:   (nothing)
    Exit:    passes if every target is refused and the lock is not closed
    """
    assert not any(check_transition(S.TRAJECTORY_LOCK, t)[0] for t in S)
    assert S.TRAJECTORY_LOCK not in CLOSED_STATES
    assert not exit_allowed(S.TRAJECTORY_LOCK)[0]


# ===========================================================================
# SCENE 9 — WHO MAY LEAVE BY THE SIDE DOOR
# Proves: line 895, "any open state -> exited(type)"; closed, locked and
# already-exited signals cannot exit.
# ===========================================================================

def test_exit_allowed_only_from_open_states():
    """
    exit_allowed is True exactly for the open states.

    Enter:   (nothing)
    Exit:    passes if, for every CommitmentState, exit_allowed matches
             membership in OPEN_STATES_PER_SPEC
    """
    # PLAYERS IN THIS SCENE
    #   state   every CommitmentState in turn

    for state in S:
        assert exit_allowed(state)[0] == (state in OPEN_STATES_PER_SPEC), state

# EXEUNT — end of file.

"""
THE TRANSITION GUARD
A Play in Two Scenes
====================

PROLOGUE
--------
Every CCL-F organization sits in one of four commitment states, and it can
only ever move forward through them, one step at a time:

    OPEN  →  TRAJECTORY  →  AUTHORITY  →  EXECUTION

Some moves are forbidden outright, because they describe something that
cannot happen in the real world:

    EXECUTION  → TRAJECTORY    you cannot un-spend money already spent
    AUTHORITY  → OPEN          a decision, once made, does not un-make itself
    TRAJECTORY → OPEN          a locked-in path does not reverse on its own
    any        → skip a state  no jumping ahead (OPEN → AUTHORITY is illegal)

This file is the bouncer at the door. Other parts of the program (the LLM
nodes in nodes.py) may *propose* a move. Only this file decides whether the
move is *allowed*.

Why does that matter? A language model is probabilistic: ask it the same
question twice and you may get two answers. Safety rules must not work that
way. So the guard is written as plain, deterministic Python with no LLM in
it at all. Same input, same answer, every time.

THE PLAYBILL (what happens in this file)
    Scene 1  check_transition()  May we move from state A to state B?
    Scene 2  next_valid_state()  What is the one legal next step from here?

READER'S NOTE
    "Deterministic" means the output depends only on the input. Nothing
    random, nothing remembered from earlier calls, nothing from the network.
    A function like that is also called a "pure function", and it is the
    easiest kind of code to test: see tests/test_guards.py.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# `from __future__ import annotations` lets us write type hints such as
# `CommitmentState | None` on older Python versions. It changes nothing at
# runtime; it only affects how hints are stored.
# ===========================================================================

from __future__ import annotations

from typing import Tuple

from .types import CommitmentState   # the four states, defined in types.py


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# A leading underscore (_STATE_ORDER) is a Python convention meaning
# "private to this file: other modules should not import or change this."
# ===========================================================================

# _STATE_ORDER — the four states in their only legal order.
#   Position in this list = how far along the organization is.
#   OPEN is position 0, EXECUTION is position 3.
_STATE_ORDER: list[CommitmentState] = [
    CommitmentState.OPEN,
    CommitmentState.TRAJECTORY,
    CommitmentState.AUTHORITY,
    CommitmentState.EXECUTION,
]

# _ORDINAL — a lookup table from a state to its position number.
#   Built from _STATE_ORDER with a "dict comprehension": for each
#   (index, state) pair that enumerate() hands us, store state → index.
#   Result: {OPEN: 0, TRAJECTORY: 1, AUTHORITY: 2, EXECUTION: 3}
#   We build it once here so we never have to search the list later.
_ORDINAL: dict[CommitmentState, int] = {s: i for i, s in enumerate(_STATE_ORDER)}

# _BLOCKED — the forbidden moves, written out by name.
#   Each entry is a tuple (from_state, to_state). It is a *set*, so asking
#   "is this pair in _BLOCKED?" is instant no matter how many pairs it holds.
#   Note: the backward and skip rules in Scene 1 would also catch these
#   three, but naming them separately gives a clearer error message for the
#   cases CCL-F cares about most.
_BLOCKED: set[Tuple[CommitmentState, CommitmentState]] = {
    (CommitmentState.EXECUTION,  CommitmentState.TRAJECTORY),
    (CommitmentState.AUTHORITY,  CommitmentState.OPEN),
    (CommitmentState.TRAJECTORY, CommitmentState.OPEN),
}


# ===========================================================================
# SCENE 1 — THE JUDGEMENT
# check_transition(): may the organization move from `current` to `proposed`?
# ===========================================================================

def check_transition(
    current: CommitmentState,
    proposed: CommitmentState,
) -> Tuple[bool, str]:
    """
    Decide whether a move between two commitment states is allowed.

    Enter:   current   the state the organization is in now
             proposed  the state someone (usually an LLM node) wants to move to
    Exit:    a pair (allowed, reason)
             allowed   True if the move is legal, False if it is blocked
             reason    a sentence explaining the verdict, written to the audit log

    The rules are checked in a fixed order, and the first rule that matches
    decides the answer:
      1. Staying put is always fine (a "no-op").
      2. A move named in _BLOCKED is refused.
      3. Moving backward is refused.
      4. Skipping a state is refused.
      5. Anything left is a single step forward: allowed.
    """
    # PLAYERS IN THIS SCENE (local variables, introduced here first)
    #   c_ord    position number of the current state  (0–3)
    #   p_ord    position number of the proposed state (0–3)
    #   skipped  the state that a too-big jump would leap over

    # --- Rule 1: no change requested -------------------------------------
    # Proposing the state we are already in is harmless. Allow it and move on.
    if current == proposed:
        return True, "No-op: already in target state."

    # --- Rule 2: a named, forbidden move ---------------------------------
    # `(current, proposed) in _BLOCKED` builds a tuple and asks the set
    # whether it contains it.
    if (current, proposed) in _BLOCKED:
        return False, (
            f"BLOCKED: transition {current} → {proposed} is structurally "
            f"prohibited by CCL-F. This pair represents an irreversible "
            f"commitment that cannot be undone by re-opening the loop."
        )

    # Turn both states into position numbers so we can compare them with
    # ordinary arithmetic (less than, difference, and so on).
    c_ord = _ORDINAL[current]
    p_ord = _ORDINAL[proposed]

    # --- Rule 3: moving backward -----------------------------------------
    # A smaller position number means an earlier state.
    if p_ord < c_ord:
        return False, (
            f"BLOCKED: backward transition {current} → {proposed}. "
            f"CCL-F commitment states are monotonically non-decreasing."
        )

    # --- Rule 4: skipping ahead ------------------------------------------
    # A legal step changes the position by exactly 1. A gap of 2 or more
    # means at least one state was jumped over; name the first one skipped.
    if p_ord - c_ord > 1:
        skipped = _STATE_ORDER[c_ord + 1]
        return False, (
            f"BLOCKED: transition {current} → {proposed} skips {skipped}. "
            f"Non-monotonic jumps are structurally prohibited."
        )

    # --- Rule 5: the only case left ----------------------------------------
    # Not the same, not blocked, not backward, not a skip: one step forward.
    return True, f"Allowed: {current} → {proposed} is a valid single-step forward transition."


# ===========================================================================
# SCENE 2 — THE NEXT STEP
# next_valid_state(): what is the one legal move from here?
# ===========================================================================

def next_valid_state(current: CommitmentState) -> CommitmentState | None:
    """
    Return the state that comes right after `current`.

    Enter:   current   the state the organization is in now
    Exit:    the next state in _STATE_ORDER, or None if `current` is already
             EXECUTION (the final state, so there is nowhere left to go)

    nodes.py uses this to know which single move an LLM is even allowed to
    propose next.
    """
    # PLAYERS IN THIS SCENE
    #   idx   position number of the current state

    idx = _ORDINAL[current]

    # The last valid position is len(_STATE_ORDER) - 1, which is 3.
    # If we are already there, there is no next state.
    if idx + 1 >= len(_STATE_ORDER):
        return None

    return _STATE_ORDER[idx + 1]

# EXEUNT — end of file.

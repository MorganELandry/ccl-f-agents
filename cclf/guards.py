"""
CCL-F Transition Guards
=======================
Structurally blocked transitions are enforced here, not in policy.
The guard is a pure function: (current_state, proposed_state) → bool + reason.

Blocked transitions (from types.py docstring, re-stated as code):
  EXECUTION  → TRAJECTORY   cannot unspend resources
  AUTHORITY  → OPEN         authority closure is durable
  TRAJECTORY → OPEN         trajectory lock does not self-reverse
  any        → skip a state  no non-monotonic jumps allowed
"""

from __future__ import annotations
from typing import Tuple
from .types import CommitmentState

# Ordered sequence for monotonicity check
_STATE_ORDER = [
    CommitmentState.OPEN,
    CommitmentState.TRAJECTORY,
    CommitmentState.AUTHORITY,
    CommitmentState.EXECUTION,
]

_ORDINAL = {s: i for i, s in enumerate(_STATE_ORDER)}

# Explicitly blocked pairs (source → target)
_BLOCKED: set[Tuple[CommitmentState, CommitmentState]] = {
    (CommitmentState.EXECUTION,  CommitmentState.TRAJECTORY),
    (CommitmentState.AUTHORITY,  CommitmentState.OPEN),
    (CommitmentState.TRAJECTORY, CommitmentState.OPEN),
}


def check_transition(
    current: CommitmentState,
    proposed: CommitmentState,
) -> Tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).

    Rules applied in order:
    1. Identity transitions are no-ops (allowed, no audit entry needed).
    2. Explicitly blocked pairs are rejected.
    3. Non-monotonic jumps (skipping a state) are rejected.
    4. Backward transitions are rejected.
    5. Otherwise allowed.
    """
    if current == proposed:
        return True, "No-op: already in target state."

    # Explicit block
    if (current, proposed) in _BLOCKED:
        return False, (
            f"BLOCKED: transition {current} → {proposed} is structurally "
            f"prohibited by CCL-F. This pair represents an irreversible "
            f"commitment that cannot be undone by re-opening the loop."
        )

    c_ord = _ORDINAL[current]
    p_ord = _ORDINAL[proposed]

    # Backward
    if p_ord < c_ord:
        return False, (
            f"BLOCKED: backward transition {current} → {proposed}. "
            f"CCL-F commitment states are monotonically non-decreasing."
        )

    # Skip (gap > 1)
    if p_ord - c_ord > 1:
        skipped = _STATE_ORDER[c_ord + 1]
        return False, (
            f"BLOCKED: transition {current} → {proposed} skips {skipped}. "
            f"Non-monotonic jumps are structurally prohibited."
        )

    return True, f"Allowed: {current} → {proposed} is a valid single-step forward transition."


def next_valid_state(current: CommitmentState) -> CommitmentState | None:
    """Returns the next state in the sequence, or None if already at EXECUTION."""
    idx = _ORDINAL[current]
    if idx + 1 >= len(_STATE_ORDER):
        return None
    return _STATE_ORDER[idx + 1]

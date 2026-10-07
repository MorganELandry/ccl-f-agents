"""
THE RECORD THAT CANNOT BE REVISED
A Play in Nine Scenes
=================================

PROLOGUE
--------
Tests for cclf/audit.py, the audit trail of CCL-F v0.2 Layer 4:

  "Every state transition is append-only and immutable. The audit trail
   supports full post-mortem replay from any point in the program history
   ... The record cannot be revised after the fact — only extended."
   (spec line 1000)
  "the audit trail is the supervisor's non-erasable event log" (line 868)
  Overrides and reopens carry "the agent's identity" (lines 940, 996).

The code makes each entry carry the hash of the entry before it, so an
edited, removed or reordered entry breaks the chain, and AuditTrail.verify()
reports where. These tests attack the log in each of those ways.

THE PLAYBILL
    Scene 1   test_every_transition_is_logged
    Scene 2   test_entries_chain_from_genesis
    Scene 3   test_actor_identity_is_required
    Scene 4   test_refused_action_leaves_no_partial_state    (was a spec mismatch; now fixed)
    Scene 5   test_entries_returns_a_copy
    Scene 6   test_verify_detects_edited_entry
    Scene 7   test_verify_detects_removed_entry
    Scene 8   test_verify_detects_reordered_entries
    Scene 9   test_payload_cannot_be_edited_in_place
    Scene 10  test_truncation_needs_a_kept_head

READER'S NOTE — dataclasses.replace
    AuditEntry is a frozen dataclass: its fields cannot be assigned. To
    forge an edited entry, `dataclasses.replace(entry, actor="x")` builds a
    NEW entry, a copy with one field changed. The forger can then put that
    copy into a list in place of the real one and hand it to verify().
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# dataclasses.replace   forge altered copies of frozen entries.
# pytest                fixtures, raises.
# cclf                  AuditTrail, SignalType, Supervisor.
# cclf.audit            GENESIS, the prev_hash of the first entry.
# stagehands            CUST, TECH, PROCESS, to_review, transitions.
# ===========================================================================

from dataclasses import replace

import pytest

from cclf import AuditTrail, SignalType, Supervisor, TransitionRefused
from cclf.audit import GENESIS
from stagehands import CUST, PROCESS, TECH, to_review, transitions


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# (none: each scene builds its own log through the fixture below)


# ===========================================================================
# THE FIXTURE — a supervisor with a short, real history
# ===========================================================================

@pytest.fixture
def sv():
    """
    A Supervisor with one constraint taken into review and closed by authority.

    Enter:   (nothing)
    Exit:    the Supervisor; its log has at least six entries
    """
    # PLAYERS IN THIS SCENE
    #   s   the new Supervisor

    s = Supervisor()
    to_review(s, "c")
    s.attempt_closure("c", "vp", CUST, (), "schedule")
    return s


# ===========================================================================
# SCENE 1 — NOTHING MOVES UNRECORDED
# Proves: "Every state transition is append-only": the signal's whole path
# is in the log, with the acting agent.
# ===========================================================================

def test_every_transition_is_logged(sv):
    """
    The log holds each transition of "c", in order.

    Enter:   sv   fixture
    Exit:    passes if the transitions are exactly the four the signal made
    """
    assert transitions(sv, "c") == [
        ("unregistered", "registered"), ("registered", "classified"),
        ("classified", "under_review"), ("under_review", "closed_authority")]


# ===========================================================================
# SCENE 2 — LINKED FROM THE FIRST LINE
# Proves: the chain starts at GENESIS, numbers run 0..n-1, and verify()
# accepts an untouched log.
# ===========================================================================

def test_entries_chain_from_genesis(sv):
    """
    An untouched log verifies, starting from GENESIS with consecutive numbers.

    Enter:   sv   fixture
    Exit:    passes if verify() returns (True, "ok") and the links hold
    """
    # PLAYERS IN THIS SCENE
    #   log   the entries

    log = sv.audit.entries()
    assert AuditTrail.verify(log) == (True, "ok")
    assert log[0].prev_hash == GENESIS
    assert [e.sequence for e in log] == list(range(len(log)))
    assert all(b.prev_hash == a.entry_hash for a, b in zip(log, log[1:]))


# ===========================================================================
# SCENE 3 — NO ANONYMOUS ENTRIES
# Proves: every entry needs an actor identity.
# ===========================================================================

def test_actor_identity_is_required():
    """
    AuditTrail.append with an empty actor raises ValueError and adds nothing.

    Enter:   (nothing)
    Exit:    passes if the error is raised and the log stays empty
    """
    # PLAYERS IN THIS SCENE
    #   trail   a fresh AuditTrail

    trail = AuditTrail()
    with pytest.raises(ValueError):
        trail.append(1, "TRANSITION", "", {})
    assert len(trail) == 0


# ===========================================================================
# SCENE 4 — AN UNSIGNED CHANGE
# Proves: if an action is refused for lacking an actor,
# the state change it would have made must not happen either; otherwise
# the state holds a change the audit trail does not record.
# ===========================================================================

def test_refused_action_leaves_no_partial_state():
    """
    A registration with an empty registrant changes nothing.

    Enter:   (nothing)
    Exit:    passes if the call raises and the signal is not stored
    """
    # PLAYERS IN THIS SCENE
    #   s   a fresh Supervisor

    s = Supervisor()
    with pytest.raises(TransitionRefused):
        s.register_signal("x", SignalType.ANOMALY, "d", "", TECH, PROCESS)
    assert "x" not in s.signals


# ===========================================================================
# SCENE 5 — LOOK, DON'T TOUCH (the list)
# Proves: entries() hands out a copy; changing that list does not change
# the log.
# ===========================================================================

def test_entries_returns_a_copy(sv):
    """
    Clearing the list from entries() leaves the log intact.

    Enter:   sv   fixture
    Exit:    passes if the log length is unchanged and still verifies
    """
    # PLAYERS IN THIS SCENE
    #   before   the log length before tampering
    #   copy     the list returned by entries()

    before = len(sv.audit)
    copy = sv.audit.entries()
    copy.clear()
    assert len(sv.audit) == before
    assert AuditTrail.verify(sv.audit.entries())[0]


# ===========================================================================
# SCENE 6 — THE FORGED LINE
# Proves: verify() detects an edited entry, whether or not the forger also
# recomputed that entry's own hash.
# ===========================================================================

def test_verify_detects_edited_entry(sv):
    """
    A changed actor fails verification at that entry; a re-hashed forgery
    fails at the next entry.

    Enter:   sv   fixture
    Exit:    passes if both forged logs fail and the reasons name the
             right entry numbers
    """
    # PLAYERS IN THIS SCENE
    #   log        a copy of the entries
    #   i          index of the entry to forge (the closure)
    #   forged     the altered entry
    #   ok, why    verify()'s answer

    log = sv.audit.entries()
    i = len(log) - 1
    # --- Naive forgery: change the actor, keep the old hash ----------------
    log[i] = replace(log[i], actor="somebody-else")
    ok, why = AuditTrail.verify(log)
    assert not ok and why.startswith(f"entry {i}:")
    # --- Careful forgery: also recompute the entry's own hash --------------
    log = sv.audit.entries()
    i = 2
    forged = replace(log[i], actor="somebody-else")
    forged = replace(forged, entry_hash=forged.compute_hash(
        forged.sequence, forged.at, forged.event, forged.actor, forged.payload,
        forged.prev_hash))
    log[i] = forged
    ok, why = AuditTrail.verify(log)
    assert not ok and why.startswith(f"entry {i + 1}:")


# ===========================================================================
# SCENE 7 — THE MISSING PAGE
# Proves: verify() detects a removed entry.
# ===========================================================================

def test_verify_detects_removed_entry(sv):
    """
    Deleting an entry from the middle fails verification.

    Enter:   sv   fixture
    Exit:    passes if verify() returns False
    """
    # PLAYERS IN THIS SCENE
    #   log   a copy of the entries with entry 1 removed

    log = sv.audit.entries()
    del log[1]
    assert not AuditTrail.verify(log)[0]


# ===========================================================================
# SCENE 8 — THE SHUFFLED PAGES
# Proves: verify() detects reordered entries.
# ===========================================================================

def test_verify_detects_reordered_entries(sv):
    """
    Swapping two entries fails verification.

    Enter:   sv   fixture
    Exit:    passes if verify() returns False
    """
    # PLAYERS IN THIS SCENE
    #   log   a copy of the entries with two swapped

    log = sv.audit.entries()
    log[1], log[2] = log[2], log[1]
    assert not AuditTrail.verify(log)[0]


# ===========================================================================
# SCENE 9 — LOOK, DON'T TOUCH (the payload)
# Proves: an entry's payload dict, though mutable in Python, cannot be
# changed without the change being detected.
# ===========================================================================

def test_payload_cannot_be_edited_in_place(sv):
    """
    Mutating a payload through entries() is caught by verify().

    Enter:   sv   fixture
    Exit:    passes if verify() fails at entry 0 after the mutation

    Note: entries() copies the list, not the entries, so the mutation does
    reach the stored entry. This scene checks the guarantee the spec needs
    (any revision is detectable), not that mutation is impossible.
    """
    sv.audit.entries()[0].payload["signal"] = "rewritten"
    ok, why = AuditTrail.verify(sv.audit.entries())
    assert not ok and why.startswith("entry 0:")


# ===========================================================================
# SCENE 10 — THE MISSING LAST PAGES
# Proves: a chain cut off at the end is still self-consistent, so verify()
# catches it only against a head() kept elsewhere.
# ===========================================================================

def test_truncation_needs_a_kept_head(sv):
    """
    Dropping the newest entries passes a bare verify() but fails against
    the head recorded before the cut.

    Enter:   sv   fixture
    Exit:    passes if the bare check says ok, the head check says not ok,
             and the full chain passes the head check
    """
    # PLAYERS IN THIS SCENE
    #   full    every entry
    #   head    the newest entry's hash, as kept elsewhere
    #   short   the chain with its last entry cut off

    full = sv.audit.entries()
    head = sv.audit.head()
    short = full[:-1]
    assert AuditTrail.verify(short) == (True, "ok")
    assert not AuditTrail.verify(short, expected_head=head)[0]
    assert AuditTrail.verify(full, expected_head=head) == (True, "ok")

# EXEUNT — end of file.

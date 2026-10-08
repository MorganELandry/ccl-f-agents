"""
THE PERMANENT RECORD
A Play in Three Scenes
======================

PROLOGUE
--------
The audit trail (CCL-F v0.2, Layer 4): "Every state transition is append-only
and immutable ... The record cannot be revised after the fact — only
extended."

Each entry carries the acting agent's identity and the hash of the entry
before it, so editing or deleting any entry breaks the chain, and
verify() finds the break.

Where this fits: the Supervisor (supervisor.py) owns one AuditTrail and
writes an entry for the events it handles (registrations, transitions,
closures, overrides, and refused transitions and re-entries). Layer 4 calls the audit trail "the
supervisor's non-erasable event log". run_demo.py calls AuditTrail.verify()
on the finished log and saves it with to_json().

THE PLAYBILL (what happens in this file)
    Scene 1   _canonical()          turn values into stable, JSON-ready forms
    Scene 2   AuditEntry            one immutable, hash-stamped record
                compute_hash()      the SHA-256 fingerprint of an entry
                is_self_consistent  does an entry still match its hash?
    Scene 3   AuditTrail            the append-only log itself
                append()            add a new, chained entry
                entries(), __iter__, __len__, events()   read-only views
                head()              the newest entry's hash, to keep elsewhere
                verify()            check a whole chain for tampering
                to_json()           export entries as plain dicts

READER'S NOTE — hashing and SHA-256
    A hash function turns any input into a short fixed-length "fingerprint".
    SHA-256 (from Python's hashlib) gives 64 hex characters. Changing even
    one character of the input gives a completely different fingerprint,
    and it is not practical to find a different input with the same one.
    So if you store an entry's hash, you can later tell whether the entry
    was changed: recompute the hash and compare.

READER'S NOTE — why a hash *chain* is tamper-evident
    Each entry's hash covers its own contents *and* the previous entry's
    hash (prev_hash). Entry 0 links to the fixed marker GENESIS. If someone
    edits entry 5, its recomputed hash no longer matches what is stored. If
    they also rewrite entry 5's stored hash, entry 6's prev_hash no longer
    matches it. Deleting or reordering entries breaks the sequence numbers
    or the links. To hide an edit you would have to rewrite every later
    entry too. "Tamper-evident" means changes are detectable, not that they
    are impossible: this code keeps the log in memory and does not sign or
    externally anchor the hashes.

READER'S NOTE — JSON canonicalization
    To hash a Python dict we first turn it into text with json.dumps. The
    same data must always give byte-for-byte the same text, or the hash
    would change for no reason. Two things make that true here:
    _canonical() converts enums, tuples and sets into plain JSON values
    (sets are sorted, because a set has no fixed order), and
    json.dumps(..., sort_keys=True) writes dict keys in sorted order.

READER'S NOTE — @staticmethod
    A @staticmethod is a function that lives inside a class for
    organisation but does not receive `self`. You can call it on the class
    itself: AuditEntry.compute_hash(...) or AuditTrail.verify(entries).
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# hashlib     provides sha256() for the entry fingerprints.
# json        turns payloads into canonical text (and back, to copy them).
# dataclass   builds the frozen AuditEntry record.
# Enum        recognised by _canonical() so enum members become their values.
# Any, Iterator   type hints: "any type"; "something you can loop over".
# Optional    Optional[X] means "an X, or None" (verify()'s expected_head).
# ===========================================================================

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator, Optional


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# GENESIS — the stand-in "previous hash" for the very first entry. Entry 0
#   has no entry before it, so its prev_hash is this fixed string, and
#   verify() starts its chain walk from it.
GENESIS = "GENESIS"


# ===========================================================================
# SCENE 1 — THE TRANSLATOR
# _canonical(): make a value safe and stable for JSON and hashing
# ===========================================================================

def _canonical(value: Any) -> Any:
    """
    Turn enums, tuples, sets and frozensets into JSON-stable forms.

    Enter:   value   any value that may appear in an audit payload
    Exit:    the same data using only JSON-friendly types:
               Enum            -> its .value (e.g. "under_review")
               dict            -> dict with str keys, values converted
               list / tuple    -> list, items converted
               set / frozenset -> sorted list, items converted
               anything else   -> returned unchanged

    Recursive: it calls itself on the items inside containers, so nested
    structures are converted all the way down. The leading underscore marks
    it as private to this module.
    """
    # --- Enum members become their plain value ------------------------------
    if isinstance(value, Enum):
        return value.value
    # --- dicts: string keys, converted values -------------------------------
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    # --- lists and tuples both become lists ---------------------------------
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    # --- sets have no order, so sort them for a stable result ---------------
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical(v) for v in value)
    return value


# ===========================================================================
# SCENE 2 — ONE LINE IN THE LEDGER
# AuditEntry: a single immutable, hash-stamped record
# ===========================================================================

@dataclass(frozen=True)
class AuditEntry:
    """
    One immutable audit record.

    Fields:
      sequence    position in the trail, starting at 0
      at          the supervisor's logical clock tick when it was written
      event       event name, e.g. "TRANSITION" or "GATE_OVERRIDE"
      actor       identity of the acting agent (required, never empty)
      payload     event details, already canonicalized by AuditTrail.append
      prev_hash   entry_hash of the entry before (GENESIS for entry 0)
      entry_hash  SHA-256 of all the fields above

    frozen=True means fields cannot be reassigned after creation (see the
    READER'S NOTE in types.py). Note: `payload` is a dict, and a frozen
    dataclass does not stop someone mutating the dict's contents; if that
    happened, is_self_consistent() and verify() would detect it.
    """
    sequence: int
    at: int
    event: str
    actor: str
    payload: dict
    prev_hash: str
    entry_hash: str

    # -----------------------------------------------------------------------
    # SCENE 2a — THE FINGERPRINT
    # -----------------------------------------------------------------------
    @staticmethod
    def compute_hash(sequence: int, at: int, event: str, actor: str,
                     payload: dict, prev_hash: str) -> str:
        """
        Compute the SHA-256 fingerprint of an entry's fields.

        Enter:   sequence, at, event, actor, payload, prev_hash
                 the fields of an AuditEntry, minus entry_hash itself
        Exit:    64-character hex string

        Including prev_hash is what links each entry to the one before it.
        """
        # PLAYERS IN THIS SCENE
        #   blob   the canonical JSON text that gets hashed

        # --- Canonical text: same data always gives the same string --------
        blob = json.dumps({
            "sequence": sequence, "at": at, "event": event, "actor": actor,
            "payload": _canonical(payload), "prev_hash": prev_hash,
        }, sort_keys=True)
        # --- Hash it --------------------------------------------------------
        # .encode() turns the str into bytes, which sha256 needs;
        # .hexdigest() gives the result as a readable hex string.
        return hashlib.sha256(blob.encode()).hexdigest()

    # -----------------------------------------------------------------------
    # SCENE 2b — DOES IT STILL MATCH?
    # -----------------------------------------------------------------------
    def is_self_consistent(self) -> bool:
        """
        Does this entry still match its own stored hash?

        Enter:   (none)
        Exit:    True if recomputing the hash from the current fields gives
                 entry_hash, i.e. the contents have not been changed
        """
        return self.entry_hash == AuditEntry.compute_hash(
            self.sequence, self.at, self.event, self.actor, self.payload, self.prev_hash)


# ===========================================================================
# SCENE 3 — THE LEDGER
# AuditTrail: an append-only log that can only be extended
# ===========================================================================

class AuditTrail:
    """
    Append-only log. There is deliberately no method that edits or removes
    an entry; entries() hands out a copy so callers cannot mutate the log.

    This is how the code honours Layer 4's "The record cannot be revised
    after the fact — only extended": the only way in is append(). (Python
    cannot truly stop code reaching the private _entries list; the
    leading underscore is a convention meaning "do not touch from outside".)
    """

    # -----------------------------------------------------------------------
    # SCENE 3a — AN EMPTY LEDGER
    # -----------------------------------------------------------------------
    def __init__(self) -> None:
        """
        Start an empty trail.

        Enter:   (none)
        Exit:    self._entries = [], the private list of AuditEntry objects,
                 oldest first
        """
        self._entries: list[AuditEntry] = []

    # -----------------------------------------------------------------------
    # SCENE 3b — WRITING A NEW LINE
    # -----------------------------------------------------------------------
    def append(self, at: int, event: str, actor: str, payload: dict) -> AuditEntry:
        """
        Add one entry to the end of the chain.

        Enter:   at        the supervisor's clock tick
                 event     the event name
                 actor     the acting agent's identity (must not be empty)
                 payload   event details (may hold enums, sets, tuples)
        Exit:    the new AuditEntry, already stored
                 raises ValueError if actor is empty

        The actor check reflects the spec's demand that overrides and reopens
        be logged with the agent's identity; here it applies to every entry.
        """
        # PLAYERS IN THIS SCENE
        #   prev             hash of the last entry, or GENESIS if empty
        #   seq              this entry's sequence number
        #   frozen_payload   a canonicalized private copy of the payload
        #   entry            the new AuditEntry

        # --- Every entry must name who did it -------------------------------
        if not actor:
            raise ValueError("every audit entry needs an actor identity")
        # --- Link to the previous entry -------------------------------------
        prev = self._entries[-1].entry_hash if self._entries else GENESIS
        seq = len(self._entries)
        # --- Take a private, JSON-clean copy of the payload -----------------
        # dumps-then-loads makes a deep copy, so later changes to the
        # caller's dict cannot change what was logged.
        frozen_payload = json.loads(json.dumps(_canonical(payload)))
        # --- Stamp it with its hash and store it ----------------------------
        entry = AuditEntry(seq, at, event, actor, frozen_payload, prev,
                           AuditEntry.compute_hash(seq, at, event, actor, frozen_payload, prev))
        self._entries.append(entry)
        return entry

    # -----------------------------------------------------------------------
    # SCENE 3c — READING THE LEDGER (read-only views)
    # -----------------------------------------------------------------------
    def entries(self) -> list[AuditEntry]:
        """
        A copy of all entries, oldest first.

        Enter:   (none)
        Exit:    a new list each call; callers may change that list freely
                 without affecting the trail itself
        """
        return list(self._entries)

    def __iter__(self) -> Iterator[AuditEntry]:
        """
        Make `for e in trail:` work.

        Enter:   (none)
        Exit:    an iterator over a copy of the entries, so appending during
                 the loop does not disturb it
        """
        return iter(list(self._entries))

    def __len__(self) -> int:
        """
        Make `len(trail)` work.

        Enter:   (none)
        Exit:    the number of entries
        """
        return len(self._entries)

    def events(self) -> list[str]:
        """
        Just the event names, in order.

        Enter:   (none)
        Exit:    list of str, e.g. ["EVIDENCE_ADDED", "TRANSITION", ...];
                 handy in tests: `"GATE_OVERRIDE" in sv.audit.events()`
        """
        return [e.event for e in self._entries]

    def head(self) -> str:
        """
        The newest entry's hash (GENESIS if the trail is empty).

        Enter:   (none)
        Exit:    a hex SHA-256 string, or GENESIS

        Keep this value somewhere the trail's storage cannot reach (a
        ticket, a second system, a signed message). A chain alone cannot
        reveal that entries were cut off its end: the shorter chain is
        still internally consistent. Passing the kept head to verify()
        closes that gap.
        """
        return self._entries[-1].entry_hash if self._entries else GENESIS

    # -----------------------------------------------------------------------
    # SCENE 3d — THE INSPECTION
    # -----------------------------------------------------------------------
    @staticmethod
    def verify(entries: list[AuditEntry],
               expected_head: Optional[str] = None) -> tuple[bool, str]:
        """
        Check a sequence of entries: numbering, links and hashes.
        Returns (True, "ok") or (False, reason naming the first bad entry).

        Enter:   entries         a list of AuditEntry, oldest first (for
                                 example from trail.entries(), or reloaded
                                 from storage)
                 expected_head   optional: a head() value kept elsewhere.
                                 If given, the chain must end exactly there.
        Exit:    (True, "ok") if the chain is intact, else (False, reason)

        Static, so it can check any list of entries, not only a live trail.
        It stops at the first problem it finds. Edits, removals and
        reordering anywhere are always caught; entries cut off the END are
        caught only when expected_head is given (see head()).
        """
        # PLAYERS IN THIS SCENE
        #   prev   the hash the current entry should link to (GENESIS first)
        #   i, e   position and entry being checked

        prev = GENESIS
        for i, e in enumerate(entries):
            # --- Gap or reordering? -----------------------------------------
            if e.sequence != i:
                return False, f"entry {i}: sequence number {e.sequence} out of order"
            # --- Broken link to the entry before? ---------------------------
            if e.prev_hash != prev:
                return False, f"entry {i}: does not link to the entry before it"
            # --- Contents edited after hashing? -----------------------------
            if not e.is_self_consistent():
                return False, f"entry {i}: contents do not match its hash"
            prev = e.entry_hash
        # --- Cut short? Only knowable against a head kept elsewhere ---------
        if expected_head is not None and prev != expected_head:
            return False, "chain does not end at the expected head (entries missing from the end?)"
        return True, "ok"

    # -----------------------------------------------------------------------
    # SCENE 3e — THE TRANSCRIPT
    # -----------------------------------------------------------------------
    def to_json(self) -> list[dict]:
        """
        Export every entry as a plain dict, ready for json.dump.

        Enter:   (none)
        Exit:    list of dicts (field name -> value), oldest first

        __dict__ is the object's attribute dict; .copy() gives the caller
        its own dict rather than the entry's internals.
        """
        return [e.__dict__.copy() for e in self._entries]

# EXEUNT — end of file.

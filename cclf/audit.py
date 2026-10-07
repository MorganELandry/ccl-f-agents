"""
The audit trail (CCL-F v0.2, Layer 4): "Every state transition is append-only
and immutable ... The record cannot be revised after the fact — only
extended."

Each entry carries the acting agent's identity and the hash of the entry
before it, so editing or deleting any entry breaks the chain, and
verify() finds the break.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator


GENESIS = "GENESIS"


def _canonical(value: Any) -> Any:
    """Turn enums, tuples, sets and frozensets into JSON-stable forms."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical(v) for v in value)
    return value


@dataclass(frozen=True)
class AuditEntry:
    """One immutable audit record."""
    sequence: int
    at: int
    event: str
    actor: str
    payload: dict
    prev_hash: str
    entry_hash: str

    @staticmethod
    def compute_hash(sequence: int, at: int, event: str, actor: str,
                     payload: dict, prev_hash: str) -> str:
        blob = json.dumps({
            "sequence": sequence, "at": at, "event": event, "actor": actor,
            "payload": _canonical(payload), "prev_hash": prev_hash,
        }, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def is_self_consistent(self) -> bool:
        return self.entry_hash == AuditEntry.compute_hash(
            self.sequence, self.at, self.event, self.actor, self.payload, self.prev_hash)


class AuditTrail:
    """
    Append-only log. There is deliberately no method that edits or removes
    an entry; entries() hands out a copy so callers cannot mutate the log.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def append(self, at: int, event: str, actor: str, payload: dict) -> AuditEntry:
        if not actor:
            raise ValueError("every audit entry needs an actor identity")
        prev = self._entries[-1].entry_hash if self._entries else GENESIS
        seq = len(self._entries)
        frozen_payload = json.loads(json.dumps(_canonical(payload)))
        entry = AuditEntry(seq, at, event, actor, frozen_payload, prev,
                           AuditEntry.compute_hash(seq, at, event, actor, frozen_payload, prev))
        self._entries.append(entry)
        return entry

    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def __iter__(self) -> Iterator[AuditEntry]:
        return iter(list(self._entries))

    def __len__(self) -> int:
        return len(self._entries)

    def events(self) -> list[str]:
        return [e.event for e in self._entries]

    @staticmethod
    def verify(entries: list[AuditEntry]) -> tuple[bool, str]:
        """
        Check a sequence of entries: numbering, links and hashes.
        Returns (True, "ok") or (False, reason naming the first bad entry).
        """
        prev = GENESIS
        for i, e in enumerate(entries):
            if e.sequence != i:
                return False, f"entry {i}: sequence number {e.sequence} out of order"
            if e.prev_hash != prev:
                return False, f"entry {i}: does not link to the entry before it"
            if not e.is_self_consistent():
                return False, f"entry {i}: contents do not match its hash"
            prev = e.entry_hash
        return True, "ok"

    def to_json(self) -> list[dict]:
        return [e.__dict__.copy() for e in self._entries]

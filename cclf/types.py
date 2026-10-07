"""
CCL-F Commitment State Machine — Type Definitions
==================================================
Canonical v0.2 vocabulary. Commitment states map directly to LangGraph nodes.
Transition guards are implemented as edge conditions in graph.py.

Reference: CCL-F Framework v0.1 (Zenodo, CC BY-NC-ND 4.0)
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field
import hashlib
import json
import time


# ---------------------------------------------------------------------------
# Commitment States (canonical v0.2 names)
# ---------------------------------------------------------------------------

class CommitmentState(str, Enum):
    """
    The four states of the CCL-F commitment state machine.

    OPEN         → signals are visible; no trajectory committed
    TRAJECTORY   → a direction is locked; alternatives are deprioritized
    AUTHORITY    → the decision authority has formally closed
    EXECUTION    → resources are deployed; reversal is operationally costly

    Blocked transitions (structurally enforced, not just policy):
      EXECUTION  → TRAJECTORY   (cannot unspend)
      AUTHORITY  → OPEN         (authority closure is durable)
      TRAJECTORY → OPEN         (trajectory lock does not self-reverse)
      any        → skip a state  (no non-monotonic jumps)
    """
    OPEN        = "OPEN"
    TRAJECTORY  = "TRAJECTORY"
    AUTHORITY   = "AUTHORITY"
    EXECUTION   = "EXECUTION"


# ---------------------------------------------------------------------------
# Evidence model
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """A single piece of evidence presented to the agent."""
    evidence_id: str
    content: str
    source: str
    timestamp: float = field(default_factory=time.time)
    # Novelty / independence scores set by the LLM node
    novelty_score: Optional[float] = None       # 0.0–1.0; None = not yet evaluated
    independence_score: Optional[float] = None  # 0.0–1.0; None = not yet evaluated

    def is_admissible(self) -> bool:
        """Evidence must clear both novelty AND independence guards."""
        if self.novelty_score is None or self.independence_score is None:
            return False
        return self.novelty_score >= 0.5 and self.independence_score >= 0.5


# ---------------------------------------------------------------------------
# ACS (Authority Commitment Signal) hidden-state inference
# ---------------------------------------------------------------------------

@dataclass
class ACSEstimate:
    """
    Probability distribution over CommitmentStates inferred from behavioral signals.
    The agent cannot observe ACS directly; it maintains this distribution.
    """
    p_open: float       = 1.0
    p_trajectory: float = 0.0
    p_authority: float  = 0.0
    p_execution: float  = 0.0
    confidence: float   = 0.0
    reasoning: str      = ""

    def most_likely(self) -> CommitmentState:
        probs = {
            CommitmentState.OPEN:       self.p_open,
            CommitmentState.TRAJECTORY: self.p_trajectory,
            CommitmentState.AUTHORITY:  self.p_authority,
            CommitmentState.EXECUTION:  self.p_execution,
        }
        return max(probs, key=probs.get)


# ---------------------------------------------------------------------------
# Audit entry (hash-chained)
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """
    One entry in the append-only audit log.
    Each entry hashes its own content + the previous entry's hash,
    producing a tamper-evident chain.
    """
    sequence:    int
    event_type:  str
    from_state:  Optional[CommitmentState]
    to_state:    Optional[CommitmentState]
    payload:     dict[str, Any]
    timestamp:   float = field(default_factory=time.time)
    prev_hash:   str   = ""
    # Computed from the fields above. Accepted as an argument only so an
    # entry can be rebuilt from a checkpoint; a supplied value that does not
    # match the recomputed hash is rejected as tampering.
    entry_hash:  str   = ""

    def __post_init__(self):
        expected = self._compute_hash()
        if self.entry_hash and self.entry_hash != expected:
            raise ValueError(
                f"Audit entry {self.sequence} failed integrity check: "
                "stored hash does not match its contents"
            )
        self.entry_hash = expected

    def _compute_hash(self) -> str:
        blob = json.dumps({
            "seq":        self.sequence,
            "event":      self.event_type,
            "from":       self.from_state,
            "to":         self.to_state,
            "payload":    self.payload,
            "ts":         self.timestamp,
            "prev_hash":  self.prev_hash,
        }, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Agent state (LangGraph state dict)
# ---------------------------------------------------------------------------

@dataclass
class CCLFAgentState:
    """
    The complete mutable state passed between LangGraph nodes.
    LangGraph requires state to be serialisable; all fields use basic types
    or dataclasses that can be converted to dicts.
    """
    # Current formal commitment state
    commitment_state: CommitmentState = CommitmentState.OPEN

    # Evidence buffer (presented this session)
    evidence_buffer: list[Evidence] = field(default_factory=list)

    # ACS hidden-state estimate (updated by inference node)
    acs_estimate: ACSEstimate = field(default_factory=ACSEstimate)

    # Proposed transition (set by evaluation node, consumed by guard node)
    proposed_transition: Optional[CommitmentState] = None

    # Human-in-the-loop verdict (set by interrupt node)
    human_approval: Optional[bool] = None
    human_rationale: str = ""

    # Audit log
    audit_log: list[AuditEntry] = field(default_factory=list)

    # ACO flag — Adversarial Commitment Opacity detected
    aco_detected: bool = False
    aco_reasoning: str = ""

    # Free-form messages from nodes (for visibility / debugging)
    messages: list[str] = field(default_factory=list)

    # Termination signal
    should_terminate: bool = False

    @classmethod
    def from_stream(cls, chunk: Any) -> "CCLFAgentState":
        """
        Normalise a graph.stream(stream_mode="values") chunk to a state object.
        Recent LangGraph versions yield a plain dict of fields for dataclass
        state; older versions yielded the dataclass itself.
        """
        if isinstance(chunk, cls):
            return chunk
        return cls(**chunk)

    def last_audit_hash(self) -> str:
        if not self.audit_log:
            return "GENESIS"
        return self.audit_log[-1].entry_hash

    def append_audit(self, event_type: str, payload: dict,
                     from_state: Optional[CommitmentState] = None,
                     to_state: Optional[CommitmentState] = None) -> None:
        entry = AuditEntry(
            sequence=len(self.audit_log),
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            payload=payload,
            prev_hash=self.last_audit_hash(),
        )
        self.audit_log.append(entry)

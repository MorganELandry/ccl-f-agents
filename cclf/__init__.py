"""
cclf — a runtime monitor for the Coordination Control Loop Framework (CCL-F)
v0.2 working draft: the Layer 4 commitment state machine, closure typing,
escalation, coherence scoring and execution gates.
"""

from .audit import AuditEntry, AuditTrail
from .advisor import Advisor, Proposal
from .graph import build_graph, replay
from .statemachine import TRANSITIONS, check_transition
from .supervisor import GateResult, Settings, StructuralReview, Supervisor, TransitionRefused
from .types import (
    Architecture, ClosureRecord, ClosureType, CommitmentState, Decision,
    EscalationCondition, Evidence, EvidenceKind, ExecutionClass, ExitRecord,
    ExitType, LegalSubtype, OperationalState, Referent, Signal, SignalType,
)

__all__ = [
    "AuditEntry", "AuditTrail", "Advisor", "Proposal", "build_graph", "replay",
    "TRANSITIONS", "check_transition", "GateResult", "Settings", "StructuralReview",
    "Supervisor", "TransitionRefused", "Architecture", "ClosureRecord", "ClosureType",
    "CommitmentState", "Decision", "EscalationCondition", "Evidence", "EvidenceKind",
    "ExecutionClass", "ExitRecord", "ExitType", "LegalSubtype", "OperationalState",
    "Referent", "Signal", "SignalType",
]

"""
THE FRONT OF HOUSE
A Play in One Scene
===================

PROLOGUE
--------
cclf — a runtime monitor for the Coordination Control Loop Framework (CCL-F)
v0.2 working draft: the Layer 4 commitment state machine, closure typing,
escalation, coherence scoring and execution gates.

This file runs when anyone writes `import cclf` or `from cclf import ...`.
It contains no logic of its own. It gathers the public names from the
modules inside the package so users can write `from cclf import Supervisor`
instead of `from cclf.supervisor import Supervisor`.

The package, module by module:
  types.py         the CCL-F vocabulary (enums) and records (dataclasses)
  statemachine.py  the Layer 4 Commitment State Machine transition rules
  audit.py         the Layer 4 Audit Trail: an append-only hash chain
  supervisor.py    the rule engine: closure typing, escalation, coherence
                   score, execution gates
  advisor.py       the model that only *proposes* (AI Applications)
  graph.py         a LangGraph pipeline that replays events through them
  observability.py optional OpenTelemetry tracing and metrics (not
                   re-exported here; import cclf.observability directly)
  backends/        the LLM backend registry the advisor builds models from
                   (imported lazily, not re-exported here)

THE PLAYBILL (what happens in this file)
    Scene 1  re-export the public names, and list them in __all__

READER'S NOTE — package __init__ and relative imports
    A folder with an __init__.py is a Python package. `from .audit import X`
    means "from the audit module in this same package". Importing names
    here makes them available as cclf.X.

READER'S NOTE — import order and side effects
    Importing this package imports every module listed below, including
    graph.py, which imports langgraph at its top. So `import cclf` needs
    langgraph installed. LangChain model packages, by contrast, are only
    imported lazily when a model is first used (see advisor.py).
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# .audit         AuditEntry, AuditTrail — the tamper-evident event log
# .advisor       Advisor, Proposal — the model-backed classifier (proposes only)
# .graph         build_graph, replay — the LangGraph event pipeline
# .statemachine  TRANSITIONS, check_transition — the v0.2 transition table
# .supervisor    GateResult, Settings, StructuralReview, Supervisor,
#                TransitionRefused — the rule engine and its results
# .types         the enums and record classes of the CCL-F vocabulary
# ===========================================================================

from .audit import AuditEntry, AuditTrail
from .advisor import Advisor, Proposal
from .graph import build_graph, replay
from .statemachine import TRANSITIONS, check_transition
from .supervisor import GateResult, Settings, StructuralReview, Supervisor, TransitionRefused
from .types import (
    AgentKind, Architecture, ClassificationRecord, ClosureRecord, ClosureType,
    CommitmentState, Decision, EmergencyConsequence, EmergencyJustification,
    EscalationCondition, Evidence, EvidenceKind, ExecutionClass, ExitRecord,
    ExitType, Grant, LegalSubtype, OpenLoopAuthorization, OperationalState, OutcomeRecord,
    Power, Referent, RiskAttestation, Signal, SignalType,
)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# __all__ — the package's official public names. It decides what
#   `from cclf import *` brings in, and tells readers and tools which names
#   are meant for outside use. Every name listed is imported just above.
__all__ = [
    "AuditEntry", "AuditTrail", "Advisor", "Proposal", "build_graph", "replay",
    "TRANSITIONS", "check_transition", "GateResult", "Settings", "StructuralReview",
    "Supervisor", "TransitionRefused", "Architecture", "ClosureRecord", "ClosureType",
    "CommitmentState", "Decision", "EscalationCondition", "Evidence", "EvidenceKind",
    "ExecutionClass", "ExitRecord", "ExitType", "LegalSubtype", "OperationalState",
    "Referent", "Signal", "SignalType", "Grant", "Power", "AgentKind",
    "ClassificationRecord", "EmergencyConsequence", "EmergencyJustification",
    "OpenLoopAuthorization", "OutcomeRecord", "RiskAttestation",
]

# EXEUNT — end of file.

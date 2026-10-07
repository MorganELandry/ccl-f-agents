"""
THE FRONT OF HOUSE
A Play in One Scene
===================

PROLOGUE
--------
cclf — CCL-F Commitment Agent.
The Coordination Control Loop Framework commitment state machine,
implemented as a LangGraph agentic workflow.

This file is the package's front door. Python runs it the first time any
code says `import cclf` (or `from cclf import ...`). Its only job is to
gather the most useful names from the modules inside the package so that
callers can write

    from cclf import build_graph, CCLFAgentState

instead of having to know which file each name lives in.

THE PLAYBILL (what happens in this file)
    Scene 1  the imports      bring the public names up to package level
             __all__          the official list of what the package offers

READER'S NOTE — __init__.py
    A folder containing an __init__.py file is a Python "package". The
    leading dot in `from .types import ...` means "from the module named
    types inside this same package", not some other `types` installed
    elsewhere (Python's standard library also has one).

READER'S NOTE — __all__
    __all__ is a list of strings naming the public parts of a module. It
    decides what `from cclf import *` brings in, and it tells readers and
    tools which names are meant for outside use.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# types          the data classes: state, states enum, evidence, estimates,
#                audit entries.
# guards         the LLM-free rules about which state moves are legal.
# graph          build_graph(), which assembles the LangGraph workflow.
# nodes          the eight step functions, offered as a whole module (tests
#                use it to swap the LLM helper out for a scripted one).
# observability  OpenTelemetry tracing / metrics support, offered as a whole
#                module.
# ===========================================================================

from .types import CCLFAgentState, CommitmentState, Evidence, ACSEstimate, AuditEntry
from .guards import check_transition, next_valid_state
from .graph import build_graph
from . import nodes
from . import observability


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# __all__ — the names this package officially offers to the outside world.
#   Each string must match a name imported above. It controls what
#   `from cclf import *` brings in, and it documents the public interface:
#   anything not listed here should be treated as internal.
__all__ = [
    "CCLFAgentState",
    "CommitmentState",
    "Evidence",
    "ACSEstimate",
    "AuditEntry",
    "check_transition",
    "next_valid_state",
    "build_graph",
    "nodes",
    "observability",
]

# EXEUNT — end of file.

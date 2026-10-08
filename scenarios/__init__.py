"""
THE REPERTOIRE
A Play in One Scene
===================

PROLOGUE
--------
Replayable event histories for the CCL-F v0.2 runtime. Each fact comes from
the CCL-F v0.2 working draft; each event's `note` names the section.

This package collects the five scenarios into one lookup table, SCENARIOS,
which run_demo.py (its command-line choices) and tests/test_scenarios.py use.
Each scenario is a plain list of event dicts that cclf.graph.replay() feeds,
one at a time, to the Supervisor. The event format is described in each
scenario module and in cclf/graph.py.

THE PLAYBILL
    Scene 1  SCENARIOS   scenario name -> its list of events
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# .apollo13     APOLLO13: Apollo 13 (1970), an Emergency Justification
#               given by a separate authority on the ground.
# .challenger   CHALLENGER: the Challenger (1986) event list.
# .mcas         MCAS: the Boeing 737 MAX event list.
# .therac25     THERAC25: the Therac-25 (1985-1987) event list.
# .usair1549    USAIR1549: US Airways Flight 1549 (2009), an Emergency
#               Justification given on scene.
# The leading dot means "from this package" (a relative import).
# ===========================================================================

from .apollo13 import APOLLO13
from .challenger import CHALLENGER
from .mcas import MCAS
from .therac25 import THERAC25
from .usair1549 import USAIR1549


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# SCENARIOS — scenario name (as typed on the command line) -> event list.
SCENARIOS = {"challenger": CHALLENGER, "therac25": THERAC25, "mcas": MCAS,
             "apollo13": APOLLO13, "usair1549": USAIR1549}

# __all__ — the names `from scenarios import *` exports; also documents the
#   package's public interface.
__all__ = ["APOLLO13", "CHALLENGER", "MCAS", "THERAC25", "USAIR1549", "SCENARIOS"]

# EXEUNT — end of file.

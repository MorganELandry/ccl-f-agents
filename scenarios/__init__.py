"""
Replayable event histories for the CCL-F v0.2 runtime. Each fact comes from
the CCL-F v0.2 working draft; each event's `note` names the section.
"""

from .challenger import CHALLENGER
from .mcas import MCAS
from .therac25 import THERAC25

SCENARIOS = {"challenger": CHALLENGER, "therac25": THERAC25, "mcas": MCAS}

__all__ = ["CHALLENGER", "MCAS", "THERAC25", "SCENARIOS"]

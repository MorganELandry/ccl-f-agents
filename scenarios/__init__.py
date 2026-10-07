"""
THE SCENARIOS PACKAGE
A Play in One Scene
===================

PROLOGUE
--------
This package holds the evidence "scripts" that are fed to the CCL-F agent:
lists of evidence items, each one a small dict, drawn from two real-world
safety failures. This `__init__.py` file is the front door: it gathers the
public scenario lists from the two scenario files so that other code can
write the short form

    from scenarios import MCAS_SCENARIO

instead of reaching into the individual files. run_demo.py, the tests, and
evals/authority_pressure.py all import from here.

THE PLAYBILL (what this file provides)
    MCAS_SCENARIO        five Boeing 737 MAX evidence items  (from mcas.py)
    PASS_1_INCIDENTS     six Therac-25 incident batches      (from therac25.py)
    PASS_2_SUPPRESSION   AECL suppression documents          (from therac25.py)

READER'S NOTE
    A file named `__init__.py` turns its folder into a Python "package". Any
    names it imports become available as `scenarios.<name>`. This is called
    "re-exporting".
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# The leading dot in `.mcas` means "the mcas module in this same package"
# (a "relative import"). These two lines pull the scenario lists up to the
# package level so callers can import them from `scenarios` directly.
# ===========================================================================

from .mcas import MCAS_SCENARIO
from .therac25 import PASS_1_INCIDENTS, PASS_2_SUPPRESSION

# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# __all__ — the official list of public names this package exports.
#   It controls what `from scenarios import *` brings in, and it tells
#   readers (and linters) that these three imports are deliberate
#   re-exports, not unused imports.
__all__ = ["MCAS_SCENARIO", "PASS_1_INCIDENTS", "PASS_2_SUPPRESSION"]

# EXEUNT — end of file.

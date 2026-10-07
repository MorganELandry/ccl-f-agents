"""
THE MCAS EVIDENCE CHECK
A Play in Three Scenes
======================

PROLOGUE
--------
Tests for MCAS scenario structure. No LLM calls required.

MCAS (the Maneuvering Characteristics Augmentation System) was the flight
software at the centre of the Boeing 737 MAX accidents. scenarios/mcas.py
retells that history as five evidence items, fed to the agent one at a time.
Each item is a plain dict with "evidence_id", "content" and "source".

These tests make sure that data is fit to use: the right number of items,
no duplicate IDs, and every item can be turned into a real Evidence object.

Run: pytest tests/ -v

THE PLAYBILL
    Scene 1  test_mcas_has_five_items              exactly five evidence items
    Scene 2  test_mcas_evidence_ids_unique         no ID is used twice
    Scene 3  test_mcas_items_build_valid_evidence  each dict builds an Evidence
                                                   (run once per item)

READER'S NOTE — plain test functions
    Unlike test_guards.py, these tests are top-level functions, not methods
    in a class. pytest collects any function whose name starts with `test_`
    in a file whose name starts with `test_`; classes are optional.

READER'S NOTE — @pytest.mark.parametrize
    Scene 3 is written once but runs five times, once per evidence item.
    The decorator line

        @pytest.mark.parametrize("item", MCAS_SCENARIO, ids=...)

    tells pytest: "for every element of MCAS_SCENARIO, call this test with
    that element passed in as the argument named `item`." Each call is
    reported as its own test, so a failure names exactly which item broke.
    `ids=` gives each run a readable label; here a small lambda (an unnamed
    one-line function) picks the item's evidence_id, so the runs show up as
    test_mcas_items_build_valid_evidence[mcas-001], [mcas-002], and so on.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest         needed here for the @pytest.mark.parametrize decorator.
# cclf.types     the Evidence dataclass each scenario item must fit into.
# scenarios      MCAS_SCENARIO, the list of five evidence dicts under test.
#                (Importable from tests/ because pytest.ini sets
#                `pythonpath = . tests`; see tests/test_guards.py.)
# ===========================================================================

import pytest
from cclf.types import Evidence
from scenarios import MCAS_SCENARIO


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# (none) — the only data used is MCAS_SCENARIO, which is imported above.
# ===========================================================================


# ===========================================================================
# SCENE 1 — A CAST OF FIVE
# Proves: the MCAS scenario has exactly five evidence items.
# ===========================================================================

def test_mcas_has_five_items():
    """
    MCAS_SCENARIO contains five items.

    Enter:   (nothing)
    Exit:    passes if len(MCAS_SCENARIO) == 5

    The demo and the end-to-end tests feed these items one per graph cycle,
    so a changed count would quietly change what those runs exercise.
    """
    # --- Setting the stage / The action / The verdict ----------------------
    assert len(MCAS_SCENARIO) == 5


# ===========================================================================
# SCENE 2 — NO TWINS
# Proves: every evidence_id in the scenario is unique.
# ===========================================================================

def test_mcas_evidence_ids_unique():
    """
    No two MCAS items share an evidence_id.

    Enter:   (nothing)
    Exit:    passes if the list of IDs has no repeats
    """
    # PLAYERS IN THIS SCENE
    #   ids   every evidence_id, in scenario order

    # --- Setting the stage -------------------------------------------------
    # A list comprehension: one ID pulled out of each dict.
    ids = [item["evidence_id"] for item in MCAS_SCENARIO]
    # --- The verdict -------------------------------------------------------
    # A set drops repeats, so equal lengths mean every ID is distinct.
    assert len(ids) == len(set(ids))


# ===========================================================================
# SCENE 3 — EACH ITEM TAKES THE STAGE
# Proves: every scenario dict can be unpacked into a valid Evidence object.
# (Run once per item; see READER'S NOTE on parametrize.)
# ===========================================================================

@pytest.mark.parametrize("item", MCAS_SCENARIO, ids=lambda i: i["evidence_id"])
def test_mcas_items_build_valid_evidence(item):
    """
    One scenario dict builds an Evidence with its ID, content and source.

    Enter:   item   one evidence dict from MCAS_SCENARIO, supplied by
                    pytest through parametrize
    Exit:    passes if Evidence(**item) succeeds and keeps the right fields
    """
    # PLAYERS IN THIS SCENE
    #   ev   the Evidence object built from `item`

    # --- The action --------------------------------------------------------
    # `**item` unpacks the dict into keyword arguments, so
    # Evidence(**{"evidence_id": "x", ...}) means Evidence(evidence_id="x", ...).
    # A missing or misspelled key would raise TypeError here and fail the test.
    ev = Evidence(**item)

    # --- The verdict -------------------------------------------------------
    # `ev.content and ev.source` is truthy only if both strings are non-empty.
    assert ev.evidence_id == item["evidence_id"]
    assert ev.content and ev.source

# EXEUNT — end of file.

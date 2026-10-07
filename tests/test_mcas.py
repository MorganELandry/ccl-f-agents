"""
Tests for MCAS scenario structure. No LLM calls required.

Run: pytest tests/ -v
"""

import pytest
from cclf.types import Evidence
from scenarios import MCAS_SCENARIO


def test_mcas_has_five_items():
    assert len(MCAS_SCENARIO) == 5


def test_mcas_evidence_ids_unique():
    ids = [item["evidence_id"] for item in MCAS_SCENARIO]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("item", MCAS_SCENARIO, ids=lambda i: i["evidence_id"])
def test_mcas_items_build_valid_evidence(item):
    ev = Evidence(**item)
    assert ev.evidence_id == item["evidence_id"]
    assert ev.content and ev.source

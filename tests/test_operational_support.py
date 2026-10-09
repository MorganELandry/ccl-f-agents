"""
THE WEAKEST LINK
A Play in Six Scenes
====================

PROLOGUE
--------
Tests for Supervisor.operational_support(), the weakest-link report over a
decision's critical claims (Layer 4, Coherence Score, October 2026: "the
operational coherence of a decision is bounded by the lowest operational
coherence among its critical claims"; Narrative Coherence and Operational
Coherence, "Zero operational support").

What the spec fixes:
  - critical claims are not averaged: one critical claim with no
    evidence-closed support has operational support zero, whatever the
    state of every other claim;
  - "operational coherence reaches zero when no evidence-closed loops remain
    backing the claim, that is, when every closure supporting it is an
    authority closure";
  - criticality is domain-configured, and the standard behind it is recorded.

What the code decides (implementation decision D10): the critical claims
are the decision's high-consequence signals (D9); a claim's support is its
chain-sound evidence closures over its real closures; a critical claim with
no real closure has support 0.

THE PLAYBILL
    Prelude   sv (fixture)
    Scene 1   test_authority_closed_critical_claim_has_zero_support
    Scene 2   test_unclosed_critical_claim_has_zero_support
    Scene 3   test_non_critical_signals_are_not_claims
    Scene 4   test_scheme_is_reported_from_settings
    Scene 5   test_report_changes_nothing
    Scene 6   test_challenger_field_joint_claim_has_zero_support
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest            fixtures.
# cclf              SignalType, Supervisor.
# cclf.supervisor   Settings.
# cclf.graph        replay, for the Challenger scenario.
# cclf.advisor      Advisor, run offline.
# scenarios         SCENARIOS.
# stagehands        CUST, add_ees, decision, to_review.
# ===========================================================================

import pytest

from cclf import SignalType, Supervisor
from cclf.advisor import Advisor
from cclf.graph import replay
from cclf.supervisor import Settings
from scenarios import SCENARIOS
from stagehands import CUST, add_ees, decision, to_review


# ===========================================================================
# DRAMATIS PERSONAE
# ===========================================================================

# C, U — a critical (constraint) and a non-critical (uncertainty) signal type.
C = SignalType.CONSTRAINT
U = SignalType.UNCERTAINTY


# ===========================================================================
# THE FIXTURE
# ===========================================================================

@pytest.fixture
def sv():
    """
    A new, empty Supervisor.

    Enter:   (nothing)
    Exit:    Supervisor()
    """
    return Supervisor()


# ===========================================================================
# SCENE 1 — A STRONG CLAIM DOES NOT COVER A WEAK ONE
# Proves: an evidence-closed critical claim does not offset an
# authority-closed one; the authority-closed claim is the weakest link at 0.
# ===========================================================================

def test_authority_closed_critical_claim_has_zero_support(sv):
    """
    One critical claim evidence-closed, one authority-closed.

    Enter:   sv   an empty Supervisor
    Exit:    passes if the authority-closed claim has support 0, is listed
             in zero_support, and is the weakest; the other has support 1
    """
    to_review(sv, "good", C)
    to_review(sv, "bad", C)
    add_ees(sv, "ev-good", ["good"])
    sv.attempt_closure("good", "chief-engineer", CUST, ["ev-good"])
    sv.attempt_closure("bad", "program-manager", CUST, [])
    decision(sv, "d", ["good", "bad"])
    report = sv.operational_support("d")
    assert report["claims"]["good"]["support"] == 1.0
    assert report["claims"]["bad"]["support"] == 0.0
    assert report["zero_support"] == ["bad"]
    assert report["weakest"] == "bad" and report["weakest_support"] == 0.0


# ===========================================================================
# SCENE 2 — NOTHING BEHIND IT
# Proves: a critical claim with no closure at all has support 0.
# ===========================================================================

def test_unclosed_critical_claim_has_zero_support(sv):
    """
    A critical claim still under review.

    Enter:   sv   an empty Supervisor
    Exit:    passes if its support is 0 with zero closures counted
    """
    to_review(sv, "open", C)
    decision(sv, "d", ["open"])
    report = sv.operational_support("d")
    assert report["claims"]["open"] == {"support": 0.0, "evidence_closures": 0, "closures": 0}
    assert report["zero_support"] == ["open"]


# ===========================================================================
# SCENE 3 — ONLY CRITICAL CLAIMS COUNT
# Proves: a non-critical signal is not a critical claim, and a decision with
# none reports no weakest link.
# ===========================================================================

def test_non_critical_signals_are_not_claims(sv):
    """
    A decision whose only signal is an uncertainty.

    Enter:   sv   an empty Supervisor
    Exit:    passes if no claims are reported and weakest is None
    """
    to_review(sv, "u", U)
    decision(sv, "d", ["u"])
    report = sv.operational_support("d")
    assert report["claims"] == {} and report["zero_support"] == []
    assert report["weakest"] is None and report["weakest_support"] is None


# ===========================================================================
# SCENE 4 — WHOSE STANDARD
# Proves: the domain's criticality scheme is reported with the result.
# ===========================================================================

def test_scheme_is_reported_from_settings():
    """
    A Supervisor configured with a criticality scheme.

    Enter:   (nothing)
    Exit:    passes if the report names the scheme, and the default is ""
    """
    sv = Supervisor(Settings(criticality_scheme="NASA Criticality 1"))
    to_review(sv, "c", C)
    decision(sv, "d", ["c"])
    assert sv.operational_support("d")["scheme"] == "NASA Criticality 1"
    assert Settings().criticality_scheme == ""


# ===========================================================================
# SCENE 5 — A REPORT, NOT AN OPERATION
# Proves: asking for the report writes nothing and moves the clock not at all.
# ===========================================================================

def test_report_changes_nothing(sv):
    """
    The audit log and clock before and after the report.

    Enter:   sv   an empty Supervisor
    Exit:    passes if both are unchanged
    """
    to_review(sv, "c", C)
    decision(sv, "d", ["c"])
    before = (len(sv.audit.entries()), sv.clock)
    sv.operational_support("d")
    assert (len(sv.audit.entries()), sv.clock) == before


# ===========================================================================
# SCENE 6 — THE NIGHT BEFORE
# Proves: in the Challenger replay, the claim that the field joint would
# seal at the forecast temperature has zero operational support, and the
# weakest link of the launch decision is at zero.
# ===========================================================================

def test_challenger_field_joint_claim_has_zero_support():
    """
    Replay Challenger and read the launch decision's weakest link.

    Enter:   (nothing)
    Exit:    passes if cold-oring-no-launch is at zero support and the
             weakest support is 0
    """
    sv = replay(SCENARIOS["challenger"], advisor=Advisor(ask=lambda system, user: ""))
    report = sv.operational_support("launch-51L")
    assert "cold-oring-no-launch" in report["zero_support"]
    assert report["weakest_support"] == 0.0

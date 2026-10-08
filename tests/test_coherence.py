"""
A SCORE FOR INTEGRITY
A Play in Ten Scenes
====================

PROLOGUE
--------
Tests for Supervisor.coherence(), the coherence score of CCL-F v0.2 Layer 4
(Layer 4, Coherence Score; Key Definitions, Coherence Score).

What the spec fixes:
  - a continuous score between 0.0 and 1.0 for one decision node;
  - five factors with provisional weights: open loops 0.30, classification
    stability 0.25, closure quality 0.20, recurrence pressure 0.15,
    authority compression 0.10;
  - the closure-quality history of a loop "(including how many times it
    has been reopened, and from which closure types) is itself a
    coordination signal feeding recurrence tracking and the coherence
    score" (Layer 4, Commitment State Machine).

What the spec leaves open: how each factor is computed. The code's
formulas (implementation decision D3) give each factor a value in [0, 1],
1 being healthy. Tests of factor behaviour are therefore labelled
implementation-decision tests, and check only direction (worse history,
lower factor), not exact numbers, except where a number is the obvious
reading of the factor's name.

THE PLAYBILL
    Prelude   sv (fixture), factors() and evidence_close() (helpers)
    Scene 1   test_weights_match_spec_and_sum_to_one
    Scene 2   test_score_is_the_weighted_sum_of_factors_in_range
    Scene 3   test_healthy_decision_scores_one
    Scene 4   test_open_loops_factor                         (impl. decision D3)
    Scene 5   test_classification_stability_factor           (impl. decision D3)
    Scene 6   test_closure_quality_factor                    (impl. decision D3)
    Scene 7   test_recurrence_pressure_factor                (impl. decision D3)
    Scene 8   test_authority_compression_factor              (impl. decision D3)
    Scene 9   test_attempted_closures_do_not_count           (impl. decision D3)
    Scene 10  test_reopen_history_feeds_the_score            (was a spec mismatch; now fixed)

READER'S NOTE — pytest.approx
    Floating-point sums such as 0.3 + 0.25 + 0.2 + 0.15 + 0.1 may come out as
    0.9999999999999999. `x == pytest.approx(1.0)` compares with a small
    tolerance, so tiny rounding differences do not fail the test.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest            fixtures and approx.
# cclf              OperationalState, SignalType, Supervisor.
# cclf.supervisor   COHERENCE_WEIGHTS, the code's weight table.
# stagehands        CUST, TECH, PROCESS, to_review, add_ees, decision.
# ===========================================================================

import pytest

from cclf import OperationalState, SignalType, Supervisor
from cclf.supervisor import COHERENCE_WEIGHTS
from stagehands import CUST, PROCESS, TECH, add_ees, decision, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# SPEC_WEIGHTS — the spec's weight table (Layer 4, Coherence Score), typed
#   out by hand.
SPEC_WEIGHTS = {
    "open_loops": 0.30,
    "classification_stability": 0.25,
    "closure_quality": 0.20,
    "recurrence_pressure": 0.15,
    "authority_compression": 0.10,
}

# U — the signal type used for most scenes: an uncertainty signal is not a
#   constraint, so no closure here sets off a constraint-only escalation.
U = SignalType.UNCERTAINTY


# ===========================================================================
# THE FIXTURE AND A HELPER
# ===========================================================================

@pytest.fixture
def sv():
    """
    A new, empty Supervisor.

    Enter:   (nothing)
    Exit:    Supervisor()
    """
    return Supervisor()


def factors(sv, decision_id="d"):
    """
    The factor dict for a decision.

    Enter:   sv, decision_id   which supervisor and decision
    Exit:    dict factor-name -> value
    """
    return sv.coherence(decision_id)[1]


def evidence_close(sv, signal_id, closer="chief-engineer"):
    """
    Close a signal under review with novel independent evidence.

    Enter:   sv, signal_id   a signal under review
             closer          who closes it
    Exit:    the ClosureRecord
    """
    add_ees(sv, f"ev-{signal_id}-{len(sv.evidence)}", [signal_id])
    return sv.attempt_closure(signal_id, closer, CUST, [f"ev-{signal_id}-{len(sv.evidence) - 1}"])


# ===========================================================================
# SCENE 1 — THE WEIGHTS ON THE PAGE
# Proves: the code's weights are the spec's, and they sum to 1, so a fully
# healthy node scores exactly 1.0.
# ===========================================================================

def test_weights_match_spec_and_sum_to_one():
    """
    COHERENCE_WEIGHTS equals the spec table and sums to 1.

    Enter:   (nothing)
    Exit:    passes if both hold
    """
    assert COHERENCE_WEIGHTS == SPEC_WEIGHTS
    assert sum(COHERENCE_WEIGHTS.values()) == pytest.approx(1.0)


# ===========================================================================
# SCENE 2 — ONE NUMBER FROM FIVE
# Proves: the score is the weighted sum of the five reported factors, and
# score and factors all lie in [0, 1] (Layer 4, Coherence Score).
# ===========================================================================

def test_score_is_the_weighted_sum_of_factors_in_range(sv):
    """
    score == sum(weight * factor), everything within [0, 1], on a messy node.

    Enter:   sv   fixture
    Exit:    passes if the identity and ranges hold
    """
    # PLAYERS IN THIS SCENE
    #   score, f   the score and its factor dict

    to_review(sv, "a", signal_type=U)
    to_review(sv, "b", signal_type=U)
    sv.classify("b", OperationalState.EXPERIMENTAL, "eng")
    sv.attempt_closure("a", "vp", CUST)
    decision(sv, "d", ["a", "b"])
    score, f = sv.coherence("d")
    assert set(f) == set(SPEC_WEIGHTS)
    assert score == pytest.approx(sum(SPEC_WEIGHTS[k] * f[k] for k in f), abs=1e-3)
    assert 0.0 <= score <= 1.0 and all(0.0 <= v <= 1.0 for v in f.values())


# ===========================================================================
# SCENE 3 — A CLEAN NODE
# Proves: one signal, evidence-closed, stable, no recurrence: every factor
# 1.0 and the score 1.0.
# ===========================================================================

def test_healthy_decision_scores_one(sv):
    """
    A decision over one evidence-closed signal scores 1.0.

    Enter:   sv   fixture
    Exit:    passes if the score and every factor are 1.0

    One signal is enough. Authority compression counts only non-evidence
    closures (see Scene 8), so a node made only of chain-sound evidence
    closures scores 1.0 on that factor however many closers it has.
    """
    to_review(sv, "a", signal_type=U)
    evidence_close(sv, "a")
    decision(sv, "d", ["a"])
    assert sv.coherence("d") == (1.0, {k: 1.0 for k in SPEC_WEIGHTS})


# ===========================================================================
# SCENE 4 — OPEN LOOPS
# Proves: more open loops, lower factor; a trajectory-locked loop still
# counts as open ("the loop remained open", Layer 4, Commitment State
# Machine).
# ===========================================================================

def test_open_loops_factor(sv):
    """
    Implementation-decision test (D3: factor = 1 - open-or-locked / signals).
    One of two open gives 0.5; after an override locks the constraint, it
    still counts as open.

    Enter:   sv   fixture
    Exit:    passes if the factor is 0.5 before and after the lock
    """
    to_review(sv, "c")
    to_review(sv, "u", signal_type=U)
    evidence_close(sv, "u")
    decision(sv, "d", ["c", "u"])
    assert factors(sv)["open_loops"] == 0.5
    sv.request_execution("d", "director", override_rationale="go")
    assert sv.signals["c"].state.value == "trajectory_lock"
    assert factors(sv)["open_loops"] == 0.5


# ===========================================================================
# SCENE 5 — CLASSIFICATION STABILITY
# Proves: reclassifying a signal during review lowers the stability factor.
# ===========================================================================

def test_classification_stability_factor(sv):
    """
    Implementation-decision test (D3/D8: share of signals not reclassified
    to a different state since review opened). Reclassifying one of two
    signals halves it.

    Enter:   sv   fixture
    Exit:    passes if the factor goes from 1.0 to 0.5
    """
    to_review(sv, "a", signal_type=U)
    to_review(sv, "b", signal_type=U)
    decision(sv, "d", ["a", "b"])
    assert factors(sv)["classification_stability"] == 1.0
    sv.classify("a", OperationalState.EXPERIMENTAL, "eng")
    assert factors(sv)["classification_stability"] == 0.5


# ===========================================================================
# SCENE 6 — CLOSURE QUALITY
# Proves: authority closure scores worse than evidence closure (Layer 2:
# evidence "Valid", authority "Flagged").
# ===========================================================================

def test_closure_quality_factor(sv):
    """
    Implementation-decision test (D3: chain-sound evidence closures divided
    by real closures plus reopens). One evidence and one authority closure,
    with no reopens, gives 0.5.

    Enter:   sv   fixture
    Exit:    passes if the factor is 0.5
    """
    to_review(sv, "a", signal_type=U)
    to_review(sv, "b", signal_type=U)
    evidence_close(sv, "a")
    sv.attempt_closure("b", "vp", CUST)
    decision(sv, "d", ["a", "b"])
    assert factors(sv)["closure_quality"] == 0.5


# ===========================================================================
# SCENE 7 — RECURRENCE PRESSURE
# Proves: pressure rises as an unreviewed recurrence group grows, and is
# relieved once its structural review documents a model update.
# ===========================================================================

def test_recurrence_pressure_factor(sv):
    """
    Implementation-decision test (D3: 1 - min(1, members / threshold) for
    the worst unreviewed group). The factor falls as members are added and
    returns to 1.0 after the group's review is resolved.

    Enter:   sv   fixture
    Exit:    passes if the factor sequence is strictly falling, then 1.0
    """
    # PLAYERS IN THIS SCENE
    #   seen   factor values after each new member
    #   n      each member number 1-3 of recurrence group "g"

    seen = []
    decision(sv, "d", [], accept=False)
    for n in (1, 2, 3):
        sv.register_signal(f"m{n}", U, "d", "eng", TECH, PROCESS, recurrence_group="g")
        sv.link_signal("d", f"m{n}", "clerk")
        seen.append(factors(sv)["recurrence_pressure"])
    assert seen[0] > seen[1] > seen[2] == 0.0
    sv.resolve_review("R1", "board", "redesign")
    assert factors(sv)["recurrence_pressure"] == 1.0


# ===========================================================================
# SCENE 8 — AUTHORITY COMPRESSION
# Proves: non-evidence closures concentrated in one agent's hands lower the
# factor.
# ===========================================================================

def test_authority_compression_factor(sv):
    """
    Implementation-decision test (D3: 1 - the largest share of all real
    closures made by one agent's non-evidence closures, once there are at
    least two closures and at least one is non-evidence). Two authority
    closures by two agents gives 0.5; by one agent gives 0.0.

    Enter:   sv   fixture
    Exit:    passes if the spread node scores 0.5 and the concentrated one 0.0
    """
    # PLAYERS IN THIS SCENE
    #   sid, closer   each signal id and the agent who authority-closes it

    for sid, closer in (("a", "vp-1"), ("b", "vp-2"), ("c", "vp-1"), ("e", "vp-1")):
        to_review(sv, sid, signal_type=U)
        sv.attempt_closure(sid, closer, CUST)
    decision(sv, "spread", ["a", "b"], accept=False)
    decision(sv, "concentrated", ["c", "e"], accept=False)
    assert factors(sv, "spread")["authority_compression"] == 0.5
    assert factors(sv, "concentrated")["authority_compression"] == 0.0


# ===========================================================================
# SCENE 9 — ATTEMPTS ARE NOT RESOLUTIONS
# Proves: attempted closure "does not constitute loop resolution" (Layer 3,
# Autonomy-Bounded Closure, Attempted Closure), so it does not count as a
# closure in the score.
# ===========================================================================

def test_attempted_closures_do_not_count(sv):
    """
    Implementation-decision test (D3). An attempted closure from outside
    the closure authority leaves closure quality at 1.0 and the loop open.

    Enter:   sv   fixture
    Exit:    passes if closure_quality is 1.0 and open_loops is 0.0
    """
    # PLAYERS IN THIS SCENE
    #   f   the factor dict for decision "d"

    to_review(sv, "a", signal_type=U, closure_authority=["chief"])
    sv.attempt_closure("a", "outsider", CUST)
    decision(sv, "d", ["a"])
    f = factors(sv)
    assert f["closure_quality"] == 1.0 and f["open_loops"] == 0.0


# ===========================================================================
# SCENE 10 — A LOOP THAT HAD TO BE REOPENED
# Proves: (Layer 4, Commitment State Machine) how many times a loop was
# reopened feeds the coherence score.
# ===========================================================================

def test_reopen_history_feeds_the_score():
    """
    A reopened-and-reclosed loop scores below a node with the same closure
    mix and no reopen.

    Enter:   (nothing)
    Exit:    passes if the reopened node's score is lower

    Both nodes hold exactly two evidence closures, by lab-1 and lab-2, and
    no open loops, so every D3 factor would be equal between them. The only
    difference is that in `reopened` the first closure was invalidated and
    superseded, and closure_quality counts that reopen as a closure that
    did not hold (2 / (2 + 1) instead of 2 / 2).
    """
    # PLAYERS IN THIS SCENE
    #   clean      two signals, each evidence-closed once
    #   reopened   one signal, closed, reopened, closed again
    #   sid, lab   each of clean's signals and the lab that evidence-closes it

    clean, reopened = Supervisor(), Supervisor()
    for sid, lab in (("a", "lab-1"), ("b", "lab-2")):
        to_review(clean, sid, signal_type=U)
        evidence_close(clean, sid, lab)
    decision(clean, "d", ["a", "b"], accept=False)
    to_review(reopened, "a", signal_type=U)
    evidence_close(reopened, "a", "lab-1")
    reopened.reopen("a", "auditor", "the test data were invalid")
    evidence_close(reopened, "a", "lab-2")
    decision(reopened, "d", ["a"], accept=False)
    assert reopened.coherence("d")[0] < clean.coherence("d")[0]

# EXEUNT — end of file.

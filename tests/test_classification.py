"""
WHAT STATE ARE WE IN?
A Play in Nine Scenes
=====================

PROLOGUE
--------
Tests for Supervisor.classify(), which implements CCL-F v0.2 Rule 2,
"Classification Precedes Action" (Layer 1, Rule 2), together with the
five operational states of Key Definitions (Operational State).

What the spec requires, and what each scene checks:

  "Unvalidated conditions cannot be classified as nominal" (Rule 2, What it
    requires and What to do).
  "Classification must be supported by evidence, not assumed" (Rule 2,
    What to do).
    The runtime reads "validated" through the EES test: nominal needs at
    least one cited item of External Evidence Source evidence. Anything
    less is recorded as elevated uncertainty, and the refusal is audited.
  "Classification into any state other than nominal does not block
    execution — it determines what coordination requirements apply"
    (Key Definitions, Operational State): non-nominal classifications are accepted as given.
  registered -> classified is "required before review opens" (Layer 4,
    Commitment State Machine).
  The Therac-25 pattern (Rule 3, Cases): an assertion that no
    malfunction occurred is not validating evidence.

THE PLAYBILL
    Scene 1   test_nominal_without_evidence_is_refused
    Scene 2   test_nominal_with_non_ees_evidence_is_refused   (parametrized, 3 runs)
    Scene 3   test_nominal_with_classifier_evidence_is_refused
    Scene 3b  test_nominal_with_registrant_evidence_classified_by_another_is_accepted
    Scene 4   test_nominal_with_ees_evidence_is_accepted
    Scene 5   test_non_nominal_states_are_applied_as_given    (parametrized, 4 runs)
    Scene 6   test_classification_moves_registered_to_classified
    Scene 7   test_reclassification_is_recorded_in_history
    Scene 8   test_model_proposals_are_marked_in_the_audit
    Scene 9   test_unclassified_signal_fails_elevated_and_irreversible_gates
                                                              (parametrized, 2 runs)

READER'S NOTE — ids= in parametrize
    `@pytest.mark.parametrize("kind", [...], ids=lambda k: k.value)` gives
    each run a readable name in the report (e.g. "[model_output]") instead
    of "[kind0]". The lambda turns each value into its label.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       fixtures and parametrize.
# cclf         CommitmentState, EvidenceKind, ExecutionClass,
#              OperationalState, SignalType, Supervisor.
# stagehands   TECH, PROCESS, add_ees, add_non_ees, decision, entries.
# ===========================================================================

import pytest

from cclf import (
    CommitmentState, EvidenceKind, ExecutionClass, OperationalState, SignalType, Supervisor,
)
from stagehands import PROCESS, TECH, add_ees, add_non_ees, decision, entries


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# O — short alias for OperationalState.
O = OperationalState

# NON_NOMINAL — the four states the spec lets anyone choose without evidence.
NON_NOMINAL = [O.ELEVATED_UNCERTAINTY, O.OFF_ENVELOPE, O.EXPERIMENTAL, O.CONTAINMENT]


# ===========================================================================
# THE FIXTURE — a supervisor holding one freshly registered signal
# ===========================================================================

@pytest.fixture
def sv():
    """
    A Supervisor with one registered (not yet classified) uncertainty signal.

    Enter:   (nothing)
    Exit:    a Supervisor whose signal "s" is in state `registered`,
             registered by "engineer" about PROCESS
    """
    # PLAYERS IN THIS SCENE
    #   s   the new Supervisor

    s = Supervisor()
    s.register_signal("s", SignalType.UNCERTAINTY, "seal margin", "engineer", TECH, PROCESS)
    return s


# ===========================================================================
# SCENE 1 — "IT'S FINE" IS NOT A CLASSIFICATION
# Proves: nominal with no evidence becomes elevated uncertainty, and the
# refusal is logged (Rule 2: Classification Precedes Action).
# ===========================================================================

def test_nominal_without_evidence_is_refused(sv):
    """
    classify(nominal) with no evidence applies elevated_uncertainty.

    Enter:   sv   fixture
    Exit:    passes if the returned and stored state is elevated_uncertainty
             and one CLASSIFICATION_REJECTED entry records proposed=nominal
    """
    # PLAYERS IN THIS SCENE
    #   applied    the state classify() actually applied
    #   rejected   the CLASSIFICATION_REJECTED audit entries

    # --- The action --------------------------------------------------------
    applied = sv.classify("s", O.NOMINAL, "manager")
    # --- The verdict -------------------------------------------------------
    assert applied == O.ELEVATED_UNCERTAINTY
    assert sv.signals["s"].operational_state == O.ELEVATED_UNCERTAINTY
    rejected = entries(sv, "CLASSIFICATION_REJECTED")
    assert len(rejected) == 1
    assert rejected[0].payload["proposed"] == "nominal"
    assert rejected[0].actor == "manager"


# ===========================================================================
# SCENE 2 — THE WRONG KIND OF SUPPORT
# Proves: model output, a bare assertion (Therac-25's "could not have been
# produced by any malfunction") and internal analysis do not validate a
# nominal classification. (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("kind", [EvidenceKind.MODEL_OUTPUT, EvidenceKind.ASSERTION,
                                  EvidenceKind.INTERNAL_ANALYSIS], ids=lambda k: k.value)
def test_nominal_with_non_ees_evidence_is_refused(sv, kind):
    """
    Nominal citing only non-EES evidence is refused.

    Enter:   sv     fixture
             kind   a non-EES evidence kind
    Exit:    passes if elevated_uncertainty is applied
    """
    add_non_ees(sv, "e1", kind, ["s"])
    assert sv.classify("s", O.NOMINAL, "manager", ["e1"]) == O.ELEVATED_UNCERTAINTY


# ===========================================================================
# SCENE 3 — MARKING ONE'S OWN HOMEWORK
# Proves: evidence produced by the CLASSIFYING agent does not validate their
# own nominal classification (Layer 2, External Evidence Source: the
# producer is not "the registering or reclassifying agent, for a reversal
# path or a classification").
# ===========================================================================

def test_nominal_with_classifier_evidence_is_refused(sv):
    """
    A direct measurement produced by the classifier does not validate nominal.

    Enter:   sv   fixture
    Exit:    passes if elevated_uncertainty is applied
    """
    add_ees(sv, "e1", ["s"], produced_by="manager")
    assert sv.classify("s", O.NOMINAL, "manager", ["e1"]) == O.ELEVATED_UNCERTAINTY


# ===========================================================================
# SCENE 3b — THE REGISTRANT'S MEASUREMENT, SOMEONE ELSE'S CLAIM
# Proves: the registrant is no longer excluded as such. Under the one EES
# definition, a measurement the registrant took can validate a nominal
# classification another agent makes ("A common cause in the world is not
# a shared error").
# ===========================================================================

def test_nominal_with_registrant_evidence_classified_by_another_is_accepted(sv):
    """
    Setting the stage: evidence produced by the registrant ("engineer").
    The action: "manager" classifies nominal citing it. The verdict: nominal
    is applied, and the classification record names the classifier.

    Enter:   sv   fixture
    Exit:    passes if nominal is applied and recorded as manager's
    """
    add_ees(sv, "e1", ["s"], produced_by="engineer")
    assert sv.classify("s", O.NOMINAL, "manager", ["e1"]) == O.NOMINAL
    assert sv.signals["s"].classification_records[-1].by == "manager"
    assert sv.signals["s"].classification_records[-1].evidence_ids == ("e1",)


# ===========================================================================
# SCENE 4 — VALIDATED, THEREFORE NOMINAL
# Proves: with independent validating evidence, nominal is accepted and no
# rejection is logged.
# ===========================================================================

def test_nominal_with_ees_evidence_is_accepted(sv):
    """
    Nominal citing a primary document from an independent source is accepted.

    Enter:   sv   fixture
    Exit:    passes if nominal is applied and nothing is rejected
    """
    add_ees(sv, "e1", ["s"], kind=EvidenceKind.PRIMARY_DOCUMENT)
    assert sv.classify("s", O.NOMINAL, "manager", ["e1"]) == O.NOMINAL
    assert entries(sv, "CLASSIFICATION_REJECTED") == []


# ===========================================================================
# SCENE 5 — THE OTHER FOUR STATES NEED NO PERMISSION
# Proves: Key Definitions, Operational State: non-nominal classification is applied as given; it
# changes requirements rather than being refused. (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("state", NON_NOMINAL, ids=lambda s: s.value)
def test_non_nominal_states_are_applied_as_given(sv, state):
    """
    Each non-nominal state is applied without evidence and without rejection.

    Enter:   sv      fixture
             state   one of NON_NOMINAL
    Exit:    passes if classify returns `state` and logs no rejection
    """
    assert sv.classify("s", state, "engineer") == state
    assert entries(sv, "CLASSIFICATION_REJECTED") == []


# ===========================================================================
# SCENE 6 — CLASSIFIED BEFORE REVIEWED
# Proves: Layer 4, Commitment State Machine: classification moves registered -> classified, and is
# what lets review open.
# ===========================================================================

def test_classification_moves_registered_to_classified(sv):
    """
    classify() takes the signal from registered to classified.

    Enter:   sv   fixture
    Exit:    passes if the state is classified afterwards and review then opens
    """
    sv.classify("s", O.EXPERIMENTAL, "engineer")
    assert sv.signals["s"].state == CommitmentState.CLASSIFIED
    sv.open_review("s", "engineer")
    assert sv.signals["s"].state == CommitmentState.UNDER_REVIEW


# ===========================================================================
# SCENE 7 — THE RECORD OF EVERY LABEL
# Proves: every classification, including a rejected nominal, lands in the
# signal's classification history (what Rule 3's stability test reads).
# ===========================================================================

def test_reclassification_is_recorded_in_history(sv):
    """
    Two classifications leave two history entries, the applied states in order.

    Enter:   sv   fixture
    Exit:    passes if history holds [elevated_uncertainty, experimental]
    """
    sv.classify("s", O.NOMINAL, "manager")          # rejected -> elevated
    sv.classify("s", O.EXPERIMENTAL, "engineer")
    assert [st for _, st in sv.signals["s"].classification_history] == \
        [O.ELEVATED_UNCERTAINTY, O.EXPERIMENTAL]


# ===========================================================================
# SCENE 8 — WHO PROPOSED IT?
# Proves: a model's proposal is marked as such in the audit, so the record
# shows when probabilistic automation tried to call something nominal
# (AI Applications, Three Applications).
# ===========================================================================

def test_model_proposals_are_marked_in_the_audit(sv):
    """
    proposed_by_model=True is carried into both audit entries.

    Enter:   sv   fixture
    Exit:    passes if CLASSIFICATION_REJECTED and CLASSIFIED both record
             proposed_by_model True
    """
    sv.classify("s", O.NOMINAL, "advisor", proposed_by_model=True)
    assert entries(sv, "CLASSIFICATION_REJECTED")[0].payload["proposed_by_model"] is True
    assert entries(sv, "CLASSIFIED")[0].payload["proposed_by_model"] is True


# ===========================================================================
# SCENE 9 — NO DECISION WITHOUT A CLASSIFICATION
# Proves: Rule 2, "Every execution-class decision requires explicit
# operational state classification"; the elevated and irreversible gates
# both refuse, with a "classification not acknowledged" failure.
# ===========================================================================

@pytest.mark.parametrize("cls", [ExecutionClass.ELEVATED, ExecutionClass.IRREVERSIBLE],
                         ids=lambda c: c.value)
def test_unclassified_signal_fails_elevated_and_irreversible_gates(sv, cls):
    """
    An execution request over an unclassified signal is not permitted.

    Enter:   sv    fixture (signal "s" registered, unclassified)
             cls   ELEVATED or IRREVERSIBLE
    Exit:    passes if the gate refuses and a failure reads "classification
             not acknowledged"
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult

    decision(sv, "d", ["s"], cls)
    result = sv.request_execution("d", "director")
    assert not result.permitted
    assert any("classification not acknowledged" in f for f in result.failures)

# EXEUNT — end of file.

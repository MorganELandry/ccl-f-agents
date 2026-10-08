"""
THE EXECUTION CLASS
A Play in Thirty-Nine Scenes
============================

PROLOGUE
--------
Acceptance tests for the October 2026 "Execution Class Assignment" change
to the CCL-F v0.2 draft. They were written from the specification text
alone (the Execution Class Assignment subsection of Layer 4, the new tenth
Escalation Condition, the Reversal Path Key Definition and the changelog
entry), plus the API notes for the new calls, not from the implementation.
Each scene quotes, or closely paraphrases, the spec sentence it proves.

The bypass being closed, in the changelog's words: "the execution class was
whatever the registering agent declared, so an irreversible launch
registered as routine passed with no gate requirement beyond registration."

The rule that closes it: "Every execution-class decision is irreversible
unless shown otherwise." A decision may hold the elevated or routine class
"only if it has a registered reversal path ... supported by at least one
External Evidence Source showing that the path has been tested".

How the scenes build a world. Most scenes use one constraint signal, "c1",
closed by authority (a reviewer says "fine", no evidence). Such a decision
FAILS the irreversible gate (the constraint is not evidence-closed and there
is no EES in its support) but PASSES the routine and elevated gates. So:
  - blocked, with the constraint failure  -> the irreversible gate was applied;
  - permitted at ROUTINE / ELEVATED        -> the declared lower class applied.
That makes the applied class visible in the verdict, not only in
effective_class().

THE PLAYBILL
    Scenes 1-5    helpers: failures_with(), as_value(), decision_reviews()
                  (Scene 1); authority_world(), sound_world(),
                  reversal_evidence(), register() (Scenes 2-5)
    Scenes 6-10   irreversible by default; the record shows both classes
    Scenes 11-12  a tested reversal path lets the declared class apply
    Scenes 13-22  what does NOT count as a tested reversal path
    Scenes 23-24  no exemption for constraint or anomaly loops
    Scenes 25-32  reclassification: rationale, logging, raising, lowering
    Scenes 33-38  lowering after a blocked request escalates (Scene 33 also
                  holds the helper blocked_then_lowered()); 37b-37c: on a
                  linked decision, and registering under a new identifier
    Scene 39      Rule 4 acceptance still required; unknown evidence ids
                  (two tests)

READER'S NOTE — pytest.mark.parametrize
    `@pytest.mark.parametrize("name", [a, b, c])` runs the same test once
    per value, passing each value in as the argument `name`. pytest reports
    each run as its own test, e.g. test_x[ROUTINE], so a failure names the
    exact value that broke.

READER'S NOTE — pytest.raises
    `with pytest.raises(SomeError):` passes only if the indented block
    raises SomeError (or a subclass). Code after the raising line inside
    the block never runs, so the follow-up checks sit outside it.

READER'S NOTE — enums in the audit trail
    The audit trail stores enum members by their plain value (for example
    "irreversible"), so payload checks compare against `.value`. The helper
    as_value() also accepts a raw enum, so these scenes do not depend on
    which of the two the runtime chose.

READER'S NOTE — new names referenced inside scenes, not at the top
    EscalationCondition.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK is new. It is
    looked up inside the scenes that need it (not in DRAMATIS PERSONAE), so
    that before it exists only those scenes fail, rather than the whole file
    failing to import.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       the test runner; parametrize and raises (see READER'S NOTEs)
# cclf         the runtime under test. From it we use:
#   EscalationCondition  the structural-review conditions (the tenth is new)
#   EvidenceKind         what kind of process produced an item of evidence
#   ExecutionClass       irreversible / elevated / routine
#   OperationalState     the five operational states (Rule 2), for Scene 19
#   SignalType          the six signal types (Rule 1)
#   Supervisor           the Layer 4 supervisor that owns all state
#   TransitionRefused    the error raised when the runtime refuses a move
# stagehands   shared set-up helpers (see tests/stagehands.py). We use
#              to_review(), add_ees(), entries() and the constants; we do
#              NOT use stagehands.decision(), because these scenes need to
#              control the reversal path themselves.
# ===========================================================================

import pytest

from cclf import (
    EscalationCondition, EvidenceKind, ExecutionClass, OperationalState, SignalType,
    Supervisor, TransitionRefused,
)
from stagehands import INDEPENDENT_LAB, PROCESS, TECH, add_ees, entries, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# IRR, ELEV, ROUT — short names for the three execution classes.
IRR = ExecutionClass.IRREVERSIBLE
ELEV = ExecutionClass.ELEVATED
ROUT = ExecutionClass.ROUTINE

# LOWER_CLASSES — the two classes a decision may hold only with a tested
#   reversal path ("the elevated or routine class").
LOWER_CLASSES = [ROUT, ELEV]

# CONSTRAINT_MSG — prefix of the irreversible-gate failure for constraint or
#   anomaly loops that are not evidence-closed. Its presence shows the
#   irreversible gate was applied.
CONSTRAINT_MSG = "constraint/anomaly loops not evidence-closed"

# RISK_MSG — the irreversible-gate failure when the Rule 4 acceptance names
#   no principal risk claim (and so cites no External Evidence Source for
#   one). register() below accepts with the rationale only, so it shows.
RISK_MSG = "no principal risk claim named in the Rule 4 acceptance"

# REVIEW_MSG — prefix of the failure while a downgrade-after-block review is
#   unresolved (from the API notes).
REVIEW_MSG = "unresolved structural reviews"

# RULE4_MSG — prefix of the failure when no named agent accepted the decision.
RULE4_MSG = "Rule 4"

# DOWNGRADE_VALUE — the plain value of the new escalation condition.
DOWNGRADE_VALUE = "execution_class_downgrade_after_block"

# RECLASS_KEYS — payload keys every DECISION_RECLASSIFIED audit entry must
#   carry (the runtime also logs "applied_from" and "applied_to"; Scene 27
#   checks only that these six are present).
RECLASS_KEYS = {"decision", "from", "to", "rationale", "reversal_path", "evidence"}

# REGISTRAR — the agent who registers decisions in these scenes.
REGISTRAR = "registrar"

# RECLASSIFIER — a second agent who changes a decision's class.
RECLASSIFIER = "reclassifier"

# DIRECTOR — the agent who gives Rule 4 acceptance and requests execution.
DIRECTOR = "director"

# REVIEWER — closes "c1" by authority (no evidence) in authority_world().
REVIEWER = "reviewer"

# BOARD — the agent who resolves structural reviews.
BOARD = "review-board"

# PATH — a concrete reversal path, as free text.
PATH = "redeploy the tagged previous build and restore the nightly snapshot"

# ELIGIBLE_KINDS — evidence kinds the EES definition says qualify:
#   "Independent formal or symbolic verification, primary source documents,
#   direct measurement or observation, and evaluation by a party with no
#   causal relationship to the process being evaluated".
ELIGIBLE_KINDS = [
    EvidenceKind.PRIMARY_DOCUMENT, EvidenceKind.DIRECT_MEASUREMENT,
    EvidenceKind.FORMAL_VERIFICATION, EvidenceKind.INDEPENDENT_PARTY,
]

# INELIGIBLE_KINDS — kinds that never qualify as EES (restated conclusions,
#   additional passes by the same kind of reasoning process).
INELIGIBLE_KINDS = [
    EvidenceKind.MODEL_OUTPUT, EvidenceKind.ASSERTION, EvidenceKind.INTERNAL_ANALYSIS,
]


# ===========================================================================
# SCENE 1 — READING THE VERDICT
# Small helpers for reading gate results and audit payloads.
# ===========================================================================

def failures_with(result, prefix):
    """
    Return the failure strings of a GateResult that start with `prefix`.

    Enter:   result   a GateResult from request_execution
             prefix   one of the message prefixes in DRAMATIS PERSONAE
    Exit:    a list of matching strings (empty when that requirement is met)
    """
    return [f for f in result.failures if f.startswith(prefix)]


def as_value(x):
    """
    Return an enum member's plain value, or `x` unchanged if it is not an enum.

    Enter:   x   a payload value (an enum member or a plain string)
    Exit:    the plain value, e.g. "routine"
    """
    return getattr(x, "value", x)


def decision_reviews(sv, decision_id):
    """
    Return every structural review scoped to one decision.

    Enter:   sv, decision_id   the Supervisor and the decision
    Exit:    a list of StructuralReview objects whose scope is
             "decision:<decision_id>" (resolved or not)
    """
    return [r for r in sv.reviews if r.scope == f"decision:{decision_id}"]


# ===========================================================================
# SCENE 2 — A CONSTRAINT WAVED THROUGH
# authority_world(): one loop closed by authority, no evidence anywhere.
# ===========================================================================

def authority_world(sv, signal_type=SignalType.CONSTRAINT):
    """
    Put signal "c1" under review and close it by authority.

    Enter:   sv            the Supervisor
             signal_type   CONSTRAINT (default) or ANOMALY
    Exit:    None. "c1" is closed by REVIEWER with no evidence: an authority
             closure. A decision over it fails the irreversible gate and
             passes the routine and elevated gates.
    """
    to_review(sv, "c1", signal_type)
    sv.attempt_closure("c1", REVIEWER, TECH, [], "I say it is fine")


# ===========================================================================
# SCENE 3 — A CONSTRAINT PROPERLY CLOSED
# sound_world(): one loop closed by chain-sound evidence from outside.
# ===========================================================================

def sound_world(sv):
    """
    Put constraint "c1" under review and close it with independent evidence.

    Enter:   sv   the Supervisor
    Exit:    None. "c1" is evidence-closed with lab evidence that depends on
             no upstream loop, so a decision over it can pass even the
             irreversible gate (given Rule 4 acceptance).
    """
    to_review(sv, "c1")
    add_ees(sv, "close-ev", ["c1"])
    sv.attempt_closure("c1", REVIEWER, TECH, ["close-ev"], "measured")


# ===========================================================================
# SCENE 4 — THE TEST OF THE WAY BACK
# reversal_evidence(): add evidence offered as testing the reversal path.
# ===========================================================================

def reversal_evidence(sv, evidence_id="rev-ev", kind=EvidenceKind.DIRECT_MEASUREMENT,
                      producer=INDEPENDENT_LAB):
    """
    Add one item of evidence about the reversal path (attached to no signal).

    Enter:   sv            the Supervisor
             evidence_id   the new evidence's ID
             kind          its EvidenceKind (default: direct measurement)
             producer      who produced it (default: INDEPENDENT_LAB)
    Exit:    the Evidence object. With the defaults it is an EES for every
             decision in these scenes.
    """
    return sv.add_evidence(evidence_id, "rollback rehearsal record", "test", kind,
                           producer, "evidence-clerk")


# ===========================================================================
# SCENE 5 — THE DECISION ON THE TABLE
# register(): register a decision over "c1", optionally with a reversal path.
# ===========================================================================

def register(sv, declared, path=None, evidence=(), accept=True, decision_id="d1"):
    """
    Register a decision over "c1" by REGISTRAR, and by default accept it.

    Enter:   sv            the Supervisor
             declared      the declared ExecutionClass
             path          the reversal path text, or None
             evidence      reversal evidence ids
             accept        give Rule 4 acceptance by DIRECTOR?
             decision_id   the decision's ID (default "d1")
    Exit:    the Decision object
    """
    # PLAYERS IN THIS SCENE
    #   d   the new Decision (returned)

    d = sv.register_decision(decision_id, f"decision {decision_id}", declared, ["c1"],
                             REGISTRAR, reversal_path=path,
                             reversal_evidence_ids=list(evidence))
    if accept:
        sv.accept_decision(decision_id, DIRECTOR, "I accept authorization, risk and rationale")
    return d


# ===========================================================================
# SCENE 6 — DECLARED LOW, GATED HIGH
# Proves: a lower class declared with no reversal path is gated as
# irreversible, and the record shows both classes.
# ===========================================================================

@pytest.mark.parametrize("declared", LOWER_CLASSES, ids=lambda c: c.name)
def test_lower_class_without_reversal_path_is_gated_as_irreversible(declared):
    """
    Spec: "Every execution-class decision is irreversible unless shown
    otherwise." "A decision without that support is gated as irreversible,
    whatever class was declared, and the record shows both the declared and
    the applied class."

    Setting the stage: "c1" closed by authority; the decision declared
    ROUTINE (or ELEVATED) with no reversal path, accepted.
    The action: request execution.
    The verdict: blocked with the irreversible-gate failures; the applied
    class is IRREVERSIBLE and the declared class is kept as declared.
    """
    # PLAYERS IN THIS SCENE
    #   sv       the Supervisor
    #   d        the Decision
    #   result   the GateResult
    sv = Supervisor()
    authority_world(sv)
    d = register(sv, declared)
    assert sv.effective_class("d1") is IRR
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert len(failures_with(result, CONSTRAINT_MSG)) == 1
    assert failures_with(result, RISK_MSG) == [RISK_MSG]
    assert result.execution_class is IRR
    assert result.declared_class is declared
    assert d.execution_class is declared


# ===========================================================================
# SCENE 7 — THE BLOCK IS WRITTEN DOWN WITH BOTH CLASSES
# Proves: the EXECUTION_BLOCKED audit payload records declared and applied.
# ===========================================================================

def test_blocked_audit_records_declared_and_applied_class():
    """
    Spec: "the record shows both the declared and the applied class."
    API: EXECUTION_BLOCKED payloads carry "declared_class" and
    "execution_class" (applied).
    """
    # PLAYERS IN THIS SCENE
    #   sv        the Supervisor
    #   blocked   the EXECUTION_BLOCKED entries
    sv = Supervisor()
    authority_world(sv)
    register(sv, ROUT)
    sv.request_execution("d1", DIRECTOR)
    blocked = entries(sv, "EXECUTION_BLOCKED")
    assert len(blocked) == 1
    assert as_value(blocked[0].payload["declared_class"]) == ROUT.value
    assert as_value(blocked[0].payload["execution_class"]) == IRR.value


# ===========================================================================
# SCENE 8 — AN OVERRIDE NAMES BOTH CLASSES TOO
# Proves: overriding the irreversible gate applied to a declared-routine
# decision logs both classes.
# ===========================================================================

def test_override_audit_records_declared_and_applied_class():
    """
    Spec: "the record shows both the declared and the applied class" and
    "Gates can be overridden. Every override is permanently logged".
    API: GATE_OVERRIDE payloads carry "declared_class" and "execution_class".
    """
    # PLAYERS IN THIS SCENE
    #   sv          the Supervisor
    #   result      the overridden GateResult
    #   overrides   the GATE_OVERRIDE entries
    sv = Supervisor()
    authority_world(sv)
    register(sv, ROUT)
    result = sv.request_execution("d1", "risk-officer", override_rationale="risk accepted")
    assert result.overridden
    assert result.execution_class is IRR
    assert result.declared_class is ROUT
    overrides = entries(sv, "GATE_OVERRIDE")
    assert len(overrides) == 1
    assert as_value(overrides[0].payload["declared_class"]) == ROUT.value
    assert as_value(overrides[0].payload["execution_class"]) == IRR.value


# ===========================================================================
# SCENE 9 — DECLARED IRREVERSIBLE STAYS IRREVERSIBLE
# Proves: a reversal path does not lower a decision declared irreversible.
# ===========================================================================

def test_declared_irreversible_with_tested_path_stays_irreversible():
    """
    Spec: a reversal path is what lets a decision "hold the elevated or
    routine class"; it does not change the declared class.
    API: effective_class is "the declared class if it is IRREVERSIBLE".
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 6
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv)
    register(sv, IRR, PATH, ["rev-ev"])
    assert sv.effective_class("d1") is IRR
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert result.execution_class is IRR
    assert result.declared_class is IRR


# ===========================================================================
# SCENE 10 — AN UNSUPPORTED ELEVATED DECISION
# Proves: an open constraint loop under a declared-elevated decision with
# no reversal path meets the irreversible gate, not the elevated one.
# ===========================================================================

def test_open_constraint_declared_elevated_without_path_is_blocked():
    """
    Spec: "A decision without that support is gated as irreversible,
    whatever class was declared".

    Setting the stage: "c1" still under review (open), decision declared
    ELEVATED with no reversal path. The elevated gate alone would pass it
    (the loop is classified, so it is documented). The verdict: blocked by
    the constraint requirement.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 6
    sv = Supervisor()
    to_review(sv, "c1")
    register(sv, ELEV)
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert len(failures_with(result, CONSTRAINT_MSG)) == 1
    assert result.execution_class is IRR


# ===========================================================================
# SCENE 11 — A TESTED WAY BACK
# Proves: a reversal path supported by EES lets the declared class apply.
# ===========================================================================

@pytest.mark.parametrize("declared", LOWER_CLASSES, ids=lambda c: c.name)
def test_tested_reversal_path_lets_declared_class_apply(declared):
    """
    Spec: "A decision may hold the elevated or routine class only if it has
    a registered reversal path ... supported by at least one External
    Evidence Source showing that the path has been tested".

    Setting the stage: the same authority-closed world as Scene 6, but the
    decision registers a reversal path backed by an independent lab's
    rehearsal record. The verdict: the declared class applies and the
    decision passes that gate; EXECUTION_PERMITTED records both classes.
    """
    # PLAYERS IN THIS SCENE
    #   sv          the Supervisor
    #   result      the GateResult
    #   permitted   the EXECUTION_PERMITTED entries
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv)
    register(sv, declared, PATH, ["rev-ev"])
    assert sv.effective_class("d1") is declared
    result = sv.request_execution("d1", DIRECTOR)
    assert result.permitted, result.failures
    assert not result.overridden
    assert result.execution_class is declared
    assert result.declared_class is declared
    permitted = entries(sv, "EXECUTION_PERMITTED")
    assert len(permitted) == 1
    assert as_value(permitted[0].payload["declared_class"]) == declared.value
    assert as_value(permitted[0].payload["execution_class"]) == declared.value


# ===========================================================================
# SCENE 12 — ANY ELIGIBLE KIND OF WITNESS
# Proves: each EES-eligible evidence kind can support the reversal path.
# ===========================================================================

@pytest.mark.parametrize("kind", ELIGIBLE_KINDS, ids=lambda k: k.name)
def test_each_eligible_kind_supports_reversal_path(kind):
    """
    Spec: the support is "evidence of an eligible kind produced by neither
    the agent who registered or reclassified the decision, nor the agent
    accepting it, nor a process under evaluation in its loops."
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv, kind=kind)
    register(sv, ROUT, PATH, ["rev-ev"])
    assert sv.effective_class("d1") is ROUT


# ===========================================================================
# SCENE 13 — A WAY BACK NOBODY TRIED
# Proves: a reversal path with no evidence counts as absent.
# ===========================================================================

def test_untested_reversal_path_counts_as_absent():
    """
    Spec: "An untested reversal path counts as absent, as an untested
    channel does under AP.2."
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 6
    sv = Supervisor()
    authority_world(sv)
    register(sv, ROUT, PATH)
    assert sv.effective_class("d1") is IRR
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert result.execution_class is IRR


# ===========================================================================
# SCENE 14 — A TEST OF NO PATH AT ALL
# Proves: reversal evidence with no registered reversal path does not count.
# ===========================================================================

def test_evidence_without_registered_path_does_not_count():
    """
    Spec: a decision may hold a lower class "only if it has a registered
    reversal path — the concrete means by which its effects can be undone —
    supported by" an EES. Evidence alone is not a registered path.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv)
    register(sv, ROUT, None, ["rev-ev"])
    assert sv.effective_class("d1") is IRR
    assert not sv.request_execution("d1", DIRECTOR).permitted


# ===========================================================================
# SCENE 15 — WITNESSES OF THE WRONG KIND
# Proves: model output, assertion and internal analysis do not test a path.
# ===========================================================================

@pytest.mark.parametrize("kind", INELIGIBLE_KINDS, ids=lambda k: k.name)
def test_ineligible_kind_does_not_support_reversal_path(kind):
    """
    Spec: the support must be "evidence of an eligible kind"; restated
    conclusions and additional passes by the same kind of process "do not
    constitute an External Evidence Source."

    The evidence is produced by INDEPENDENT_LAB, so only its kind can be the
    reason it fails.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv, kind=kind)
    register(sv, ROUT, PATH, ["rev-ev"])
    assert sv.effective_class("d1") is IRR
    assert not sv.request_execution("d1", DIRECTOR).permitted


# ===========================================================================
# SCENE 16 — THE REGISTRANT VOUCHES FOR THEIR OWN WAY BACK
# Proves: evidence produced by the registering agent does not count.
# ===========================================================================

def test_evidence_by_registering_agent_does_not_count():
    """
    Spec: "produced by neither the agent who registered or reclassified the
    decision, nor ..."
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv, producer=REGISTRAR)
    register(sv, ROUT, PATH, ["rev-ev"])
    assert sv.effective_class("d1") is IRR
    assert not sv.request_execution("d1", DIRECTOR).permitted


# ===========================================================================
# SCENE 17 — THE ACCEPTOR VOUCHES FOR THE WAY BACK
# Proves: evidence produced by the accepting agent does not count.
# ===========================================================================

def test_evidence_by_accepting_agent_does_not_count():
    """
    Spec: "produced by neither the agent who registered or reclassified the
    decision, nor the agent accepting it, nor ..."

    Checked after acceptance, when the accepting agent is known.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv, producer=DIRECTOR)
    register(sv, ROUT, PATH, ["rev-ev"])
    assert sv.effective_class("d1") is IRR
    assert not sv.request_execution("d1", DIRECTOR).permitted


# ===========================================================================
# SCENE 18 — THE PROCESS UNDER EVALUATION TESTS ITSELF
# Proves: evidence produced by a process under evaluation in the decision's
# loops does not count.
# ===========================================================================

def test_evidence_by_evaluated_process_does_not_count():
    """
    Spec: "... nor a process under evaluation in its loops."

    "c1" is about PROCESS (stagehands.to_review sets that).
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv, producer=PROCESS)
    register(sv, ROUT, PATH, ["rev-ev"])
    assert sv.effective_class("d1") is IRR


# ===========================================================================
# SCENE 19 — ANOTHER LOOP'S PROCESS
# Proves: the exclusion covers the evaluated process of every loop the
# decision rests on, not only the first.
# ===========================================================================

def test_evidence_by_another_loops_evaluated_process_does_not_count():
    """
    Spec: "... nor a process under evaluation in its loops." ("its loops":
    all of them).

    Setting the stage: "c1" (about PROCESS) and "c2" (about
    "second-process"), both authority-closed; the reversal evidence is
    produced by "second-process".
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    sv.register_signal("c2", SignalType.CONSTRAINT, "signal c2", "engineer", TECH,
                       "second-process", steward="steward", successor="successor")
    # --- Classify, review and close c2 the same way as c1 -------------------
    sv.classify("c2", OperationalState.ELEVATED_UNCERTAINTY, "engineer")
    sv.open_review("c2", "engineer")
    sv.attempt_closure("c2", REVIEWER, TECH, [], "I say it is fine")
    reversal_evidence(sv, producer="second-process")
    sv.register_decision("d1", "decision d1", ROUT, ["c1", "c2"], REGISTRAR,
                         reversal_path=PATH, reversal_evidence_ids=["rev-ev"])
    sv.accept_decision("d1", DIRECTOR, "accepted")
    assert sv.effective_class("d1") is IRR


# ===========================================================================
# SCENE 20 — THE RECLASSIFIER VOUCHES FOR THE WAY BACK
# Proves: evidence produced by the agent who lowers the class does not
# count, while the same evidence counts when someone else lowers it.
# ===========================================================================

def test_evidence_by_reclassifying_agent_does_not_count():
    """
    Spec: "produced by neither the agent who registered or reclassified the
    decision, ..." and "Lowering it needs the same reversal-path support as
    registering at the lower class".

    Two worlds: in each, REGISTRAR registers IRREVERSIBLE and the evidence is
    produced by RECLASSIFIER. In the first RECLASSIFIER lowers the class
    (evidence excluded); in the second REGISTRAR lowers it (evidence counts).
    """
    # PLAYERS IN THIS SCENE
    #   applied   effective class per lowering agent
    #   lowerer   the agent who lowers the class in each world
    #   sv        each world's Supervisor
    applied = {}
    for lowerer in (RECLASSIFIER, REGISTRAR):
        sv = Supervisor()
        authority_world(sv)
        register(sv, IRR)
        reversal_evidence(sv, producer=RECLASSIFIER)
        sv.reclassify_decision("d1", ROUT, lowerer, "rollback rehearsed",
                               reversal_path=PATH, reversal_evidence_ids=["rev-ev"])
        applied[lowerer] = sv.effective_class("d1")
    assert applied[RECLASSIFIER] is IRR
    assert applied[REGISTRAR] is ROUT


# ===========================================================================
# SCENE 21 — THE ORIGINAL REGISTRANT AFTER A RECLASSIFICATION
# Proves (literal reading): the registering agent stays excluded after
# someone else reclassifies.
# ===========================================================================

def test_registrant_still_excluded_after_another_agent_reclassifies():
    """
    Spec: "produced by neither the agent who registered or reclassified the
    decision". Read literally, both the registrant and the reclassifier are
    excluded; reclassification by a second agent does not clear the first.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    register(sv, IRR)
    reversal_evidence(sv, producer=REGISTRAR)
    sv.reclassify_decision("d1", ROUT, RECLASSIFIER, "rollback rehearsed",
                           reversal_path=PATH, reversal_evidence_ids=["rev-ev"])
    assert sv.effective_class("d1") is IRR


# ===========================================================================
# SCENE 22 — ONE GOOD WITNESS IS ENOUGH
# Proves: one qualifying item among non-qualifying ones supports the path.
# ===========================================================================

def test_one_qualifying_item_among_others_is_enough():
    """
    Spec: "supported by at least one External Evidence Source".
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv, "rev-model", kind=EvidenceKind.MODEL_OUTPUT)
    reversal_evidence(sv, "rev-self", producer=REGISTRAR)
    reversal_evidence(sv, "rev-lab")
    register(sv, ROUT, PATH, ["rev-model", "rev-self", "rev-lab"])
    assert sv.effective_class("d1") is ROUT
    assert sv.request_execution("d1", DIRECTOR).permitted


# ===========================================================================
# SCENE 23 — THE ANOMALY GETS NO EXEMPTION, AND NEEDS NONE
# Proves: a decision resting on an anomaly loop follows the same rule.
# ===========================================================================

@pytest.mark.parametrize("tested", [False, True], ids=["no-path", "tested-path"])
def test_anomaly_loop_follows_the_same_rule(tested):
    """
    Spec: "No separate rule is needed for decisions resting on constraint or
    anomaly loops: like every decision, they are irreversible until a tested
    reversal path is shown."

    Setting the stage: anomaly "c1" closed by authority; decision declared
    ROUTINE. Without a tested path: gated as irreversible (the anomaly
    fails the constraint/anomaly requirement). With one: the routine gate.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 6
    sv = Supervisor()
    authority_world(sv, SignalType.ANOMALY)
    if tested:
        reversal_evidence(sv)
        register(sv, ROUT, PATH, ["rev-ev"])
    else:
        register(sv, ROUT)
    result = sv.request_execution("d1", DIRECTOR)
    if tested:
        assert result.permitted, result.failures
        assert result.execution_class is ROUT
    else:
        assert not result.permitted
        assert len(failures_with(result, CONSTRAINT_MSG)) == 1
        assert result.execution_class is IRR


# ===========================================================================
# SCENE 24 — THE CONSTRAINT, LIKEWISE
# Proves: a constraint loop with a tested reversal path is not held to the
# irreversible gate merely for being a constraint.
# ===========================================================================

def test_constraint_loop_with_tested_path_gets_lower_gate():
    """
    Spec: "No separate rule is needed for decisions resting on constraint or
    anomaly loops". The same tested-path rule decides the class; the loop
    type does not.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 6
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv)
    register(sv, ELEV, PATH, ["rev-ev"])
    result = sv.request_execution("d1", DIRECTOR)
    assert result.permitted, result.failures
    assert failures_with(result, CONSTRAINT_MSG) == []


# ===========================================================================
# SCENE 25 — NO SILENT CHANGES
# Proves: reclassification without a rationale is refused, and nothing
# changes or is logged.
# ===========================================================================

def test_reclassification_requires_rationale():
    """
    Spec: "A decision's execution class can be changed, never silently:
    every change is logged with the agent, rationale, and any reversal
    evidence."
    API: reclassify_decision "Requires a non-empty rationale (else
    TransitionRefused)."
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    #   d    the Decision
    sv = Supervisor()
    authority_world(sv)
    d = register(sv, ROUT)
    with pytest.raises(TransitionRefused):
        sv.reclassify_decision("d1", IRR, RECLASSIFIER, "")
    assert d.execution_class is ROUT
    assert entries(sv, "DECISION_RECLASSIFIED") == []


# ===========================================================================
# SCENE 26 — TOO LATE TO RELABEL
# Proves: an executed decision cannot be reclassified.
# ===========================================================================

def test_executed_decision_cannot_be_reclassified():
    """
    API: reclassify_decision is "Refused for an executed decision." (The
    spec ties the class to the gate; once the gate has been passed and the
    decision executed, a new label could only rewrite the record.)
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    #   d    the Decision
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv)
    d = register(sv, ROUT, PATH, ["rev-ev"])
    assert sv.request_execution("d1", DIRECTOR).permitted
    with pytest.raises(TransitionRefused):
        sv.reclassify_decision("d1", IRR, RECLASSIFIER, "on reflection, irreversible")
    assert d.execution_class is ROUT
    assert entries(sv, "DECISION_RECLASSIFIED") == []


# ===========================================================================
# SCENE 27 — THE CHANGE IS WRITTEN DOWN
# Proves: a reclassification is logged with agent, rationale and evidence.
# ===========================================================================

def test_reclassification_is_logged_with_agent_rationale_and_evidence():
    """
    Spec: "every change is logged with the agent, rationale, and any
    reversal evidence."
    API: audit event "DECISION_RECLASSIFIED" with payload keys "decision",
    "from", "to", "rationale", "reversal_path", "evidence".
    """
    # PLAYERS IN THIS SCENE
    #   sv       the Supervisor
    #   logged   the DECISION_RECLASSIFIED entries
    #   p        the one entry's payload
    sv = Supervisor()
    authority_world(sv)
    register(sv, IRR)
    reversal_evidence(sv)
    sv.reclassify_decision("d1", ROUT, RECLASSIFIER, "rollback rehearsed by the lab",
                           reversal_path=PATH, reversal_evidence_ids=["rev-ev"])
    logged = entries(sv, "DECISION_RECLASSIFIED")
    assert len(logged) == 1
    assert logged[0].actor == RECLASSIFIER
    p = logged[0].payload
    assert RECLASS_KEYS <= set(p)
    assert p["decision"] == "d1"
    assert as_value(p["from"]) == IRR.value
    assert as_value(p["to"]) == ROUT.value
    assert p["rationale"] == "rollback rehearsed by the lab"
    assert p["reversal_path"] == PATH
    assert list(p["evidence"]) == ["rev-ev"]


# ===========================================================================
# SCENE 28 — RAISING THE CLASS IS FREE
# Proves: raising the class needs no evidence, and it is still logged.
# ===========================================================================

@pytest.mark.parametrize("start, raised", [(ROUT, ELEV), (ROUT, IRR), (ELEV, IRR)],
                         ids=["ROUTINE-to-ELEVATED", "ROUTINE-to-IRREVERSIBLE",
                              "ELEVATED-to-IRREVERSIBLE"])
def test_raising_class_needs_no_evidence(start, raised):
    """
    Spec: "Raising the class needs no evidence." "every change is logged".
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    #   d    the Decision
    sv = Supervisor()
    authority_world(sv)
    d = register(sv, start)
    sv.reclassify_decision("d1", raised, RECLASSIFIER, "more caution is warranted")
    assert d.execution_class is raised
    assert len(entries(sv, "DECISION_RECLASSIFIED")) == 1


# ===========================================================================
# SCENE 29 — RAISING TO IRREVERSIBLE APPLIES THE IRREVERSIBLE GATE
# Proves: once raised, a previously supported routine decision is gated
# as irreversible.
# ===========================================================================

def test_raised_to_irreversible_meets_irreversible_gate():
    """
    Spec: "Raising the class needs no evidence." The raised class then
    applies (API: effective class is the declared class if IRREVERSIBLE).
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 6
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv)
    register(sv, ROUT, PATH, ["rev-ev"])
    sv.reclassify_decision("d1", IRR, RECLASSIFIER, "more caution is warranted")
    assert sv.effective_class("d1") is IRR
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert result.execution_class is IRR


# ===========================================================================
# SCENE 30 — LOWERING WITHOUT A TESTED WAY BACK
# Proves: lowering without reversal support leaves the decision gated as
# irreversible.
# ===========================================================================

@pytest.mark.parametrize("lowered", LOWER_CLASSES, ids=lambda c: c.name)
def test_lowering_without_support_stays_irreversible(lowered):
    """
    Spec: "Lowering it needs the same reversal-path support as registering
    at the lower class" — and registering at the lower class without
    support is "gated as irreversible, whatever class was declared".

    The verdict: the declared class changes (the change is recorded), the
    applied class stays IRREVERSIBLE, and the request is blocked.
    """
    # PLAYERS IN THIS SCENE
    #   sv, d, result   as in Scene 6
    sv = Supervisor()
    authority_world(sv)
    d = register(sv, IRR)
    sv.reclassify_decision("d1", lowered, RECLASSIFIER, "it is really reversible")
    assert d.execution_class is lowered
    assert sv.effective_class("d1") is IRR
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert result.execution_class is IRR
    assert result.declared_class is lowered


# ===========================================================================
# SCENE 31 — LOWERING WITH A TESTED WAY BACK
# Proves: lowering with reversal support (and no prior block) lets the
# lower class apply.
# ===========================================================================

def test_lowering_with_support_applies_lower_class():
    """
    Spec: "Lowering it needs the same reversal-path support as registering
    at the lower class" — with that support, it holds the lower class.
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 6
    sv = Supervisor()
    authority_world(sv)
    register(sv, IRR)
    reversal_evidence(sv)
    sv.reclassify_decision("d1", ROUT, REGISTRAR, "rollback rehearsed",
                           reversal_path=PATH, reversal_evidence_ids=["rev-ev"])
    assert sv.effective_class("d1") is ROUT
    result = sv.request_execution("d1", DIRECTOR)
    assert result.permitted, result.failures
    assert result.execution_class is ROUT


# ===========================================================================
# SCENE 32 — WHAT IS KEPT, WHAT IS REPLACED, WHAT IS REFUSED
# Proves: an omitted reversal path is kept, a given one replaces the old,
# and unknown evidence ids are refused with nothing changed.
# ===========================================================================

def test_reclassify_keeps_replaces_and_refuses_reversal_support():
    """
    API: "A given reversal_path / reversal_evidence_ids replaces the stored
    ones; if omitted, the stored ones are kept." "Unknown evidence ids
    refused."
    Spec: changes are "never silent" — a refused change leaves no trace of
    having happened.

    Setting the stage: routine with tested support; raise to IRREVERSIBLE
    (support omitted, so kept); lower back to ROUTINE (still omitted: the
    kept support applies). Then try to move to ELEVATED citing an unknown
    id: refused, nothing changed. Then replace the evidence with model
    output: the path is no longer tested.
    """
    # PLAYERS IN THIS SCENE
    #   sv     the Supervisor
    #   d      the Decision
    #   count  DECISION_RECLASSIFIED entries before the refused call
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv)
    d = register(sv, ROUT, PATH, ["rev-ev"])
    # --- Raise, then lower again: the stored support is kept ----------------
    sv.reclassify_decision("d1", IRR, RECLASSIFIER, "pausing to check")
    sv.reclassify_decision("d1", ROUT, REGISTRAR, "check done, rollback still rehearsed")
    assert sv.effective_class("d1") is ROUT
    # --- Unknown evidence id: refused, nothing changes ----------------------
    count = len(entries(sv, "DECISION_RECLASSIFIED"))
    with pytest.raises(TransitionRefused):
        sv.reclassify_decision("d1", ELEV, REGISTRAR, "new evidence",
                               reversal_evidence_ids=["no-such-evidence"])
    assert d.execution_class is ROUT
    assert len(entries(sv, "DECISION_RECLASSIFIED")) == count
    assert sv.effective_class("d1") is ROUT
    # --- Replacing the evidence with model output: no longer tested ---------
    reversal_evidence(sv, "rev-model", kind=EvidenceKind.MODEL_OUTPUT)
    sv.reclassify_decision("d1", ROUT, REGISTRAR, "updated rehearsal record",
                           reversal_evidence_ids=["rev-model"])
    assert sv.effective_class("d1") is IRR


# ===========================================================================
# SCENE 33 — RELABELED BECAUSE THE GATE SAID NO
# Proves: lowering after a blocked request opens a structural review with
# the new condition, scoped to the decision.
# ===========================================================================

def blocked_then_lowered(sv):
    """
    Build a decision whose irreversible request was blocked, then lower it.

    Enter:   sv   the Supervisor
    Exit:    None. "c1" is evidence-closed (sound_world), so the irreversible
             gate's loop and EES requirements are met. d1 is registered
             IRREVERSIBLE and NOT accepted, so its first request is blocked
             (Rule 4). REGISTRAR then lowers it to ROUTINE with a valid,
             lab-tested reversal path. Finally DIRECTOR accepts it, so
             nothing but the review can block it afterwards.
    """
    # PLAYERS IN THIS SCENE
    #   first   the blocked GateResult
    sound_world(sv)
    register(sv, IRR, accept=False)
    first = sv.request_execution("d1", DIRECTOR)
    assert not first.permitted and failures_with(first, RULE4_MSG)
    reversal_evidence(sv)
    sv.reclassify_decision("d1", ROUT, REGISTRAR, "rollback rehearsed",
                           reversal_path=PATH, reversal_evidence_ids=["rev-ev"])
    sv.accept_decision("d1", DIRECTOR, "I accept authorization, risk and rationale")


def test_lowering_after_block_opens_structural_review():
    """
    Spec: "a lowering made after an execution request for the same decision
    was blocked escalates to structural review automatically". Escalation
    Conditions: "Execution class downgraded after an execution request for
    the same decision was blocked".
    API: condition EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK, scope
    "decision:<decision_id>".
    """
    # PLAYERS IN THIS SCENE
    #   sv     the Supervisor
    #   revs   reviews scoped to d1
    sv = Supervisor()
    blocked_then_lowered(sv)
    revs = decision_reviews(sv, "d1")
    assert len(revs) == 1
    assert revs[0].condition is EscalationCondition.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK
    assert EscalationCondition.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK.value == DOWNGRADE_VALUE
    assert not revs[0].resolved


# ===========================================================================
# SCENE 34 — NO CLASS WILL DO UNTIL THE REVIEW IS DONE
# Proves: while the review is unresolved, the decision cannot execute at
# the lower class (despite valid support) nor at the irreversible class
# (despite meeting that gate).
# ===========================================================================

def test_unresolved_downgrade_review_blocks_execution_at_any_class():
    """
    Spec: "Until that review is resolved, the decision cannot execute at any
    class."
    API: the failure string starts with "unresolved structural reviews".

    The action: request at ROUTINE; then raise back to IRREVERSIBLE (its
    loop and EES requirements are met in sound_world) and request again.
    The verdict: both blocked, and in each case the review is the only
    reason given. (The runtime checks an unresolved downgrade review right
    after Rule 4 and returns at once, so this asserts that early return;
    it does not by itself show sound_world meeting the irreversible gate.
    Scene 35 shows the decision executing once the review is resolved.)
    """
    # PLAYERS IN THIS SCENE
    #   sv        the Supervisor
    #   low       the GateResult at the lowered class
    #   high      the GateResult after raising back to IRREVERSIBLE
    sv = Supervisor()
    blocked_then_lowered(sv)
    low = sv.request_execution("d1", DIRECTOR)
    assert not low.permitted
    assert failures_with(low, REVIEW_MSG)
    sv.reclassify_decision("d1", IRR, REGISTRAR, "back to the full gate")
    high = sv.request_execution("d1", DIRECTOR)
    assert not high.permitted
    assert failures_with(high, REVIEW_MSG)
    assert len(low.failures) == 1 and len(high.failures) == 1


# ===========================================================================
# SCENE 35 — THE REVIEW CONCLUDES
# Proves: once the review is resolved, the decision executes at the lower
# class.
# ===========================================================================

def test_after_review_resolved_decision_executes_at_lower_class():
    """
    Spec: "Until that review is resolved, the decision cannot execute at any
    class" — and so, once it is resolved, the ordinary class rules apply.
    """
    # PLAYERS IN THIS SCENE
    #   sv       the Supervisor
    #   rev      the downgrade review
    #   result   the GateResult after resolution
    sv = Supervisor()
    blocked_then_lowered(sv)
    assert not sv.request_execution("d1", DIRECTOR).permitted
    (rev,) = decision_reviews(sv, "d1")
    sv.resolve_review(rev.review_id, BOARD,
                      "downgrade justified: rollback independently rehearsed",
                      elements_changed=["gate parameter: reversal-test evidence required"])
    assert rev.resolved
    result = sv.request_execution("d1", DIRECTOR)
    assert result.permitted, result.failures
    assert result.execution_class is ROUT
    assert result.declared_class is ROUT


# ===========================================================================
# SCENE 36 — LOWERED AFTER A BLOCK, EVEN WITHOUT SUPPORT
# Proves: the escalation does not depend on whether the lowering is
# supported.
# ===========================================================================

def test_unsupported_lowering_after_block_also_escalates():
    """
    Spec: "a lowering made after an execution request for the same decision
    was blocked escalates to structural review automatically". The sentence
    has no condition on the lowering's support, so an unsupported lowering
    escalates too.
    """
    # PLAYERS IN THIS SCENE
    #   sv     the Supervisor
    #   revs   reviews scoped to d1
    sv = Supervisor()
    authority_world(sv)
    register(sv, IRR)
    assert not sv.request_execution("d1", DIRECTOR).permitted
    sv.reclassify_decision("d1", ELEV, RECLASSIFIER, "it is only elevated really")
    revs = decision_reviews(sv, "d1")
    assert len(revs) == 1
    assert revs[0].condition is EscalationCondition.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK


# ===========================================================================
# SCENE 37 — LOWERINGS THAT DO NOT ESCALATE
# Proves: lowering with no prior blocked request, or after a block on a
# decision that is NOT linked to it, opens no review.
# ===========================================================================

@pytest.mark.parametrize("other_blocked", [False, True], ids=["no-block",
                                                              "unlinked-decision-blocked"])
def test_lowering_without_prior_block_on_linked_decision_does_not_escalate(other_blocked):
    """
    Spec: the escalation applies to "a lowering made after an execution
    request for the same decision was blocked", or after "any linked
    decision was blocked"; "two decisions are linked when they name a
    failure mode in common and share a signal".

    Setting the stage: optionally, a decision "d0" over a DIFFERENT loop
    "c0" (no shared signal, so not linked) is blocked first. Then d1,
    never requested, is lowered with valid support. The verdict: no review
    for d1, no review with the new condition, and d1 executes at ROUTINE.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    if other_blocked:
        to_review(sv, "c0")
        sv.register_decision("d0", "decision d0", IRR, ["c0"], REGISTRAR)
        sv.accept_decision("d0", DIRECTOR, "accepted")
        assert not sv.request_execution("d0", DIRECTOR).permitted
    register(sv, IRR)
    reversal_evidence(sv)
    sv.reclassify_decision("d1", ROUT, REGISTRAR, "rollback rehearsed",
                           reversal_path=PATH, reversal_evidence_ids=["rev-ev"])
    assert decision_reviews(sv, "d1") == []
    assert [r for r in sv.reviews if as_value(r.condition) == DOWNGRADE_VALUE] == []
    assert sv.request_execution("d1", DIRECTOR).permitted


# ===========================================================================
# SCENE 37b — A LINKED DECISION WAS BLOCKED
# Proves: "a lowering made after any linked decision was blocked escalates
# the same way" (Execution Class Assignment).
# ===========================================================================

def test_lowering_after_a_linked_decision_was_blocked_escalates():
    """
    Setting the stage: d0 over loop "c1" is blocked. d1, over the same loop
    (same signal, same failure mode: linked), is registered irreversible.
    The action: d1 is lowered to ROUTINE with valid support. The verdict:
    a downgrade-after-block review on d1 that names d0, and d1 cannot
    execute at any class until it is resolved.
    """
    # PLAYERS IN THIS SCENE
    #   sv     the Supervisor
    #   revs   reviews scoped to d1
    sv = Supervisor()
    authority_world(sv)
    register(sv, IRR, decision_id="d0")
    assert not sv.request_execution("d0", DIRECTOR).permitted
    register(sv, IRR)
    reversal_evidence(sv)
    sv.reclassify_decision("d1", ROUT, REGISTRAR, "rollback rehearsed",
                           reversal_path=PATH, reversal_evidence_ids=["rev-ev"])
    revs = decision_reviews(sv, "d1")
    assert len(revs) == 1 and as_value(revs[0].condition) == DOWNGRADE_VALUE
    assert "d0" in revs[0].detail
    assert failures_with(sv.request_execution("d1", DIRECTOR), REVIEW_MSG)


# ===========================================================================
# SCENE 37c — THE SAME COMMITMENT UNDER A NEW NAME
# Proves: "registering the same commitment under a new decision identifier
# does not avoid it" (Execution Class Assignment). IMPLEMENTATION DECISION:
# a new decision linked to a blocked one and registered at a lower class
# escalates at once.
# ===========================================================================

def test_registering_a_linked_decision_at_a_lower_class_escalates():
    """
    Setting the stage: d0 over "c1", irreversible, is blocked. The action:
    the same commitment is registered as d1 at ROUTINE with a tested
    reversal path. The verdict: d1 has a downgrade-after-block review and
    is held at every class; an unlinked decision registered the same way
    is not.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    register(sv, IRR, decision_id="d0")
    assert not sv.request_execution("d0", DIRECTOR).permitted
    reversal_evidence(sv)
    register(sv, ROUT, path=PATH, evidence=["rev-ev"])
    revs = decision_reviews(sv, "d1")
    assert len(revs) == 1 and as_value(revs[0].condition) == DOWNGRADE_VALUE
    assert failures_with(sv.request_execution("d1", DIRECTOR), REVIEW_MSG)
    # --- An unlinked decision at the same class: no review -----------------
    to_review(sv, "c9")
    sv.register_decision("d9", "unrelated", ROUT, ["c9"], REGISTRAR, reversal_path=PATH,
                         reversal_evidence_ids=["rev-ev"])
    assert decision_reviews(sv, "d9") == []


# ===========================================================================
# SCENE 38 — RAISING AFTER A BLOCK
# Proves: raising the class after a blocked request does not escalate.
# ===========================================================================

def test_raising_after_block_does_not_escalate():
    """
    Spec: only "a lowering made after an execution request for the same
    decision was blocked escalates"; "Raising the class needs no evidence."

    Setting the stage: declared ROUTINE with no path, blocked (gated as
    irreversible). Then raised to IRREVERSIBLE.
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    register(sv, ROUT)
    assert not sv.request_execution("d1", DIRECTOR).permitted
    sv.reclassify_decision("d1", IRR, RECLASSIFIER, "admit it is irreversible")
    assert decision_reviews(sv, "d1") == []
    assert [r for r in sv.reviews if as_value(r.condition) == DOWNGRADE_VALUE] == []


# ===========================================================================
# SCENE 39 — THE SIGNATURE IS STILL NEEDED; THE UNKNOWN WITNESS IS NOT
# Proves: Rule 4 acceptance is required at the lower classes, and unknown
# reversal evidence ids are refused at registration with nothing stored.
# ===========================================================================

@pytest.mark.parametrize("declared", LOWER_CLASSES, ids=lambda c: c.name)
def test_rule4_acceptance_still_required_at_lower_class(declared):
    """
    API: "Rule 4 acceptance (Supervisor.accept_decision) is still required
    at every class." (The changelog: "No other rule, construct, or claim is
    changed.")
    """
    # PLAYERS IN THIS SCENE
    #   sv, result   as in Scene 6
    sv = Supervisor()
    authority_world(sv)
    reversal_evidence(sv)
    register(sv, declared, PATH, ["rev-ev"], accept=False)
    assert sv.effective_class("d1") is declared
    result = sv.request_execution("d1", DIRECTOR)
    assert not result.permitted
    assert failures_with(result, RULE4_MSG)
    assert result.execution_class is declared


def test_unknown_reversal_evidence_id_refused_and_nothing_registered():
    """
    API: register_decision "Unknown ids are refused (TransitionRefused) and
    nothing is registered."

    The verdict: refused; no DECISION_REGISTERED entry; the same decision id
    can then be registered cleanly (it was never stored).
    """
    # PLAYERS IN THIS SCENE
    #   sv   the Supervisor
    sv = Supervisor()
    authority_world(sv)
    with pytest.raises(TransitionRefused):
        register(sv, ROUT, PATH, ["no-such-evidence"], accept=False)
    assert entries(sv, "DECISION_REGISTERED") == []
    reversal_evidence(sv)
    register(sv, ROUT, PATH, ["rev-ev"])
    assert len(entries(sv, "DECISION_REGISTERED")) == 1
    assert sv.effective_class("d1") is ROUT


# EXEUNT — end of file.

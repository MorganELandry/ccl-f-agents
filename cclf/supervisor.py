"""
THE SUPERVISOR
A Play in Nine Acts
===================

PROLOGUE
--------
The coordination supervisor: CCL-F v0.2 Layer 4 as a running monitor.

The v0.2 spec (Layer 4 — Runtime Realization, opening paragraph) describes the
runtime as "a commitment state machine, a coherence scoring model, execution
gates, and an immutable audit trail". This file is the piece that holds all
four together. The Supervisor class owns the signals, evidence, decisions,
structural reviews and registered architecture, and it is the only thing
that changes their state. Every operation:
  1. is checked against the commitment state machine (statemachine.py),
  2. is typed by deterministic rules (closure type, classification,
     escalation conditions, execution gates) with no model involved,
  3. is written to the hash-chained audit trail (audit.py) with the acting
     agent's identity.

Models (probabilistic automation) may only *propose* through advisor.py;
their proposals pass through the same rules as anyone else's, and model
output never counts as evidence (EES; spec Layer 2, External Evidence
Source, "What does not qualify": "multiple LLM instances ... do not
constitute independent evidence").

Where this file sits: types.py defines the vocabulary (signals, states,
closure types, ...), statemachine.py says which state moves are legal,
audit.py keeps the tamper-evident log, and this file applies the spec's
rules on top of those three. graph.py and advisor.py call into it.

SPEC VERSUS IMPLEMENTATION
    Every rule enforced here is labelled with the spec section it comes
    from. Where the spec leaves something open, the code had to choose; those
    choices are called out in comments as "IMPLEMENTATION DECISION", either
    with one of the project's labels D1-D9 (the code cites docs/DECISIONS.md
    for these) or, for choices without a D-label, in plain words. An
    implementation decision is this project's reading, not a claim the spec
    makes.

THE PLAYBILL (what happens in this file)
    ACT I — SETTINGS AND RECORDS
        Scene 1   TransitionRefused        the error every refused operation raises
        Scene 2   Settings                 the tunable thresholds (D1, D3-D6), the
                                           stabilization window, the threshold rationale
        Scene 3   StructuralReview         one automatic escalation (Rules 7-8)
        Scene 4   GateResult               the outcome of an execution request
        Scene 5   Supervisor.__init__      the supervisor's own records; logs SETTINGS
        Scene 6   _tick                    advance the logical clock
        Scene 7   _log                     write one audit entry
        Scene 8   _require_actor           no anonymous operations
        Scene 9   _decision                look up a decision or refuse
        Scene 10  _signal                  look up a signal or refuse
        Scene 11  _move, _mark_first_review
                                           the only door through the state machine;
                                           any entry into review starts the clock
    ACT II — EVIDENCE, ARCHITECTURE AND AGENTS
        Scene 1   is_novel                 Evidence Novelty (Layer 2)
        Scene 2   is_ees                   External Evidence Source (Layer 2): one
                                           definition, judged against the claimant
        Scene 2b  _qualifying, _closure_sound, _signal_sound, _supersession_shown,
                  _loop_resolved, chain_sound
                                           Closure Chain: every cited item resolved
                                           all the way up?
        Scene 3   register_architecture    record the Layer 0 facts
        Scene 4   add_evidence             record one item of evidence
        Scene 4b  add_dependency           a dependency found later (LATE_DEPENDENCY)
        Scene 5   register_agent, obligation_capable
                                           Agent Admissibility (Layer 0)
        Scene 6   register_reporting_line, in_reporting_line
                                           who reports to whom (Overrides)
    ACT III — THE SIGNAL LIFECYCLE: ENTRANCE, CLASSIFICATION, REVIEW
        Scene 1   register_signal          unregistered -> registered
        Scene 2   classify                 Rule 2: classification precedes action
        Scene 3   open_review              classified -> under_review
    ACT IV — CLOSURE TYPING
        Scene 1   attempt_closure          type a closure by its features
        Scene 2   _apply_closure           record it (or only attempt it)
        Scene 3   adopt_frame              framing signal: authority closure + suppression
    ACT V — THE SIGNAL LIFECYCLE CONTINUED: SUPPRESSION, REOPENING, EXITS
        Scene 1   suppress                 under_review -> suppressed
        Scene 2   reenter_suppressed       suppressed -> under_review, with rationale
        Scene 3   reopen                   closed -> under_review, never silently
        Scene 4   exit                     any open state -> exited(type)
        Scene 5   reenter                  exited -> under_review, by exit type
    ACT VI — ESCALATION AND STRUCTURAL REVIEW
        Scene 1   _escalate                open (or join) a structural review
        Scene 2   _apply_pending_escalations  escalate a signal on arrival in review
        Scene 3   _check_recurrence        Rule 7: recurrence group threshold; Rule 8
                                           Effect (UPDATE_INEFFECTIVE)
        Scene 4   _check_authority_count   authority closures on irreversible decisions
        Scene 5   _review_decisions, _acceptors, _independence_failures,
                  _resolution_conflicts, resolve_review
                                           each trigger resolved by what it requires,
                                           by an independent agent (re-checked later)
    ACT VII — SOURCE STANDING (AP.7, CREDIBILITY DISCOUNTING, AP-G)
        Scene 1   record_signal_outcome, _counted_outcomes
                                           scored outcomes, and which ones count
        Scene 2   accuracy_stable_or_improving  the accuracy test (D7)
        Scene 3   discount_supported_by_record  is a discount earned by the record?
        Scene 4   record_credibility_discount   detect shooting the messenger
    ACT VIII — DECISIONS, COHERENCE AND EXECUTION GATES
        Scene 1   register_decision        create a decision node
        Scene 1b  _check_evidence_ids, _reversal_supported, _applied_class,
                  effective_class, reclassify_decision, _check_lowering,
                  _check_below_blocked, _linked, _blocked_linked
                                           Execution Class Assignment; relabeling
                                           after refusal, however it happens
        Scene 2   link_signal              attach a signal to a decision
        Scene 2b  holds, grant, revoke,    who may recommend, authorize, execute;
                  recommend                chains of grants, revocation, expiry
        Scene 3   accept_decision          Rule 4: a single named accepting agent,
                                           the risk claim, the Rule 3 registration
        Scene 3b  _attester_failures, attest_risk_evidence, _attestation_failures
                                           the independent attestation of the risk
                                           evidence
        Scene 4   _decision_signals        the decision's known signals
        Scene 5   _lowerings, _classification_stable
                                           D8: no lowering of caution since review
        Scene 6   coherence                the Layer 4 coherence score (D3)
        Scene 7   architecture_check, unverified_preconditions
                                           the Layer 0 voids a runtime can see (D9),
                                           and the AP.2-AP.8 it cannot check
        Scene 7b  _gate_resolved, _other_loop_closed, _unresolved_at_gate,
                  _decision_ees, _nominal_unvalidated
                                           the irreversible gate's loop and evidence
                                           tests
        Scene 7c  _latch                   the POST-EXECUTION LATCH (executed_open);
                                           external exits annotated, not moved
        Scene 8   request_execution        the execution gates and overrides
        Scene 9   _emergency_execution     the Emergency Justification
    ACT IX — READ-ONLY VIEWS
        Scene 1   open_reviews             unresolved structural reviews
        Scene 2   summary                  counts for dashboards and reports

READER'S NOTE — "logical clock"
    The supervisor keeps an integer `clock` that goes up by one for each
    operation (_tick). It is not wall-clock time; it only orders events.
    Evidence novelty and classification stability are both judged against
    it, and every audit entry carries it.

READER'S NOTE — how a refusal works
    A rule violation raises TransitionRefused (a custom exception, ACT I,
    Scene 1). The caller can catch it. Most operations check their inputs
    before changing anything, but some tick the clock or write an audit
    entry (for example TRANSITION_REFUSED) before refusing; the scenes say
    where.

READER'S NOTE — Optional and Iterable (from the typing module)
    Optional[str] means "a str or None". Iterable[str] means "anything you
    can loop over that yields str": a list, a tuple, a set, a generator.
    These are type hints only; Python does not enforce them at run time.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# __future__.annotations  makes every type hint a lazy string, so hints like
#                         dict[str, Signal] work on older Python versions and
#                         can name classes defined later.
# dataclasses             dataclasses.replace() copies a frozen record with
#                         one field changed (add_dependency, ACT II, Scene 4b).
# time                    the default wall clock for grant expiry.
# dataclass, field        build simple record classes (see ACT I READER'S
#                         NOTEs on dataclasses and field(default_factory)).
# Callable, Iterable,     type hints (see the READER'S NOTE above).
#   Optional
# AuditTrail              the append-only, hash-chained log (audit.py).
# check_transition        is current -> target in the v0.2 transition table?
# exit_allowed            may a signal in this state exit?
# reentry_allowed         may an exited signal of this exit type re-enter?
# types                   the v0.2 vocabulary. Three are given short aliases:
#                         S = CommitmentState (lifecycle position),
#                         E = EscalationCondition (the Layer 2 triggers),
#                         O = OperationalState (the five Rule 2 states).
#                         EES_ELIGIBLE_KINDS lists the evidence kinds that can
#                         be an External Evidence Source; CLOSED_STATES is the
#                         set of the three closed commitment states;
#                         CLOSING_EXITS is the exit type (superseded) that
#                         closes a loop of the other types at the
#                         irreversible gate (ACT VIII, Scene 7b);
#                         EXTERNAL_EXITS (whistleblower, legal) are the
#                         exits the latch annotates instead of moving;
#                         OBLIGATION_KINDS is the agent kinds that can hold
#                         an obligation (Agent Admissibility).
# ===========================================================================

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from .audit import AuditTrail
from .statemachine import check_transition, exit_allowed, reentry_allowed
from .types import (
    AgentKind, Architecture, ClassificationRecord, ClosureRecord, ClosureType,
    CommitmentState as S, Decision, EES_ELIGIBLE_KINDS, EmergencyConsequence,
    EmergencyJustification, EscalationCondition as E, Evidence, ExecutionClass,
    ExitRecord, ExitType, Grant, LegalSubtype, OBLIGATION_KINDS, OpenLoopAuthorization,
    OperationalState as O, OutcomeRecord, Power, Referent, RiskAttestation, Signal,
    SignalType, CLOSED_STATES, CLOSING_EXITS, EXTERNAL_EXITS,
)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# The five DEFAULT_ thresholds below are labelled implementation decisions
# (D1 and D3-D6, see docs/DECISIONS.md). Since October 2026 the spec states
# three of them itself (Layer 2, Escalation Conditions, "Thresholds"): "a
# recurrence group crosses its threshold at its third occurrence (Rule 7);
# the authority-closure count on an irreversible decision escalates once it
# exceeds one; AP-G is reached at the third unsupported discount". D1, D5
# and D6 follow those defaults; the coherence threshold (D3) and the minimum
# evidence closure ratio (D4) remain this project's values. They are only
# the defaults: the Settings dataclass (ACT I, Scene 2) copies them, and a
# caller can pass different values per Supervisor (raising one of the three
# spec-stated defaults needs a logged rationale). The variables after them
# are fixed lookup tables and texts taken from the spec.
# ===========================================================================

# DEFAULT_RECURRENCE_THRESHOLD — how many signals in one recurrence group
#   trigger the Rule 7 structural review (ACT VI, Scene 3).
#   Spec: Rule 7 ("What to do"): "When a recurrence group crosses the
#   escalation threshold — at its third occurrence, unless the domain
#   registers another count (see Escalation Conditions, Thresholds) —
#   structural review is mandatory and automatic".
#   D1: 3, the spec's stated default.
DEFAULT_RECURRENCE_THRESHOLD = 3        # D1: "at its third occurrence"

# DEFAULT_AUTHORITY_CLOSURE_THRESHOLD — the escalation condition "Authority
#   closure count exceeds threshold on an irreversible decision" (Layer 2,
#   Escalation Conditions) needs a number. Spec ("Thresholds"): "the
#   authority-closure count on an irreversible decision escalates once it
#   exceeds one".
#   D5: 1, so the second authority closure on an irreversible decision's
#   signals escalates (the test is "count > 1").
DEFAULT_AUTHORITY_CLOSURE_THRESHOLD = 1  # D5: escalate when count exceeds this

# DEFAULT_SENDER_DISCOUNT_THRESHOLD — how many unsupported credibility
#   discounts against one agent (discounts not earned by a poor or
#   declining accuracy record) turn into AP-G, the Sender Discount void.
#   Spec (Layer 2, Credibility Discounting, "AP-G threshold"): "The
#   default threshold is three: AP-G is reached at the third credibility-discounting
#   event against the same registering agent during which that agent's
#   signals show a stable or improving accuracy rate."
#   D6: 3, the spec's own number (and the same number as D1).
DEFAULT_SENDER_DISCOUNT_THRESHOLD = 3   # D6: "The default threshold is three"

# DEFAULT_COHERENCE_THRESHOLD — the coherence score below which an
#   irreversible execution is blocked. Spec (Layer 4, Coherence Score):
#   "A score below the domain-configured threshold blocks irreversible
#   execution pending acknowledgment."
#   IMPLEMENTATION DECISION D3: default 0.6.
DEFAULT_COHERENCE_THRESHOLD = 0.6       # D3: "domain-configured threshold"

# DEFAULT_MIN_EVIDENCE_CLOSURE_RATIO — the share of the real closures of a
#   decision's uncertainty, dissent, classification and framing signals that
#   must be chain-sound evidence closures before an irreversible execution.
#   Spec (Layer 4, Execution Gates) requires a "minimum evidence closure
#   ratio" for those loop types but gives no value.
#   IMPLEMENTATION DECISION D4: 0.5.
DEFAULT_MIN_EVIDENCE_CLOSURE_RATIO = 0.5  # D4: "minimum evidence closure ratio"

# COHERENCE_WEIGHTS — factor name -> weight for the coherence score
#   (ACT VIII, Scene 6). The five factors and their weights are copied from
#   the spec's table (Layer 4, Coherence Score), which calls
#   them "provisional and illustrative". The weights add up to 1.0, so a
#   score built from factors in [0, 1] also lies in [0, 1]. How each factor
#   is computed is not in the spec (IMPLEMENTATION DECISION D3).
COHERENCE_WEIGHTS = {                   # Layer 4, Coherence Score (provisional)
    "open_loops": 0.30,
    "classification_stability": 0.25,
    "closure_quality": 0.20,
    "recurrence_pressure": 0.15,
    "authority_compression": 0.10,
}

# CLASS_RANK — execution class -> its height, so "lowering" can be tested
#   with <. Layer 4, Execution Class Assignment: lowest to highest, routine,
#   elevated, irreversible.
CLASS_RANK = {ExecutionClass.ROUTINE: 0, ExecutionClass.ELEVATED: 1,
              ExecutionClass.IRREVERSIBLE: 2}

# EXIT_TYPES_REQUIRING_OPEN_STATE_NOTE — the exit types that must record the
#   open loop state at the time of exit. Spec (Layer 2, Loop Exit Taxonomy,
#   "Exit obligations"): "Terminal, legal, and key person exits
#   require explicit notation of the open loop state at the time of exit."
#   Used by exit() (ACT V, Scene 4).
#   A frozenset is a set that cannot be changed after it is built; that
#   suits a fixed rule list, and checking "x in frozenset" is fast.
EXIT_TYPES_REQUIRING_OPEN_STATE_NOTE = frozenset({
    ExitType.TERMINAL, ExitType.LEGAL, ExitType.KEY_PERSON})

# LOWERINGS — new operational state -> the earlier states from which moving
#   to it is a reclassification "toward a less cautious state". Spec (Layer
#   4, Execution Gates, "Classification stabilized"): "to nominal from any
#   other state, or to elevated uncertainty from off-envelope, experimental,
#   or containment". Every other change (toward greater caution, or between
#   off-envelope, experimental and containment) does not destabilize, and
#   neither does re-confirming the same state. Read by _lowerings() (ACT
#   VIII, Scene 5).
LOWERINGS = {
    O.NOMINAL: frozenset({O.ELEVATED_UNCERTAINTY, O.OFF_ENVELOPE, O.EXPERIMENTAL,
                          O.CONTAINMENT}),
    O.ELEVATED_UNCERTAINTY: frozenset({O.OFF_ENVELOPE, O.EXPERIMENTAL, O.CONTAINMENT}),
}

# SPEC_THRESHOLD_DEFAULTS — Settings field -> the default the spec states
#   for it (Layer 2, Escalation Conditions, "Thresholds"). "Raising a
#   threshold above its default needs its rationale logged, since a
#   threshold raised to avoid escalation is itself a compression event
#   (Ambiguity Debt)." Settings.__post_init__ (ACT I, Scene 2) refuses a
#   raised value without Settings.threshold_rationale.
SPEC_THRESHOLD_DEFAULTS = {
    "recurrence_threshold": DEFAULT_RECURRENCE_THRESHOLD,
    "authority_closure_threshold": DEFAULT_AUTHORITY_CLOSURE_THRESHOLD,
    "sender_discount_threshold": DEFAULT_SENDER_DISCOUNT_THRESHOLD,
}

# EMERGENCY_RECURRENCE_COUNT — the Emergency Justification that counts as
#   recurrence on one failure mode. Spec (Layer 4, Overrides): "the third on
#   the same failure mode since its last structural review is treated as
#   recurrence, whatever threshold the domain sets for ordinary recurrence,
#   and opens a review no Emergency Justification can suspend." Fixed, so it
#   is not a Settings field.
EMERGENCY_RECURRENCE_COUNT = 3

# RULE8_ONLY_CONDITIONS — the escalation conditions whose reviews are
#   resolved only by a Rule 8 update. Spec (Layer 4, Overrides): "A review
#   opened by a count crossing its threshold — recurrence (Rule 7),
#   authority closures, AP-G — or by relabeling after refusal is resolved
#   only by a Rule 8 update. A review opened by any other condition is
#   resolved by that update, or by a documented finding from the
#   independent reviewer, with rationale, that the event was handled on its
#   own record and no model element requires change." Off-envelope,
#   containment and the post-event review have their own standards.
RULE8_ONLY_CONDITIONS = frozenset({
    E.RECURRENCE_THRESHOLD, E.AUTHORITY_CLOSURE_COUNT, E.SENDER_DISCOUNT_RECURRENCE,
    E.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK})

# SUSPENDABLE_CONDITIONS — the reviews an Emergency Justification may
#   suspend: "Only off-envelope and containment holds admit an Emergency
#   Justification" (Escalation Conditions), and "The post-event review holds
#   later irreversible decisions on the same loops as an off-envelope review
#   does, and a further Emergency Justification may suspend it" (Overrides).
SUSPENDABLE_CONDITIONS = frozenset({E.OFF_ENVELOPE_OR_CONTAINMENT, E.EMERGENCY_POST_EVENT})

# RUNTIME_UNCHECKABLE — the Layer 0 sub-conditions this runtime has no check
#   for from registered facts (D9): channel legibility, boundary
#   agreements, scope adequacy and void recognizability. Each is reported in
#   the gate record as unverified: "each of AP.2-AP.8 either passes its
#   registered check or is reported in the gate record as unverified"
#   (Layer 4, Execution Gates, "Architecture Precondition met").
RUNTIME_UNCHECKABLE = ("AP.3", "AP.4", "AP.5", "AP.8")

# NO_QUALIFYING_AGENT — the sentence every refusal for want of an
#   independent, admissible agent ends with. Spec (Layer 4, Execution
#   Gates, Overrides): "Where no agent meets these conditions, the decision
#   does not execute irreversibly, except under the on-scene proviso of an
#   Emergency Justification. The absence is recorded as a
#   stewardship void (AP-A) for the failure modes concerned, and the remedy
#   is an external reviewer registered by the domain's principals."
NO_QUALIFYING_AGENT = ("if no agent meets these conditions, the decision does not execute "
                       "irreversibly: that absence is a stewardship void (AP-A) for the "
                       "failure modes concerned, and the remedy is an external reviewer "
                       "registered by the domain's principals")


# ###########################################################################
# ACT I — SETTINGS AND RECORDS
# The cast's paperwork: the error type, the thresholds, the record shapes,
# and the supervisor's own bookkeeping helpers.
# ###########################################################################

# ===========================================================================
# ACT I, SCENE 1 — THE REFUSAL
# What is raised when an operation would break a v0.2 rule?
# ===========================================================================

class TransitionRefused(Exception):
    """
    A requested operation broke a v0.2 rule.

    No signal, evidence, decision or review was changed by the refused
    step. Depending on where the refusal happens, the logical clock may
    already have ticked, an audit entry (TRANSITION_REFUSED or
    REENTRY_REFUSED) may already have been written, and a refused real
    closure has already used up a closure record number (ACT IV, Scene 2).

    READER'S NOTE — custom exceptions
        A class that inherits from Exception is a new kind of error. It
        needs no body: the docstring is enough. Raising it
        (`raise TransitionRefused("why")`) stops the operation, and callers
        can catch exactly this kind of error with
        `except TransitionRefused:` without also catching unrelated bugs.
    """


# ===========================================================================
# ACT I, SCENE 2 — THE HOUSE RULES
# Which thresholds does this supervisor use?
# ===========================================================================

@dataclass(frozen=True)
class Settings:
    """
    The tunable thresholds, one Supervisor at a time. Frozen: a threshold
    cannot be raised after construction, past the rationale check and the
    SETTINGS log entry (a raised threshold "needs its rationale logged").

    Each default comes from the DRAMATIS PERSONAE above (labelled
    implementation decisions D1, D3-D6; the spec states the defaults for
    the recurrence, authority-closure and AP-G thresholds, which D1, D5 and
    D6 follow).

    READER'S NOTE — dataclasses
        @dataclass writes the boring parts of a class for you. From the
        annotated class attributes below it generates an __init__ (so
        Settings(recurrence_threshold=5) works), a readable __repr__ and an
        __eq__. Each `name: type = default` line becomes one constructor
        argument with that default.
    """
    recurrence_threshold: int = DEFAULT_RECURRENCE_THRESHOLD
    authority_closure_threshold: int = DEFAULT_AUTHORITY_CLOSURE_THRESHOLD
    sender_discount_threshold: int = DEFAULT_SENDER_DISCOUNT_THRESHOLD
    coherence_threshold: float = DEFAULT_COHERENCE_THRESHOLD
    min_evidence_closure_ratio: float = DEFAULT_MIN_EVIDENCE_CLOSURE_RATIO
    # authority_roots: agents who hold every Power over every scope and may
    #   delegate it (the principals: an organization's officers, the user an
    #   assistant acts for). Empty means authority is not enforced, as
    #   before. Set, every recommendation, acceptance and execution request
    #   must rest on a root or on a chain of grants from one
    #   (IMPLEMENTATION DECISION; see ACT VIII, Scene 2b).
    authority_roots: frozenset = frozenset()
    # stabilization_window: None (the default) judges "classification
    #   stabilized" over each signal's whole history since its first review
    #   opened. A number of clock ticks instead judges only the lowerings
    #   made within that many ticks before the execution request: "A domain
    #   may register a stabilization window instead, in which case the test
    #   covers that window before the execution request" (Layer 4, Execution
    #   Gates). See _classification_stable (ACT VIII, Scene 5).
    stabilization_window: Optional[int] = None
    # threshold_rationale: why a threshold was raised above the spec's
    #   default. Required (non-blank) when any of the three thresholds in
    #   SPEC_THRESHOLD_DEFAULTS is set above its default; the Supervisor logs
    #   it with the settings when it is created.
    threshold_rationale: str = ""

    def __post_init__(self) -> None:
        """
        Refuse a raised threshold that gives no rationale.

        Enter:   (the fields just set by the generated __init__)
        Exit:    None; raises ValueError naming each raised threshold when
                 threshold_rationale is blank

        Spec (Layer 2, Escalation Conditions, "Thresholds"): "A domain may
        set a lower count where a single repetition is already intolerable.
        Raising a threshold above its default needs its rationale logged".
        Lowering needs nothing. ValueError (not TransitionRefused) because
        no supervisor exists yet: this is a bad configuration, not a
        refused operation.

        READER'S NOTE — __post_init__
            A dataclass's generated __init__ calls __post_init__ (if the
            class defines one) right after it has set every field, so it is
            the place for checks that involve the field values. A frozen
            dataclass can still be read here; only assignment is refused
            (dataclasses.FrozenInstanceError).
        """
        # PLAYERS IN THIS SCENE
        #   raised   names of thresholds set above the spec's default

        raised = [name for name, default in SPEC_THRESHOLD_DEFAULTS.items()
                  if getattr(self, name) > default]
        if raised and not self.threshold_rationale.strip():
            raise ValueError(f"thresholds raised above the spec's default need a logged "
                             f"rationale (Settings.threshold_rationale): {raised}")


# ===========================================================================
# ACT I, SCENE 3 — THE STRUCTURAL REVIEW
# What does one automatic escalation look like?
# ===========================================================================

@dataclass
class StructuralReview:
    """
    An automatic escalation to structural review (Layer 2).

    Spec: Layer 2, Escalation Conditions: "The following conditions
    automatically escalate to structural review". Rule 7 fires the review;
    Rule 8 ("Why it matters") says what it must produce: "a documented
    update to the coordination model — not a re-approval of existing
    practice". "The review is resolved by what its trigger requires —
    evidence-based reclassification to nominal or elevated uncertainty for
    off-envelope, independent steward review for containment, a documented
    Rule 8 update for a threshold count or relabeling after refusal, and
    for every other condition either that update or an independent finding
    that no model element requires change" (Escalation Conditions).
    resolve_review() (ACT VI, Scene 5) records what resolved it in the
    fields below.

    Fields:
        review_id     "R1", "R2", ... in order of opening
        condition     which escalation condition fired
        scope         what the review is about: a signal id, "group:<id>",
                      "agent:<id>", "decision:<id>" or "emergency:<failure
                      mode>"
        detail        human-readable description of why it fired
        opened_at     the logical clock when it opened
        signal_ids    the signals it holds in `escalated` (may be empty)
        resolved_by   the agent who resolved it, or None while open
        model_update  the Rule 8 coordination model update ("" while open,
                      and for reviews resolved by a finding instead)
        trigger       for OFF_ENVELOPE_OR_CONTAINMENT: which of the two
                      operational states opened it (they are resolved
                      differently); None for every other condition
        elements_changed  the registered elements of the coordination model
                      the Rule 8 update names as changed
        level         for a recurrence review: the level at which the
                      recurring instances are generated (Rule 8, "Scope")
        finding       the written finding that resolved an off-envelope,
                      containment or post-event review
        reviewing_steward  for a containment review: the independent
                      steward who reviewed it
        elements_held for a post-event review: whether every element of
                      the Emergency Justification held, per the finding
        suspended_by  ids of the Emergency Justifications that suspended
                      this review ("The justification suspends the holding
                      reviews; it does not resolve them")
        decision_id   for a post-event review: the decision that executed
                      under the justification
        resolved_at   the logical clock when it was (last) resolved
        no_model_change  True if resolved by an independent finding that no
                      model element requires change, not a Rule 8 update
        history       earlier resolutions replaced by a re-resolution (a
                      resolution found not independent at a gate; see
                      resolve_review), each as a dict of its fields

    READER'S NOTE — field(default_factory=list)
        A dataclass default like `signal_ids: list[str] = []` would be one
        single list shared by every StructuralReview ever made, so adding a
        signal to one review would add it to all of them. Python's
        dataclass refuses that. field(default_factory=list) instead calls
        list() afresh for each new object, so each review gets its own
        empty list.
    """
    review_id: str
    condition: E
    scope: str            # signal id, "group:<id>", "agent:<id>" or "decision:<id>"
    detail: str
    opened_at: int
    signal_ids: list[str] = field(default_factory=list)
    resolved_by: Optional[str] = None
    model_update: str = ""
    trigger: Optional[O] = None
    elements_changed: tuple[str, ...] = ()
    level: Optional[str] = None
    finding: str = ""
    reviewing_steward: Optional[str] = None
    elements_held: Optional[bool] = None
    suspended_by: list[str] = field(default_factory=list)
    decision_id: Optional[str] = None
    resolved_at: int = -1
    no_model_change: bool = False
    history: list[dict] = field(default_factory=list)

    @property
    def suspendable(self) -> bool:
        """
        Could an Emergency Justification suspend this review?

        Enter:   (nothing)
        Exit:    True for a review opened by an off-envelope or containment
                 classification, or an emergency post-event review

        Spec (Layer 2, Escalation Conditions): "Only off-envelope and
        containment holds admit an Emergency Justification"; (Layer 4,
        Overrides) "The post-event review holds later irreversible decisions
        on the same loops as an off-envelope review does, and a further
        Emergency Justification may suspend it." Every other review records
        "failures of the coordination process itself, not conditions of the
        world, and no emergency justifies proceeding past them".
        """
        return self.condition in SUSPENDABLE_CONDITIONS

    @property
    def resolved(self) -> bool:
        """
        Has this review been resolved?

        Enter:   (nothing)
        Exit:    True once resolve_review() has named who resolved it

        READER'S NOTE — @property
            @property lets a method be read like a plain attribute:
            `review.resolved`, with no parentheses. The value is worked out
            each time it is read, so it can never go stale.
        """
        return self.resolved_by is not None


# ===========================================================================
# ACT I, SCENE 4 — THE GATE RESULT
# What does an execution request report back?
# ===========================================================================

@dataclass
class GateResult:
    """
    Outcome of an execution request (ACT VIII, Scene 8).

    Fields:
        decision_id        the decision that asked to execute
        execution_class    irreversible, elevated or routine
        permitted          True if execution may go ahead (cleanly or by override)
        overridden         True if it went ahead only because of an override
        architecture_void  True if a Layer 0 void was found: the spec (Layer 0,
                           Why This Matters) calls the gates "structurally
                           void" in that case
        failures           every gate requirement that was not met
        coherence          the decision's coherence score at request time
        latched_signals    signals latched into executed_open by an
                           irreversible execution under an override or an
                           Emergency Justification (the POST-EXECUTION
                           LATCH; see request_execution)
        declared_class     the class the decision declares; execution_class
                           above is the class the gate APPLIED, which is
                           irreversible unless a tested reversal path
                           supports the declared one (Execution Class
                           Assignment)
        emergency_id       "EJ<n>" if it executed under an Emergency
                           Justification, else None
        annotated_signals  loops in an external exit (whistleblower, legal)
                           that the latch annotated with the authorization
                           instead of moving
        unverified         the Layer 0 sub-conditions (AP.2-AP.8) that have
                           no registered or runtime check for this decision:
                           reported, never blocking
    """
    decision_id: str
    execution_class: ExecutionClass
    permitted: bool
    overridden: bool
    architecture_void: bool
    failures: list[str]
    coherence: float
    latched_signals: list[str] = field(default_factory=list)
    declared_class: Optional[ExecutionClass] = None
    emergency_id: Optional[str] = None
    annotated_signals: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)


# ===========================================================================
# THE SUPERVISOR
# The leading role: one object that holds every record and applies every
# rule. Its methods are the scenes of ACTS I (from Scene 5) to IX.
# ===========================================================================

class Supervisor:
    """
    CCL-F v0.2 Layer 4 supervisor.

    Spec (Layer 4 — Runtime Realization, opening section): "its controller
    is the discrete-event supervisory automaton ... The commitment state
    machine is the supervisor's automaton — its blocked transitions are the
    supervisor's forbidden-event set, enforced structurally rather than by
    convention. Execution gates are the supervisor's interlock logic on
    irreversible actuation."

    Every public method that changes state takes the acting agent's
    identity (`by`, or `registered_by`), refuses with TransitionRefused when
    a rule is broken, and writes what it did to `self.audit`. The read-only
    queries (is_novel, is_ees, chain_sound, effective_class, coherence,
    architecture_check, accuracy_stable_or_improving,
    discount_supported_by_record, obligation_capable, in_reporting_line,
    open_reviews, summary) take no actor and write nothing. The one entry
    written without an actor's operation is SETTINGS, at construction.
    """

    # =======================================================================
    # ACT I, SCENE 5 — THE COMPANY ASSEMBLES
    # What does a new supervisor hold?
    # =======================================================================

    def __init__(self, settings: Optional[Settings] = None,
                 architecture: Optional[Architecture] = None,
                 now: Optional[Callable[[], float]] = None) -> None:
        """
        Create an empty supervisor.

        Enter:   settings       thresholds to use (default: Settings())
                 architecture   the registered Layer 0 architecture
                                (default: an empty Architecture())
                 now            the wall clock grant expiry is judged by,
                                in seconds since the epoch (default:
                                time.time; tests pass their own)
        Exit:    a Supervisor with no signals, evidence, decisions or
                 reviews; its first audit entry, SETTINGS, records every
                 threshold and the threshold rationale (Layer 2,
                 Escalation Conditions, "Thresholds": a raised threshold
                 "needs its rationale logged")

        Attributes it sets:
            settings              the thresholds in use
            architecture          the registered Layer 0 architecture
        Records it keeps (all start empty, or at 0):
            audit                 the append-only, hash-chained audit trail
            signals               signal id -> Signal
            evidence              evidence id -> Evidence
            decisions             decision id -> Decision
            reviews               every StructuralReview, open or resolved, in order
            reviewed_groups       recurrence groups whose Rule 7 review was resolved
            group_resolutions     recurrence group -> id of the review whose
                                  resolution last reviewed it (Rule 8, "Effect")
            outcomes              agent -> every OutcomeRecord of their signals (AP.7)
            agent_kinds           agent -> AgentKind, for agents registered with
                                  one (Agent Admissibility)
            role_successors       role -> its registered successor
            reports_to            agent -> the agents they report to directly
            emergencies           every Emergency Justification given, as
                                  (id, decision id, failure modes, giver,
                                  clock time)
            discounts             agent -> number of credibility discounts recorded
                                  (all of them, supported or not)
            unsupported_discounts agent -> number of discounts NOT supported by
                                  the agent's record; only these count toward
                                  AP-G (D6)
            sender_discount_void  agents now under AP-G (Sender Discount)
            grants                every Grant of a power, in order (ACT VIII,
                                  Scene 2b)
            revoked               grant id -> (revoking agent, clock time)
            clock                 the logical clock (see the module READER'S NOTE)
            _closure_seq          counter for closure record ids "C1", "C2", ...
        """
        # --- Settings and architecture, with defaults ----------------------
        # `x or Default()` uses x if it was given (and is truthy), otherwise
        # builds a fresh default. A fresh one each time matters: a default
        # argument written as `settings=Settings()` would be shared by every
        # Supervisor.
        self.settings = settings or Settings()
        self.architecture = architecture or Architecture()
        # --- The records ---------------------------------------------------
        self.audit = AuditTrail()
        self.signals: dict[str, Signal] = {}
        self.evidence: dict[str, Evidence] = {}
        self.decisions: dict[str, Decision] = {}
        self.grants: list[Grant] = []
        self.revoked: dict[str, tuple[str, int]] = {}
        self.now = now or time.time
        self.reviews: list[StructuralReview] = []
        self.reviewed_groups: set[str] = set()
        self.group_resolutions: dict[str, str] = {}    # group -> resolving review
        self.outcomes: dict[str, list[OutcomeRecord]] = {}  # agent -> scored outcomes
        self.agent_kinds: dict[str, AgentKind] = {}    # agent -> its kind
        self.role_successors: dict[str, str] = {}      # role -> successor
        self.reports_to: dict[str, set[str]] = {}      # agent -> direct superiors
        self.emergencies: list[tuple[str, str, tuple, str, int]] = []
        self.discounts: dict[str, int] = {}            # agent -> discount count
        self.unsupported_discounts: dict[str, int] = {}  # agent -> AP-G count
        self.sender_discount_void: set[str] = set()    # agents under AP-G
        self.clock = 0
        self._closure_seq = 0
        # --- Log the thresholds in force -----------------------------------
        # dataclasses.asdict() turns the Settings into a plain dict;
        # authority_roots is a frozenset, made a sorted list for the log.
        self._log("SETTINGS", "supervisor",
                  **{k: (sorted(v) if isinstance(v, frozenset) else v)
                     for k, v in dataclasses.asdict(self.settings).items()})

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    # =======================================================================
    # ACT I, SCENE 6 — THE CLOCK STRIKES
    # Advance the logical clock by one.
    # =======================================================================

    def _tick(self) -> int:
        """
        Advance the logical clock.

        Enter:   (nothing)
        Exit:    the new clock value (also stored in self.clock)
        """
        self.clock += 1
        return self.clock

    # =======================================================================
    # ACT I, SCENE 7 — THE SCRIBE
    # Write one entry to the audit trail.
    # =======================================================================

    def _log(self, event: str, actor: str, **payload) -> None:
        """
        Append one audit entry stamped with the current clock.

        Enter:   event      an upper-case event name, e.g. "TRANSITION"
                 actor      the agent responsible
                 **payload  any extra named details to store with it
        Exit:    None; the entry is appended to self.audit

        Spec: Layer 4, Audit Trail: "Every state transition is
        append-only and immutable ... The record cannot be revised after the
        fact — only extended." AuditTrail (audit.py) enforces that.

        READER'S NOTE — **payload
            `**payload` collects every extra keyword argument into a dict.
            So `self._log("X", "eng", signal="s1", reason="r")` arrives here
            with payload == {"signal": "s1", "reason": "r"}.
        """
        self.audit.append(self.clock, event, actor, payload)

    # =======================================================================
    # ACT I, SCENE 8 — NO ANONYMOUS ACTORS
    # Refuse any operation that does not name who is doing it.
    # =======================================================================

    @staticmethod
    def _require_actor(by: str) -> None:
        """
        Every operation is attributed; check before anything changes.

        Enter:   by   the acting agent's identity
        Exit:    None, or raises TransitionRefused if `by` is empty/blank

        Why: the spec's audit obligations (e.g. overrides "permanently logged
        with the agent's identity", Layer 4, Execution Gates; reopens logged
        with "the identity of the reopening agent", Layer 4, Commitment State
        Machine) mean nothing without an identity.

        READER'S NOTE — @staticmethod
            A static method does not receive `self`; it is a plain function
            that lives inside the class for tidiness. It is still called as
            self._require_actor(by).
        """
        # str(by).strip() removes surrounding spaces, so "   " is refused too.
        if not by or not str(by).strip():
            raise TransitionRefused("every operation needs an acting agent's identity")

    # =======================================================================
    # ACT I, SCENE 9 — CALLING A DECISION BY NAME
    # Look up a decision, or refuse if it does not exist.
    # =======================================================================

    def _decision(self, decision_id: str) -> Decision:
        """
        Fetch a registered decision.

        Enter:   decision_id   the decision's id
        Exit:    the Decision; raises TransitionRefused if unknown
        """
        # `{decision_id!r}` in an f-string inserts repr(decision_id), which
        # puts quotes around a string, so blanks and odd characters show up.
        if decision_id not in self.decisions:
            raise TransitionRefused(f"unknown decision {decision_id!r}")
        return self.decisions[decision_id]

    # =======================================================================
    # ACT I, SCENE 10 — CALLING A SIGNAL BY NAME
    # Look up a signal, or refuse if it does not exist.
    # =======================================================================

    def _signal(self, signal_id: str) -> Signal:
        """
        Fetch a registered signal.

        Enter:   signal_id   the signal's id
        Exit:    the Signal; raises TransitionRefused if unknown
        """
        if signal_id not in self.signals:
            raise TransitionRefused(f"unknown signal {signal_id!r}")
        return self.signals[signal_id]

    # =======================================================================
    # ACT I, SCENE 11 — THE ONLY DOOR
    # Move a signal to a new commitment state, if the state machine allows.
    # =======================================================================

    def _move(self, sig: Signal, target: S, actor: str, **payload) -> None:
        """
        Apply one commitment-state transition, checked and logged.

        Enter:   sig        the signal to move
                 target     the commitment state to move it to
                 actor      the agent responsible
                 **payload  extra details for the audit entry
        Exit:    None; sig.state is updated and a TRANSITION entry written.
                 If the move is not in the v0.2 table, a TRANSITION_REFUSED
                 entry is written and TransitionRefused is raised.

        Spec: Layer 4, Commitment State Machine: "certain
        transitions are blocked regardless of organizational pressure."
        check_transition() (statemachine.py) holds the table and the four
        named blocked transitions. Almost every state change in this file
        goes through here; the exceptions are exit() and reenter(), whose
        legality depends on the exit type (see ACT V, Scenes 4-5).
        """
        # PLAYERS IN THIS SCENE
        #   ok, reason   (allowed?, the rule text or the blocking reason)
        #   previous     the state the signal was in before the move

        # --- Ask the state machine -----------------------------------------
        # `ok, reason = f()` is tuple unpacking: f returns a pair and each
        # name receives one half.
        ok, reason = check_transition(sig.state, target)
        if not ok:
            # The refusal itself is audited, so a blocked attempt is visible.
            # `**{"from": ...}` is used because `from` is a Python keyword
            # and cannot be written as `from=...` in a call.
            self._log("TRANSITION_REFUSED", actor, signal=sig.signal_id,
                      **{"from": sig.state, "to": target, "reason": reason})
            raise TransitionRefused(reason)
        # --- Make the move and record it, with the rule that allowed it ----
        previous = sig.state
        sig.state = target
        self._mark_first_review(sig, target)
        self._log("TRANSITION", actor, signal=sig.signal_id,
                  **{"from": previous, "to": target, "rule": reason}, **payload)

    def _mark_first_review(self, sig: Signal, target: S) -> None:
        """
        Record the signal's first entry into review, by whatever route.

        Enter:   sig      the signal that has just moved
                 target   the state it moved to
        Exit:    None; sets sig.first_review_opened_at to the current clock
                 if the signal moved into under_review and the field is
                 still unset

        Spec (Layer 4, Execution Gates, "Classification stabilized"): the
        test covers lowerings "since its first review opened". A signal can
        first reach review through open_review(), reenter() after an exit
        taken from `classified`, a recovery, or a reopen; each must start
        the clock, or a lowering made while under review would never count.
        """
        if target == S.UNDER_REVIEW and sig.first_review_opened_at < 0:
            sig.first_review_opened_at = self.clock

    # ###########################################################################
    # ACT II — EVIDENCE, ARCHITECTURE AND AGENTS
    # The two evidence tests that closure typing relies on, the Closure
    # Chain, the operations that record evidence and the Layer 0
    # architecture, and who the agents are (kinds, reporting lines).
    # ###########################################################################

    # =======================================================================
    # ACT II, SCENE 1 — IS IT NEW?
    # Evidence Novelty: did this evidence arrive after the signal did?
    # =======================================================================

    def is_novel(self, ev: Evidence, sig: Signal) -> bool:
        """
        Evidence Novelty: not present when the signal was registered.

        Enter:   ev    the evidence
                 sig   the signal it is offered against
        Exit:    True if the evidence is new relative to the signal

        Spec: Layer 2, Evidence Novelty Requirement:
        "Evidence-based closure requires that the closing evidence was not
        present when the signal was registered. Restating existing analysis
        in more confident language does not constitute new evidence." Why:
        otherwise a loop could be "closed" by the very data that raised it.

        IMPLEMENTATION DECISION (novelty by the logical clock): "not present
        at registration" is checked mechanically. The evidence must not be
        among the ids attached at registration, and its clock stamp `at`
        must be later than the signal's `registered_at`. The runtime cannot
        tell whether new evidence merely restates old analysis in new words.
        """
        return ev.evidence_id not in sig.evidence_at_registration and ev.at > sig.registered_at

    # =======================================================================
    # ACT II, SCENE 2 — IS IT INDEPENDENT?
    # External Evidence Source: does this evidence come from outside?
    # =======================================================================

    def is_ees(self, ev: Evidence, sig: Optional[Signal], claimant: Optional[str],
               excluded: Iterable[str] = ()) -> bool:
        """
        External Evidence Source: an eligible kind of evidence, produced by
        neither the agent making the claim it is offered for, nor a process
        whose output the claim evaluates, nor anyone else the caller names
        (the agent accepting the decision it supports). Model output never
        qualifies.

        Enter:   ev         the evidence
                 sig        the signal the claim is about (its
                            evaluated_process is excluded), or None for a
                            claim that is not about one signal
                 claimant   the agent making the claim: the closing agent,
                            for a closure; the classifying agent, for a
                            classification; the exiting agent, for a
                            supersession
                 excluded   further producers that cannot count: the
                            accepting agent of the decision the claim
                            supports, other evaluated processes
        Exit:    True if the evidence counts as an External Evidence Source

        Spec: Layer 2, External Evidence Source (EES), "Definition": "A
        source is an External Evidence Source for a claim only if its errors
        cannot share a cause with the errors of the process making the
        claim ... Operationally, the evidence is of an eligible kind (see
        What qualifies, below), and its producer is none of the following:
        the agent making the claim it is offered for (the closing agent, for
        a closure; the registering or reclassifying agent, for a reversal
        path or a classification; the accepting agent, for a Rule 4
        acceptance); the agent accepting the decision it supports; or any
        process whose output the claim evaluates. ... This one definition is
        the one used wherever this document requires an External Evidence
        Source." The signal's registrant is NOT excluded as such: a
        measurement the registrant took can confirm a closure someone else
        makes ("A common cause in the world is not a shared error").

        IMPLEMENTATION DECISION (EES operationalized as evidence kind +
        producing process): the spec's test is about causal ancestry, which
        a runtime cannot see. Here it becomes two checks on recorded facts:
          1. the evidence's `kind` is in EES_ELIGIBLE_KINDS (primary
             document, direct measurement, formal verification, independent
             party; never model output, internal analysis or assertion), and
          2. the producer named in `produced_by` is not the claimant, not
             the signal's `evaluated_process`, and not in `excluded`.
        The result is only as good as the `kind` and `produced_by` that were
        recorded.
        """
        # PLAYERS IN THIS SCENE
        #   barred   every producer whose evidence cannot count here

        barred = set(excluded) | {claimant}
        if sig is not None:
            barred.add(sig.evaluated_process)
        return ev.kind in EES_ELIGIBLE_KINDS and ev.produced_by not in barred

    # =======================================================================
    # ACT II, SCENE 2b — IS IT SOUND ALL THE WAY UP?
    # Closure Chain: an evidence closure is only as good as the loops its
    # evidence depends on.
    # =======================================================================

    def _qualifying(self, rec: ClosureRecord, sig: Signal,
                    excluded: frozenset = frozenset()) -> list[Evidence]:
        """
        The cited evidence that makes a closure an evidence closure.

        Enter:   rec        a closure record on `sig`
                 sig        the signal it closed
                 excluded   further producers that cannot count (the
                            acceptor of the decision being judged)
        Exit:    the cited Evidence items that are novel and EES for the
                 closing agent's claim

        Recomputed from the record rather than stored: evidence is frozen
        and a signal's registration time never changes, so with nothing
        extra excluded the answer is the same as at closure time.
        """
        return [self.evidence[e] for e in rec.evidence_ids
                if e in self.evidence and self.is_novel(self.evidence[e], sig)
                and self.is_ees(self.evidence[e], sig, rec.closed_by, excluded)]

    def _closure_sound(self, rec: ClosureRecord, sig: Signal, seen: frozenset,
                       excluded: frozenset = frozenset()) -> bool:
        """
        Is this closure a chain-sound evidence closure?

        Enter:   rec        a closure record on `sig`
                 sig        the signal it closed
                 seen       signal ids already on the path being checked (to
                            catch cycles)
                 excluded   further producers that cannot count (see
                            _qualifying)
        Exit:    True only for a real (not attempted) evidence closure with
                 at least one qualifying item, every cited item of which
                 has every upstream loop resolved

        Spec: Layer 2, Closure Chain: "An evidence closure is chain-sound
        only if every item of evidence it cites has every upstream loop
        itself resolved — closed by chain-sound evidence closure, or exited
        as superseded with an External Evidence Source — all the way up.
        Citing an item is relying on it, so every cited item is
        load-bearing: a closure cannot pass by pairing one clean item with
        others that rest on unresolved loops. A loop cannot be its own
        upstream, directly or through others".

        `all(...)` over an empty list is True, so evidence with no
        upstream loops is sound on its own. Cited ids not on record carry
        no recorded dependency and are skipped.
        """
        # PLAYERS IN THIS SCENE
        #   path   `seen` plus this signal: what the upstream checks must avoid

        if rec.attempted_only or rec.closure_type != ClosureType.EVIDENCE:
            return False
        if not self._qualifying(rec, sig, excluded):
            return False
        path = seen | {sig.signal_id}
        return all(self._loop_resolved(up, path, excluded)
                   for e in rec.evidence_ids if e in self.evidence
                   for up in self.evidence[e].depends_on)

    def _signal_sound(self, signal_id: str, seen: frozenset,
                      excluded: frozenset = frozenset()) -> bool:
        """
        Is this signal currently closed by a chain-sound evidence closure?

        Enter:   signal_id   the signal to check
                 seen        signal ids already on the path (cycle guard)
                 excluded    further producers that cannot count
        Exit:    False if the signal is on the path already (a cycle), is
                 unknown, or is not in closed_evidence; otherwise whether its
                 latest real closure is chain-sound
        """
        # PLAYERS IN THIS SCENE
        #   sig      the signal
        #   latest   its most recent real (not attempted) closure record

        if signal_id in seen or signal_id not in self.signals:
            return False
        sig = self.signals[signal_id]
        if sig.state != S.CLOSED_EVIDENCE:
            return False
        latest = next(c for c in reversed(sig.closures) if not c.attempted_only)
        return self._closure_sound(latest, sig, seen, excluded)

    def _supersession_shown(self, sig: Signal, excluded: frozenset = frozenset()) -> bool:
        """
        Has this signal exited as superseded, with an External Evidence
        Source showing the context that generated it no longer exists?

        Enter:   sig        the signal
                 excluded   further producers that cannot count
        Exit:    True for an exited(superseded) signal whose exit cites at
                 least one item that is EES for the exiting agent's claim

        Spec: Layer 4, Execution Gates, "Constraint and anomaly loops
        evidence-closed": "or has exited as superseded with an External
        Evidence Source showing that the context that generated it no
        longer exists."

        IMPLEMENTATION DECISION: the spec asks for an EES here, not for
        Evidence Novelty or a chain test on the exit's own evidence, so
        neither is applied.
        """
        if sig.state != S.EXITED or sig.exit is None:
            return False
        if sig.exit.exit_type != ExitType.SUPERSEDED:
            return False
        return any(self.is_ees(self.evidence[e], sig, sig.exit.by, excluded)
                   for e in sig.exit.evidence_ids if e in self.evidence)

    def _loop_resolved(self, signal_id: str, seen: frozenset,
                       excluded: frozenset = frozenset()) -> bool:
        """
        Is this loop resolved, in the one sense the Closure Chain and the
        irreversible gate share?

        Enter:   signal_id   the loop
                 seen        signal ids already on the path (cycle guard)
                 excluded    further producers that cannot count
        Exit:    True if it is closed by a chain-sound evidence closure, or
                 exited as superseded with an External Evidence Source; False
                 for an unknown id or a loop already on the path

        Spec: Layer 2, Closure Chain ("closed by chain-sound evidence
        closure, or exited as superseded with an External Evidence Source")
        and Reversibility Logic ("Of the exits, only a supersession resolves
        a loop: for a constraint or anomaly loop, one shown by an External
        Evidence Source").
        """
        if signal_id in seen or signal_id not in self.signals:
            return False
        if self._supersession_shown(self.signals[signal_id], excluded):
            return True
        return self._signal_sound(signal_id, seen, excluded)

    def chain_sound(self, signal_id: str) -> bool:
        """
        Public check: is this signal closed by a chain-sound evidence closure?

        Enter:   signal_id   a registered signal
        Exit:    True or False; raises TransitionRefused for an unknown id

        Assessed now, not at closure time ("Chain soundness is assessed at
        the time it is needed, not fixed at closure").
        """
        self._signal(signal_id)
        return self._signal_sound(signal_id, frozenset())

    # ------------------------------------------------------------------
    # Architecture and evidence
    # ------------------------------------------------------------------

    # =======================================================================
    # ACT II, SCENE 3 — THE ARCHITECTURE IS SET
    # Record the Layer 0 coordination architecture.
    # =======================================================================

    def register_architecture(self, architecture: Architecture, by: str) -> None:
        """
        Replace the registered Layer 0 architecture.

        Enter:   architecture   stewards, successors, tested channels,
                                reporters and interested parties per
                                failure mode (see types.Architecture)
                 by             the registering agent
        Exit:    None; self.architecture is replaced and the full content
                 is logged as ARCHITECTURE_REGISTERED

        Spec: Layer 0, the Architecture Precondition. These
        are the facts architecture_check() (ACT VIII, Scene 7) reads.
        """
        self._require_actor(by)
        self._tick()
        self.architecture = architecture
        # --- Log the whole architecture ------------------------------------
        # `{k: sorted(v) for k, v in d.items()}` is a dict comprehension: it
        # builds a new dict with the same keys and each set turned into a
        # sorted list, so the audit entry is stable and readable.
        self._log("ARCHITECTURE_REGISTERED", by,
                  stewards=architecture.stewards, successors=architecture.successors,
                  channels_tested=architecture.channels_tested,
                  reporters={k: sorted(v) for k, v in architecture.reporters.items()},
                  interested_parties={k: sorted(v) for k, v in
                                      architecture.interested_parties.items()})

    # =======================================================================
    # ACT II, SCENE 4 — EXHIBIT A
    # Record one item of evidence and attach it to signals.
    # =======================================================================

    def add_evidence(self, evidence_id: str, content: str, source: str, kind,
                     produced_by: str, by: str, signal_ids: Iterable[str] = (),
                     depends_on: Iterable[str] = ()) -> Evidence:
        """
        Register one item of evidence, stamped with the current clock.

        Enter:   evidence_id   unique id for the evidence
                 content       what it says (stored, never interpreted)
                 source        where it came from (free text)
                 kind          an EvidenceKind (used by the EES test)
                 produced_by   the process that produced it (used by the EES test)
                 by            the registering agent
                 signal_ids    signals to attach it to (default: none)
                 depends_on    signals this evidence depends on: its
                               upstream loops (Layer 2, Closure Chain)
        Exit:    the new Evidence; raises TransitionRefused if the id is
                 already used or any signal id (in either list) is unknown,
                 and then stores nothing

        The clock stamp is what is_novel() later compares with a signal's
        registration time. "Dependencies are registered by the agent who
        adds the evidence; the chain can only be as complete as that
        registration." A dependency cycle is accepted here and simply never
        counts (see _closure_sound).
        """
        # PLAYERS IN THIS SCENE
        #   at    the clock value stamped on the evidence
        #   ev    the new Evidence record
        #   sid   each signal id the evidence is attached to

        self._require_actor(by)
        # --- Validate everything before changing anything --------------------
        # list() makes a one-time iterator (such as a generator) safe to use
        # twice; looking every signal up first means an unknown id refuses
        # the whole operation instead of leaving the evidence half-attached.
        signal_ids = list(signal_ids)
        depends_on = tuple(depends_on)
        if evidence_id in self.evidence:
            raise TransitionRefused(f"evidence {evidence_id!r} already registered")
        for sid in signal_ids + list(depends_on):
            self._signal(sid)
        at = self._tick()
        # --- Create and store the record -----------------------------------
        ev = Evidence(evidence_id, content, source, kind, produced_by, at, depends_on)
        self.evidence[evidence_id] = ev
        # --- Attach to each named signal -----------------------------------
        for sid in signal_ids:
            self._signal(sid).evidence_ids.append(evidence_id)
        self._log("EVIDENCE_ADDED", by, evidence=evidence_id, kind=kind,
                  produced_by=produced_by, source=source, signals=list(signal_ids),
                  depends_on=list(depends_on))
        return ev

    # =======================================================================
    # ACT II, SCENE 4b — A DEPENDENCY FOUND LATER
    # Add an upstream loop to evidence already on record.
    # =======================================================================

    def add_dependency(self, evidence_id: str, signal_id: str, by: str) -> Evidence:
        """
        Register that an item of evidence depends on one more upstream loop.

        Enter:   evidence_id   evidence already on record
                 signal_id     the upstream loop (a registered signal)
                 by            the registering agent
        Exit:    the updated Evidence (a new frozen copy replaces the old one
                 in self.evidence). Logs DEPENDENCY_ADDED; if any real
                 closure already cites the item, also logs LATE_DEPENDENCY
                 naming those closures, and CHAIN_WEAKENED for each signal
                 whose closure was chain-sound before and is not after.
                 Refuses an unknown evidence or signal id; adding a
                 dependency already recorded changes nothing but the log.

        Spec: Layer 2, Closure Chain: "Dependencies are registered by the
        agent who adds the evidence; the chain can only be as complete as
        that registration. A dependency registered after the closure it
        affects, because it was discovered later, is logged as late, and the
        closure loses its standing from that point". Soundness is always
        recomputed when needed, so the loss of standing needs no stored
        flag: the next check simply sees the new upstream loop.

        IMPLEMENTATION DECISION: `by` need not be the agent who added the
        evidence. The spec says who registers dependencies in the ordinary
        course; a dependency discovered later may be found by anyone, and
        refusing it would keep a known weakness out of the record.
        """
        # PLAYERS IN THIS SCENE
        #   old            the evidence record before the change
        #   citing         ids of real closures that already cite it
        #   sound_before   signals chain-sound before the change
        #   ev             the new record
        #   sid            each signal rechecked after the change

        self._require_actor(by)
        if evidence_id not in self.evidence:
            raise TransitionRefused(f"unknown evidence {evidence_id!r}")
        self._signal(signal_id)
        self._tick()
        old = self.evidence[evidence_id]
        citing = sorted(c.record_id for s in self.signals.values() for c in s.closures
                        if not c.attempted_only and evidence_id in c.evidence_ids)
        sound_before = {sid for sid in self.signals if self._signal_sound(sid, frozenset())}
        # --- Store a new copy with the longer depends_on --------------------
        # dataclasses.replace(obj, field=value) returns a NEW object equal to
        # obj except for the named field; the frozen original is untouched.
        if signal_id not in old.depends_on:
            ev = dataclasses.replace(old, depends_on=old.depends_on + (signal_id,))
            self.evidence[evidence_id] = ev
        else:
            ev = old
        self._log("DEPENDENCY_ADDED", by, evidence=evidence_id, upstream=signal_id,
                  depends_on=list(ev.depends_on))
        # --- Late: a closure already rests on this item --------------------
        if citing:
            self._log("LATE_DEPENDENCY", by, evidence=evidence_id, upstream=signal_id,
                      closures=citing)
        for sid in sorted(sound_before):
            if not self._signal_sound(sid, frozenset()):
                self._log("CHAIN_WEAKENED", by, signal=sid, upstream=signal_id,
                          evidence=evidence_id)
        return ev

    # =======================================================================
    # ACT II, SCENE 5 — WHO OR WHAT IS THIS AGENT?
    # Agent Admissibility: register an agent's kind.
    # =======================================================================

    def register_agent(self, agent: str, agent_kind: AgentKind, by: str,
                       successor: Optional[str] = None) -> None:
        """
        Record what kind of agent `agent` is.

        Enter:   agent        the agent's identity
                 agent_kind   an AgentKind (person, unit, role, automation,
                              instrument)
                 by           the registering agent
                 successor    for a role: the agent registered to take over
                              the obligation when the occupant changes
        Exit:    None; logs AGENT_REGISTERED. A later registration replaces
                 an earlier one (both stay in the log).

        Spec: Layer 0, Agent Admissibility: "Persons and organizational
        units have obligation capacity. A role has it when a successor is
        registered under AP.1b, so that the obligation survives a change of
        occupant." Instruments, models and monitors have identity
        persistence and "cannot accept an obligation". obligation_capable()
        (Scene 5b) reads what this records.
        """
        self._require_actor(by)
        self._require_actor(agent)
        agent_kind = AgentKind(agent_kind)
        self._tick()
        self.agent_kinds[agent] = agent_kind
        if successor:
            self.role_successors[agent] = successor
        else:
            self.role_successors.pop(agent, None)
        self._log("AGENT_REGISTERED", by, agent=agent, agent_kind=agent_kind,
                  successor=successor,
                  obligation_capacity=self.obligation_capable(agent))

    def obligation_capable(self, agent: Optional[str],
                           successor: Optional[str] = None) -> bool:
        """
        Does this agent have obligation capacity?

        Enter:   agent       the agent (None counts as not capable)
                 successor   when the question is whether the agent can
                             steward a failure mode: that mode's registered
                             AP.1b successor, through which a role also has
                             capacity
        Exit:    True for a person or unit; for a role, True only with a
                 registered successor who is another agent; False for
                 automation and instruments. An agent never registered with
                 a kind is treated as capable (IMPLEMENTATION DECISION:
                 registries written before kinds existed keep working; the
                 kind is a claim someone must register to take capacity
                 away, and the registration is logged).

        Spec: Layer 0, Agent Admissibility, "Admissibility criterion":
        "Stewardship (AP.1) requires obligation capacity. So do Rule 4
        acceptance and open-loop authorization, which are stewardship acts."
        """
        # PLAYERS IN THIS SCENE
        #   kind        the registered AgentKind, or None
        #   successor   a role's successor: its own, else the failure mode's

        if not agent:
            return False
        kind = self.agent_kinds.get(agent)
        if kind is None:
            return True
        if kind not in OBLIGATION_KINDS:
            return False
        if kind != AgentKind.ROLE:
            return True
        successor = self.role_successors.get(agent) or successor
        return bool(successor) and successor != agent

    # =======================================================================
    # ACT II, SCENE 6 — WHO REPORTS TO WHOM?
    # Register a reporting line, so independence can be checked.
    # =======================================================================

    def register_reporting_line(self, agent: str, reports_to: str, by: str) -> None:
        """
        Record that `agent` reports to `reports_to`.

        Enter:   agent        the subordinate
                 reports_to   the agent they report to directly
                 by           the registering agent
        Exit:    None; logs REPORTING_LINE_REGISTERED. Refuses an agent
                 reporting to itself.

        Spec: Layer 4, Execution Gates, Overrides: "Where reporting lines
        are registered, the overrider sits outside the accepting agent's:
        an agent who reports to the acceptor, directly or through others,
        repeats the acceptor's judgment under another name." The same test
        applies to whoever resolves a structural review holding the
        decision, and to the agent giving an Emergency Justification.
        """
        self._require_actor(by)
        self._require_actor(agent)
        self._require_actor(reports_to)
        if agent == reports_to:
            raise TransitionRefused(f"{agent} cannot report to itself")
        self._tick()
        self.reports_to.setdefault(agent, set()).add(reports_to)
        self._log("REPORTING_LINE_REGISTERED", by, agent=agent, reports_to=reports_to)

    def in_reporting_line(self, agent: Optional[str], superior: Optional[str]) -> bool:
        """
        Does `agent` report to `superior`, directly or through others?

        Enter:   agent, superior   two agents (None never reports)
        Exit:    True if a chain of registered reporting lines leads from
                 agent up to superior

        A breadth-first walk up the registered lines; `seen` stops a loop
        of lines (A reports to B, B to A) from walking forever.
        """
        # PLAYERS IN THIS SCENE
        #   frontier   agents still to walk up from
        #   seen       agents already visited
        #   a, up      the agent being expanded, and each of its superiors

        if not agent or not superior:
            return False
        frontier, seen = [agent], {agent}
        while frontier:
            a = frontier.pop()
            for up in self.reports_to.get(a, ()):
                if up == superior:
                    return True
                if up not in seen:
                    seen.add(up)
                    frontier.append(up)
        return False

    # ###########################################################################
    # ACT III — THE SIGNAL LIFECYCLE: ENTRANCE, CLASSIFICATION, REVIEW
    # A signal enters, is classified (Rule 2), and has review opened on it.
    # ###########################################################################

    # ------------------------------------------------------------------
    # Signal lifecycle
    # ------------------------------------------------------------------

    # =======================================================================
    # ACT III, SCENE 1 — A SIGNAL ENTERS
    # unregistered -> registered
    # =======================================================================

    def register_signal(self, signal_id: str, signal_type: SignalType, description: str,
                        registered_by: str, referent: Referent, evaluated_process: str,
                        steward: Optional[str] = None, successor: Optional[str] = None,
                        closure_authority: Iterable[str] = (),
                        recurrence_group: Optional[str] = None,
                        evidence_ids: Iterable[str] = (),
                        failure_mode: Optional[str] = None) -> Signal:
        """
        Register a new coordination signal.

        Enter:   signal_id          unique id
                 signal_type        one of the six types (Rule 1, "How it
                                    fails")
                 description        what the signal says
                 registered_by      the registering agent (also the actor)
                 referent           the R5.3 referent it was raised from:
                                    technical reality or the customer as a
                                    contracting party (used for role-switch
                                    detection, ACT IV, Scene 1)
                 evaluated_process  the process under evaluation (EES test)
                 steward            named steward, if any (Layer 0, AP.1)
                 successor          named successor, if any (AP.1b)
                 closure_authority  agents allowed to close it; empty = no
                                    boundary registered (see ACT IV, Scene 2)
                 recurrence_group   group id for Rule 7 tracking, if any
                 evidence_ids       evidence already on file at registration
                 failure_mode       failure mode for Layer 0 checks, if any
        Exit:    the new Signal, in state `registered`; may open a Rule 7
                 review (ACT VI, Scene 3); raises TransitionRefused if the
                 id is already used

        Spec: Layer 4 state machine, "unregistered -> registered (signal
        enters the system)". Rule 1 ("What it requires") is why signals are
        registered at all: "Safety-relevant signals must remain
        operationally visible through the full commitment process."
        """
        # PLAYERS IN THIS SCENE
        #   at    the clock value at registration
        #   sig   the new Signal

        self._require_actor(registered_by)
        at = self._tick()
        if signal_id in self.signals:
            raise TransitionRefused(f"signal {signal_id!r} already registered")
        # --- Build the signal ----------------------------------------------
        sig = Signal(signal_id, signal_type, description, registered_by, referent,
                     evaluated_process, steward, successor, frozenset(closure_authority),
                     recurrence_group, failure_mode)
        # --- Remember what evidence existed at registration ----------------
        # This snapshot is what Evidence Novelty (ACT II, Scene 1) compares
        # against: nothing in it can later count as "new".
        sig.evidence_ids = list(evidence_ids)
        sig.evidence_at_registration = frozenset(sig.evidence_ids)
        sig.registered_at = at
        self.signals[signal_id] = sig
        # --- Enter the state machine ---------------------------------------
        # The referent, process under evaluation and evidence present at
        # registration are logged so that another agent can recompute this
        # signal's closure type from the log alone (cclf/federation.py).
        self._move(sig, S.REGISTERED, registered_by, signal_type=signal_type,
                   description=description, steward=steward, successor=successor,
                   recurrence_group=recurrence_group, failure_mode=failure_mode,
                   referent=referent, evaluated_process=evaluated_process,
                   evidence_at_registration=sorted(sig.evidence_at_registration))
        # --- Rule 7: does this signal push its group over the threshold? ---
        self._check_recurrence(sig, registered_by)
        return sig

    # =======================================================================
    # ACT III, SCENE 2 — WHAT STATE ARE WE IN?
    # Rule 2: classify a signal's operational state, never nominal unvalidated.
    # =======================================================================

    def classify(self, signal_id: str, state: O, by: str,
                 evidence_ids: Iterable[str] = (), proposed_by_model: bool = False) -> O:
        """
        Rule 2: explicit operational-state classification. "Unvalidated
        conditions cannot be classified as nominal": nominal needs at least
        one cited item that is an External Evidence Source for the
        classifying agent's claim; otherwise the classification is recorded
        as elevated uncertainty and the refusal is audited.

        Enter:   signal_id          the signal to classify
                 state              the proposed operational state (one of
                                    the five in Key Definitions, Operational
                                    State)
                 by                 the classifying agent
                 evidence_ids       evidence cited in support
                 proposed_by_model  True if a model proposed this (advisor.py);
                                    recorded, and given no extra weight
        Exit:    the operational state actually applied

        Spec: Rule 2, Classification Precedes Action: "Every execution-class decision
        requires explicit operational state classification. Unvalidated
        conditions cannot be classified as nominal ... Classification must
        be supported by evidence, not assumed." Why: a misclassified state
        is "a systematically wrong input to every subsequent coordination
        decision" (the Challenger launch was classified nominal below any
        validated O-ring temperature).

        IMPLEMENTATION DECISION (nominal needs cited EES evidence): a
        nominal classification is accepted only if at least one cited item
        passes is_ees() with the classifying agent as claimant ("the
        registering or reclassifying agent, for a reversal path or a
        classification", Layer 2, EES). Novelty is not required here. The
        runtime cannot check what the evidence actually says, only its kind
        and who produced it; a rejected nominal is downgraded to
        elevated_uncertainty rather than refused outright. The irreversible
        and elevated gates check the evidence again, with the accepting
        agent excluded too (ACT VIII, Scene 8).

        Effects:
          - the first classification moves registered -> classified (Layer 4:
            "registered -> classified (Rule 2: required before review opens)");
            later reclassifications just update the operational state
          - every classification is appended to classification_history,
            which _classification_stable() (ACT VIII, Scene 5) reads, and to
            classification_records with who classified and on what evidence
          - off_envelope or containment escalates to structural review
            (Layer 2, Escalation Conditions: "Operational state classified
            as off-envelope or containment"); the review records which of
            the two it was, since they are resolved differently
        """
        # PLAYERS IN THIS SCENE
        #   sig       the signal being classified
        #   cited     the cited Evidence records that exist (unknown ids skipped)
        #   applied   the state actually recorded (may be downgraded)

        self._require_actor(by)
        self._tick()
        sig = self._signal(signal_id)
        # --- Gather the cited evidence -------------------------------------
        # A list comprehension: [expr for x in items if cond] builds a list
        # in one line. Unknown evidence ids are silently left out.
        cited = [self.evidence[e] for e in evidence_ids if e in self.evidence]
        applied = state
        # --- Rule 2: no unvalidated nominal --------------------------------
        # any(... for ev in cited) is a generator expression fed to any():
        # it yields one True/False per item and any() stops at the first
        # True. With no cited evidence, any() is False.
        if state == O.NOMINAL and not any(self.is_ees(ev, sig, by) for ev in cited):
            applied = O.ELEVATED_UNCERTAINTY
            self._log("CLASSIFICATION_REJECTED", by, signal=signal_id, proposed=state,
                      applied=applied, proposed_by_model=proposed_by_model,
                      reason="Rule 2: unvalidated conditions cannot be classified as nominal")
        # --- First classification moves the commitment state ---------------
        if sig.state == S.REGISTERED:
            self._move(sig, S.CLASSIFIED, by)
        # --- Record the classification -------------------------------------
        sig.operational_state = applied
        sig.classification_history.append((self.clock, applied))
        sig.classification_records.append(ClassificationRecord(
            self.clock, applied, by, tuple(e.evidence_id for e in cited), state))
        self._log("CLASSIFIED", by, signal=signal_id, operational_state=applied,
                  evidence=list(evidence_ids), proposed_by_model=proposed_by_model)
        # --- Escalation condition: off-envelope or containment -------------
        # If the signal is not under review yet, _escalate() only records the
        # review; the signal is escalated when it reaches review
        # (_apply_pending_escalations, ACT VI, Scene 2). `trigger` keeps the
        # two apart: one review per signal per trigger.
        if applied in (O.OFF_ENVELOPE, O.CONTAINMENT):
            self._escalate(E.OFF_ENVELOPE_OR_CONTAINMENT, signal_id,
                           f"classified {applied.value}", [signal_id], by, trigger=applied)
        return applied

    # =======================================================================
    # ACT III, SCENE 3 — THE REVIEW OPENS
    # classified -> under_review
    # =======================================================================

    def open_review(self, signal_id: str, by: str) -> None:
        """
        Open active analysis on a classified signal. This is the only route
        in from `classified`; the other routes into review each have their own
        operation and audit obligations: reopen() for a closed signal,
        resolve_review() for an escalated one, reenter_suppressed() for a
        suppressed one, reenter() for an exited one.

        Enter:   signal_id   a signal in state `classified`
                 by          the agent opening review
        Exit:    None; the signal is under_review (or escalated at once, if
                 an unresolved review already names it); raises
                 TransitionRefused with a hint at the right route otherwise

        Spec: Layer 4 state machine, "classified -> under_review (active
        analysis opened)". Recording `first_review_opened_at` matters
        for classification stability (ACT VIII, Scene 5).
        """
        # PLAYERS IN THIS SCENE
        #   sig      the signal
        #   routes   state -> the operation to use instead (for the error)
        #   hint     the advice included in the refusal message

        self._require_actor(by)
        sig = self._signal(signal_id)
        # --- Wrong state: refuse, but point to the right door --------------
        if sig.state != S.CLASSIFIED:
            routes = {S.ESCALATED: "resolve its structural review (Rule 8)",
                      S.SUPPRESSED: "use reenter_suppressed()",
                      S.EXITED: "use reenter()"}
            # `A if cond else B` is Python's one-line if/else expression.
            # routes.get(key, default) returns the default for any state not
            # in the dict (registered, under_review, trajectory_lock, ...).
            hint = ("use reopen() with a rationale" if sig.state in CLOSED_STATES
                    else routes.get(sig.state, "classify it first (Rule 2)"))
            raise TransitionRefused(f"open_review needs a classified signal; {signal_id} is "
                                    f"{sig.state.value}: {hint}")
        # --- Open review ---------------------------------------------------
        self._tick()
        self._move(sig, S.UNDER_REVIEW, by)
        sig.review_opened_at = self.clock
        # The first opening is kept: classification stability is judged
        # from it, whatever reopens follow (ACT VIII, Scene 5).
        if sig.first_review_opened_at < 0:
            sig.first_review_opened_at = self.clock
        # --- Any escalation already waiting for this signal applies now ----
        self._apply_pending_escalations(sig, by)

    # ###########################################################################
    # ACT IV — CLOSURE TYPING
    # How a closure is classed as evidence, authority, role-switch or lock-in,
    # and when it is only an attempted closure.
    # ###########################################################################

    # =======================================================================
    # ACT IV, SCENE 1 — WHAT KIND OF CLOSURE IS THIS?
    # Type a closure by its features, then apply it.
    # =======================================================================

    def attempt_closure(self, signal_id: str, by: str, referent: Referent,
                        evidence_ids: Iterable[str] = (), rationale: str = "") -> ClosureRecord:
        """
        Type a closure by its features (Layer 2), then apply it.

          - closer outside the signal's closure authority -> attempted closure:
            recorded, no state change (Autonomy-Bounded Closure)
          - at least one cited item both novel and EES for the closing
            agent's claim -> evidence closure
          - same agent as registrant, consulting the other referent, nothing
            new -> role-switch closure (R5.3; Key Definitions)
          - otherwise -> authority closure

        Enter:   signal_id      the signal to close (must be under_review for
                                a real closure; see _move)
                 by             the closing agent
                 referent       the referent the closer is consulting now
                 evidence_ids   evidence cited for the closure
                 rationale      the closer's stated reason
        Exit:    the ClosureRecord (see _apply_closure for the effects)

        The closure types (Layer 2, Closure Quality):
          Evidence closure      "New data or analysis resolves the
                                constraint" — Valid.
          Authority closure     "A senior agent overrides without new
                                evidence" — Flagged.
          Role-switch closure   "The same agent closes their own signal by
                                changing roles" — Flagged.
          (Lock-in closure is not created by this runtime: an override now
          latches open loops into executed_open instead; see ACT VIII,
          Scene 8.)
        Why the spec types closures: Layer 2 exists to tell "whether a loop
        actually closed, or was merely recorded as closed" (Layer 2,
        opening paragraph). Flagged closures are not blocked; they are
        permanently recorded as what they are.

        Evidence closure needs both tests: "The two requirements are jointly
        necessary and independently insufficient" (EES, "Relationship to
        Evidence Novelty").

        IMPLEMENTATION DECISION (role-switch detected by referent change):
        the spec's defining test (Key Definitions, Role-Switch Closure) is
        "did the agent close the signal by consulting a different referent
        than the one that generated it, without that referent supplying
        anything new". The code checks this as: the
        closer is the registrant, the `referent` passed in differs from the
        referent recorded at registration, and no evidence qualified. It
        relies on the caller stating the referent honestly.

        The fallback to authority closure: the EES "Principle" paragraph
        says a closure without an EES is "authority closure, role-switch
        closure, or false closure depending on its other features". Here
        every closure that is neither evidence nor role-switch is typed
        authority, including a registrant closing their own signal under
        the same referent with nothing new.
        """
        # PLAYERS IN THIS SCENE
        #   sig          the signal
        #   evidence_ids the cited ids, frozen into a tuple (see below)
        #   cited        cited Evidence records that exist (unknown ids skipped)
        #   qualifying   ids of cited evidence that is both novel and EES
        #   ctype        the closure type decided here

        self._require_actor(by)
        sig = self._signal(signal_id)
        self._tick()
        # --- Freeze the cited ids ------------------------------------------
        # tuple(...) turns whatever iterable was passed into a fixed tuple,
        # so it can be looped over more than once and stored in the record.
        evidence_ids = tuple(evidence_ids)
        cited = [self.evidence[e] for e in evidence_ids if e in self.evidence]
        # --- Which cited items are both new and independent? ---------------
        # The closing agent is the claimant: their own evidence cannot be
        # the External Evidence Source for their own closure.
        qualifying = [ev.evidence_id for ev in cited
                      if self.is_novel(ev, sig) and self.is_ees(ev, sig, by)]
        # --- Type the closure (first matching rule wins) -------------------
        if qualifying:
            ctype = ClosureType.EVIDENCE
        elif by == sig.registered_by and referent != sig.registrant_referent:
            ctype = ClosureType.ROLE_SWITCH
        else:
            ctype = ClosureType.AUTHORITY
        return self._apply_closure(sig, by, referent, ctype, evidence_ids, rationale,
                                   qualifying)

    # =======================================================================
    # ACT IV, SCENE 2 — THE CLOSURE IS ENTERED IN THE RECORD
    # Record a typed closure, or only an attempted one.
    # =======================================================================

    def _apply_closure(self, sig: Signal, by: str, referent: Optional[Referent],
                       ctype: ClosureType, evidence_ids: tuple, rationale: str,
                       qualifying: list[str]) -> ClosureRecord:
        """
        Record a typed closure; an out-of-authority closer only attempts it.

        Enter:   sig            the signal
                 by             the closing agent
                 referent       the closer's referent (None for frame adoption)
                 ctype          the closure type already decided
                 evidence_ids   all cited evidence ids
                 rationale      the closer's stated reason
                 qualifying     the cited ids that were novel and EES
        Exit:    the ClosureRecord. For a real closure: the signal moves to
                 the matching closed state (via _move, so it must be
                 under_review) and escalation checks run. For an attempted
                 closure: only an ATTEMPTED_CLOSURE entry is written.

        Spec: Layer 3, Autonomy-Bounded Closure. "Closure authority
        is bounded by agent autonomy ... Beyond that boundary, closure can
        be attempted but not enforced." Attempted Closure "is recorded as a
        coordination event but does not constitute loop resolution. It is
        the most common precursor to false closure." Why the spec has it:
        treating a transmitted closure as a real one is how false closure
        happens.

        IMPLEMENTATION DECISION (no registered boundary = no limit): if the
        signal's closure_authority set is empty, any agent's closure counts
        as a real closure. Only a non-empty set marks out-of-authority
        closers as attempting.

        After a real closure, two escalation conditions are checked (Layer 2,
        Escalation Conditions):
          - "Role-switch closure detected on a safety-constraint signal"
          - "Authority closure count exceeds threshold on an irreversible
            decision", for every decision that includes this signal (only
            decisions whose applied class is irreversible are counted; see
            ACT VI, Scene 4)

        If the signal is not under_review, _move refuses the real closure
        after the closure counter has already advanced; nothing else
        changes.
        """
        # PLAYERS IN THIS SCENE
        #   signal_id   the signal's id (short name)
        #   attempted   True if the closer is outside the closure authority
        #   record      the ClosureRecord ("C<n>")
        #   target      the closed commitment state matching ctype
        #   chain_ok    for an evidence closure, whether it is chain-sound
        #               (None for other closure types)
        #   broken      upstream loops of any cited item that are not
        #               resolved (the broken links)
        #   d           each registered decision, when checking authority counts

        signal_id = sig.signal_id
        self._closure_seq += 1
        # --- Is the closer inside the signal's closure authority? ----------
        attempted = bool(sig.closure_authority) and by not in sig.closure_authority
        record = ClosureRecord(f"C{self._closure_seq}", signal_id, ctype, by, referent,
                               evidence_ids, rationale, self.clock, attempted_only=attempted)
        # --- Attempted closure: record it, change nothing ------------------
        if attempted:
            sig.closures.append(record)
            self._log("ATTEMPTED_CLOSURE", by, signal=signal_id, closure_type=ctype,
                      record=record.record_id, rationale=rationale,
                      reason="closer is outside the signal's closure authority; "
                             "recorded, not resolved")
            return record

        # --- Real closure: move to the matching closed state ---------------
        # A dict used as a lookup table, indexed immediately with [ctype].
        # `flagged` in the audit entry marks every non-evidence closure, as
        # the spec's Closure Quality table does.
        target = {ClosureType.EVIDENCE: S.CLOSED_EVIDENCE,
                  ClosureType.AUTHORITY: S.CLOSED_AUTHORITY,
                  ClosureType.ROLE_SWITCH: S.CLOSED_ROLE_SWITCH}[ctype]
        # Closure Chain: an evidence closure that is not chain-sound is
        # "recorded as an evidence closure, with the broken link shown in
        # the record". broken_links names each upstream loop of ANY cited
        # item ("every cited item is load-bearing") that is not itself
        # resolved right now.
        chain_ok, broken = None, []
        if ctype == ClosureType.EVIDENCE:
            chain_ok = self._closure_sound(record, sig, frozenset())
            broken = sorted({up for e in evidence_ids if e in self.evidence
                             for up in self.evidence[e].depends_on
                             if not self._loop_resolved(up, frozenset({signal_id}))})
        self._move(sig, target, by, closure_type=ctype, record=record.record_id,
                   qualifying_evidence=qualifying, cited_evidence=list(evidence_ids),
                   rationale=rationale, flagged=ctype != ClosureType.EVIDENCE,
                   chain_sound=chain_ok, broken_links=broken, closer_referent=referent)
        sig.closures.append(record)

        # --- Escalation: role-switch closure on a constraint signal --------
        if ctype == ClosureType.ROLE_SWITCH and sig.is_constraint:
            self._escalate(E.ROLE_SWITCH_ON_CONSTRAINT, signal_id,
                           "role-switch closure on a safety-constraint signal",
                           [signal_id], by)
        # --- Escalation: authority closures on irreversible decisions ------
        if ctype == ClosureType.AUTHORITY:
            for d in self.decisions.values():
                if signal_id in d.signal_ids:
                    self._check_authority_count(d, by)
        return record

    # =======================================================================
    # ACT IV, SCENE 3 — THE FRAME IS ADOPTED
    # A framing signal closes by authority and suppresses what it displaces.
    # =======================================================================

    def adopt_frame(self, framing_signal_id: str, by: str, displaces: Iterable[str],
                    rationale: str = "") -> None:
        """
        A framing signal achieves frame adoption: "an authority closure of the
        framing signal combined with a suppression event on the signals it
        displaced" (Key Definitions, Framing Signal).

        Enter:   framing_signal_id   a signal of type FRAMING, under_review
                 by                  the adopting agent
                 displaces           ids of the signals the frame displaces
                 rationale           the stated reason
        Exit:    None. The framing signal is authority-closed (or only
                 attempted, in which case nothing else happens); displaced
                 signals that were under_review are suppressed; if any of
                 them is a constraint signal, a structural review opens.

        Spec: Key Definitions, Framing Signal, and Rule 1 ("How it fails"):
        a framing signal "shift[s] how other signals are understood";
        Rule 1's "What to do": "Track whether a framing signal has displaced
        a technical signal's standing, and flag this as a suppression
        event." Escalation condition (Layer 2, Escalation Conditions):
        "Framing signal achieves frame adoption while technical constraint
        signals remain open." Why: this is how "prove it's unsafe" replaced
        "prove it's safe" at Challenger.

        Only displaced signals that are under_review at the call are
        suppressed (the state machine allows suppression only from
        under_review); other displaced ids are ignored. An unknown id is
        refused before anything changes.
        """
        # PLAYERS IN THIS SCENE
        #   sig         the framing signal
        #   displaced   ids of displaced signals that are under_review now
        #   record      the closure record for the framing signal
        #   d           each displaced signal id

        self._require_actor(by)
        sig = self._signal(framing_signal_id)
        if sig.signal_type != SignalType.FRAMING:
            raise TransitionRefused(f"{framing_signal_id} is not a framing signal")
        # --- Which displaced signals can be suppressed? --------------------
        displaced = [d for d in displaces if self._signal(d).state == S.UNDER_REVIEW]
        self._tick()
        # Frame adoption is authority closure by definition, whoever adopts it.
        record = self._apply_closure(sig, by, None, ClosureType.AUTHORITY, (), rationale, [])
        # --- An attempted adoption changes nothing else --------------------
        if record.attempted_only:
            return
        # --- The suppression half of frame adoption ------------------------
        for d in displaced:
            self.suppress(d, by, f"displaced by frame adoption of {framing_signal_id}")
        # --- Escalation: frame adopted over open constraint signals --------
        if any(self.signals[d].is_constraint for d in displaced):
            self._escalate(E.FRAMING_ADOPTED_OVER_OPEN_CONSTRAINTS, framing_signal_id,
                           "framing signal adopted while technical constraint signals "
                           "remained open", displaced, by)

    # ###########################################################################
    # ACT V — THE SIGNAL LIFECYCLE CONTINUED: SUPPRESSION, REOPENING, EXITS
    # The ways a signal leaves review without evidence closure, and the
    # logged routes back in.
    # ###########################################################################

    # =======================================================================
    # ACT V, SCENE 1 — THE SIGNAL GOES QUIET
    # under_review -> suppressed
    # =======================================================================

    def suppress(self, signal_id: str, by: str, reason: str) -> None:
        """
        Record that a signal lost operational visibility.

        Enter:   signal_id   a signal under_review
                 by          the agent responsible
                 reason      why (logged)
        Exit:    None; the signal is suppressed and the clock time is added
                 to its suppression_events

        Spec: Layer 4 state machine, "under_review -> suppressed (signal
        lost operational visibility)". Suppression is the Rule 1 failure
        made visible: "present in the record but absent from the decision"
        (Rule 1, "How it fails"). Suppression events are kept permanently
        ("suppression permanent", Layer 4 recovery transitions). A
        suppressed signal cannot be closed directly (Layer 4, Commitment
        State Machine, blocked transitions).
        """
        # PLAYERS IN THIS SCENE
        #   sig   the signal

        self._require_actor(by)
        self._tick()
        sig = self._signal(signal_id)
        self._move(sig, S.SUPPRESSED, by, reason=reason)
        sig.suppression_events.append(self.clock)

    # =======================================================================
    # ACT V, SCENE 2 — THE SIGNAL SPEAKS AGAIN
    # suppressed -> under_review, with a logged rationale
    # =======================================================================

    def reenter_suppressed(self, signal_id: str, by: str, rationale: str) -> None:
        """
        Bring a suppressed signal back into review.

        Enter:   signal_id   a suppressed signal
                 by          the agent bringing it back
                 rationale   required; why it re-enters
        Exit:    None; the signal is under_review (or escalated at once if an
                 unresolved review names it); refuses with no rationale or
                 if the signal is not suppressed

        Spec: Layer 4 recovery transition, "suppressed -> under_review
        (re-entry logged; suppression permanent)". The audit
        entry carries the full list of past suppression events, so the
        suppression is not erased by the re-entry.

        Note: review_opened_at is not updated here (reopen() and reenter()
        do update it). Classification stability is measured from the
        signal's FIRST review opening (first_review_opened_at), which _move
        sets on any first entry into review and no later entry changes.
        """
        # PLAYERS IN THIS SCENE
        #   sig   the signal

        self._require_actor(by)
        if not rationale:
            raise TransitionRefused("re-entry from suppression must be logged with a rationale")
        sig = self._signal(signal_id)
        if sig.state != S.SUPPRESSED:
            raise TransitionRefused(f"{signal_id} is not suppressed")
        self._tick()
        self._move(sig, S.UNDER_REVIEW, by, rationale=rationale,
                   suppression_events=list(sig.suppression_events))
        self._apply_pending_escalations(sig, by)

    # =======================================================================
    # ACT V, SCENE 3 — THE CASE IS REOPENED
    # closed -> under_review, never silently
    # =======================================================================

    def reopen(self, signal_id: str, by: str, rationale: str) -> None:
        """
        "A closed loop cannot be silently reopened — every reopen transition
        is permanently logged with rationale, the identity of the reopening
        agent, and the closure record it supersedes." A role-switch closure
        additionally needs an independent reviewer.

        Enter:   signal_id   a signal in one of the three closed states
                 by          the reopening agent
                 rationale   required; why it is reopened
        Exit:    None; the signal is under_review again (or escalated if an
                 unresolved review names it), reopen_count goes up by one,
                 review_opened_at is reset, and a CHAIN_WEAKENED entry is
                 logged for every other signal whose closure was chain-sound
                 before the reopen and is not after it (Layer 2, Closure
                 Chain)

        Spec: Layer 4, Commitment State Machine: the blocked transitions,
        quoted above; the reopen transitions, including "closed_role_switch
        -> under_review (mandatory independent review; L2 flag)". Why
        closed states can be reopened at all (same section): "a state machine
        in which closure is irreversible cannot express the framework's own
        core diagnostic", false closure. The reopen history "feeds ...
        the coherence score" (see closure_quality in ACT VIII, Scene 6).

        IMPLEMENTATION DECISION (who counts as independent): for a
        role-switch closure, the reopening agent must be neither the
        signal's registrant nor the agent who made the superseded closure.
        """
        # PLAYERS IN THIS SCENE
        #   sig            the signal
        #   superseded     the latest real (not attempted) closure record
        #   sound_before   other signals that were chain-sound before the reopen
        #   sid            each of them, rechecked after it

        self._require_actor(by)
        if not rationale:
            raise TransitionRefused("BLOCKED: a closed loop cannot be silently reopened "
                                    "(rationale required)")
        self._tick()
        sig = self._signal(signal_id)
        if sig.state not in CLOSED_STATES:
            raise TransitionRefused(f"{signal_id} is not closed")
        # --- Find the closure this reopen supersedes -----------------------
        # next(generator) returns the first item the generator yields.
        # reversed(...) walks the list from the end, so this is the most
        # recent closure that was not merely attempted. (A closed signal
        # always has one, so next() never runs out here.)
        superseded = next(c for c in reversed(sig.closures) if not c.attempted_only)
        # --- Role-switch closures need an independent reviewer -------------
        if sig.state == S.CLOSED_ROLE_SWITCH and by in (sig.registered_by, superseded.closed_by):
            raise TransitionRefused("reopening a role-switch closure requires an "
                                    "independent reviewer")
        # --- Which downstream closures stand on this one? ------------------
        # Recorded before the reopen so the loss can be logged after it.
        sound_before = {sid for sid in self.signals
                        if sid != signal_id and self._signal_sound(sid, frozenset())}
        # --- Reopen, logging the superseded record -------------------------
        self._move(sig, S.UNDER_REVIEW, by, rationale=rationale,
                   supersedes=superseded.record_id,
                   independent_review_required=sig.state == S.CLOSED_ROLE_SWITCH)
        sig.reopen_count += 1
        sig.review_opened_at = self.clock
        # --- Closure Chain: log every downstream closure that lost standing
        # ("every closure downstream of it loses its standing, and the
        # weakened link is logged"). sorted() keeps the log order stable.
        for sid in sorted(sound_before):
            if not self._signal_sound(sid, frozenset()):
                self._log("CHAIN_WEAKENED", by, signal=sid, upstream=signal_id)
        self._apply_pending_escalations(sig, by)

    # =======================================================================
    # ACT V, SCENE 4 — THE SIGNAL EXITS
    # any open state -> exited(type), with the exit type's obligations
    # =======================================================================

    def exit(self, signal_id: str, exit_type: ExitType, by: str, rationale: str,
             open_loop_state: str = "", successor: Optional[str] = None,
             external_pathway: Optional[str] = None, suppression_ref: Optional[str] = None,
             legal_subtype: Optional[LegalSubtype] = None,
             resolution_condition: Optional[str] = None,
             evidence_ids: Iterable[str] = ()) -> ExitRecord:
        """
        Register a loop exit, enforcing its Layer 2 audit obligations.

        Enter:   signal_id          an open signal
                 exit_type          one of the fourteen exit types
                 by                 the agent registering the exit
                 rationale          why
                 open_loop_state    note of the loop's state at exit
                                    (required for terminal, legal, key person)
                 successor          new steward (required for delegated)
                 external_pathway   where it went (required for whistleblower)
                 suppression_ref    the triggering suppression event
                                    (required for whistleblower)
                 legal_subtype      required for legal exits
                 resolution_condition  for containment, deferred, ambiguity:
                                    what the loop is waiting for (optional;
                                    without it the exit cannot re-enter)
                 evidence_ids       evidence cited with the exit (already
                                    added). For a superseded exit, an
                                    External Evidence Source among it for the
                                    exiting agent's claim resolves a
                                    constraint or anomaly loop at the
                                    irreversible gate and in the Closure
                                    Chain (_supersession_shown, ACT II,
                                    Scene 2b). Unknown ids are refused.
        Exit:    the ExitRecord; the signal is `exited`. Delegated exits make
                 `successor` the signal's steward.

        Spec: Layer 2, Loop Exit Taxonomy and Layer 4 (Commitment State
        Machine) "any open state -> exited(type)". Why: "An unregistered
        exit is structurally equivalent to a suppressed signal — the loop
        disappears from active monitoring while the hazard it named may
        persist." The obligations checked here are the spec's "Exit
        obligations" and the four legal sub-types ("Notes on specific exit
        types"), both in the Loop Exit Taxonomy. For containment, deferred
        and ambiguity exits the spec says they "should register a
        resolution condition"; that is not enforced here, but without one
        reenter() refuses them.

        This changes sig.state directly rather than through _move(): the
        transition table in statemachine.py does not hold exits, and
        exit_allowed() is the check for them. An exited signal may still
        count as an open loop, depending on its exit type (Signal.is_open).
        """
        # PLAYERS IN THIS SCENE
        #   sig        the signal
        #   ok, reason (may exit?, rule or blocking reason); the first unmet
        #              obligation, if any, replaces them
        #   record     the new ExitRecord
        #   previous   the state before the exit (logged as "from")

        self._require_actor(by)
        evidence_ids = tuple(evidence_ids)
        self._check_evidence_ids(evidence_ids, "evidence cited with the exit")
        self._tick()
        sig = self._signal(signal_id)
        # --- Only open signals can exit ------------------------------------
        ok, reason = exit_allowed(sig.state)
        # --- The exit type's audit obligations -----------------------------
        # The first unmet one becomes the refusal reason.
        if ok and exit_type in EXIT_TYPES_REQUIRING_OPEN_STATE_NOTE and not open_loop_state:
            ok, reason = False, (f"{exit_type.value} exit requires explicit notation of "
                                 "the open loop state at the time of exit")
        if ok and exit_type == ExitType.DELEGATED and not successor:
            ok, reason = False, "delegated exit requires successor registration"
        if ok and exit_type == ExitType.WHISTLEBLOWER and not (external_pathway
                                                              and suppression_ref):
            ok, reason = False, ("whistleblower exit requires the external pathway and the "
                                 "suppression event that triggered it")
        if ok and exit_type == ExitType.LEGAL and legal_subtype is None:
            ok, reason = False, "legal exit requires its sub-type"
        # --- A refused exit is logged, like a refused transition -----------
        # "An unregistered exit is structurally equivalent to a suppressed
        # signal": an attempted exit that fails its obligations stays on
        # the record too.
        if not ok:
            self._log("EXIT_REFUSED", by, signal=signal_id, exit_type=exit_type,
                      state=sig.state, reason=reason)
            raise TransitionRefused(reason)
        # --- Build the record ----------------------------------------------
        # When no note was given, the commitment state's name is stored as
        # the open loop state (`a or b` picks b when a is "").
        record = ExitRecord(signal_id, exit_type, by, rationale,
                            open_loop_state or sig.state.value, self.clock, successor,
                            external_pathway, suppression_ref, legal_subtype,
                            resolution_condition, evidence_ids)
        # --- Apply the exit ------------------------------------------------
        previous = sig.state
        sig.state = S.EXITED
        sig.exit = record
        # Delegated: "loop remains open under new stewardship" (Loop Exit
        # Taxonomy).
        if exit_type == ExitType.DELEGATED:
            sig.steward = successor
        self._log("EXIT", by, signal=signal_id, exit_type=exit_type, **{"from": previous},
                  rationale=rationale, open_loop_state=record.open_loop_state,
                  successor=successor, external_pathway=external_pathway,
                  suppression_ref=suppression_ref, legal_subtype=legal_subtype,
                  resolution_condition=resolution_condition, evidence=list(evidence_ids))
        return record

    # =======================================================================
    # ACT V, SCENE 5 — THE RETURN
    # exited -> under_review, where the exit type allows it
    # =======================================================================

    def reenter(self, signal_id: str, by: str, rationale: str,
                legal_resumes: Optional[bool] = None,
                new_steward: Optional[str] = None,
                condition_met: bool = False) -> None:
        """
        Return an exited signal to review where its exit type allows it.
        Forced and key-person exits need a successor steward (the signal's
        registered successor, one registered for its failure mode, or
        `new_steward`); a boundary exit must be resumed by a different agent.

        Enter:   signal_id      an exited signal
                 by             the agent bringing it back
                 rationale      required
                 legal_resumes  for legal exits: has the external authority
                                lifted it?
                 new_steward    a steward to take over (forced / key person)
                 condition_met  for containment / deferred / ambiguity: the
                                re-entering agent states that the resolution
                                condition registered at exit is now met
        Exit:    None; the signal is under_review (or escalated at once if an
                 unresolved review names it); refusals of the re-entry rule
                 itself are logged as REENTRY_REFUSED

        Spec: Layer 4 exit transitions (Commitment State Machine). Stated re-entries:
        recoverable and delegated. Inferred re-entries (flagged by the spec
        itself as inference): forced and key person need "successor steward
        registered, inferred from AP.1b"; exhaustion; boundary needs a
        "different agent with covering authority" (from Autonomy-Bounded
        Closure). Legal: regulatory intervention / investigative hold "may
        resume to under_review when lifted". No re-entry: terminal,
        superseded, timeout; whistleblower goes to an external process.
        Containment, deferred and ambiguity re-enter "when the resolution
        condition registered at exit is met"; with none registered they do
        not re-enter. IMPLEMENTATION DECISION D2: the runtime cannot observe
        the condition, so `condition_met` is the re-entering agent's stated
        claim, logged with the condition it answers.

        Like exit(), this sets sig.state directly; reentry_allowed() is the
        check. The "different agent" test for boundary exits is only that
        `by` differs from the agent who registered the exit; the runtime
        does not check covering authority.
        """
        # PLAYERS IN THIS SCENE
        #   sig          the signal
        #   successor    the steward to use: new_steward, else the signal's
        #                successor, else the architecture's successor for its
        #                failure mode (None if none of these exist)
        #   ok, reason   (allowed?, rule or blocking reason)

        self._require_actor(by)
        if not rationale:
            raise TransitionRefused("re-entry must be logged with a rationale")
        sig = self._signal(signal_id)
        if sig.state != S.EXITED or sig.exit is None:
            raise TransitionRefused(f"{signal_id} has not exited")
        # --- Who could take over? (a chain of `or` fallbacks) --------------
        successor = new_steward or sig.successor or self.architecture.successors.get(sig.mode)
        self._tick()
        # --- Ask the re-entry rule for this exit type ----------------------
        ok, reason = reentry_allowed(sig.exit.exit_type, legal_resumes,
                                     sig.exit.legal_subtype, bool(successor),
                                     by != sig.exit.by,
                                     bool(sig.exit.resolution_condition), condition_met)
        if not ok:
            self._log("REENTRY_REFUSED", by, signal=signal_id,
                      exit_type=sig.exit.exit_type, reason=reason)
            raise TransitionRefused(reason)
        # --- Re-enter review -----------------------------------------------
        sig.state = S.UNDER_REVIEW
        sig.review_opened_at = self.clock
        self._mark_first_review(sig, S.UNDER_REVIEW)
        # Forced and key-person exits leave the loop ownerless; the
        # successor takes over as steward (AP.1b).
        if sig.exit.exit_type in (ExitType.FORCED, ExitType.KEY_PERSON):
            sig.steward = successor
        self._log("REENTRY", by, signal=signal_id, exit_type=sig.exit.exit_type,
                  rule=reason, rationale=rationale, steward=sig.steward,
                  resolution_condition=sig.exit.resolution_condition,
                  condition_met=condition_met)
        self._apply_pending_escalations(sig, by)

    # ###########################################################################
    # ACT VI — ESCALATION AND STRUCTURAL REVIEW
    # Rule 7 fires the review; Rule 8 says what it must produce.
    # ###########################################################################

    # ------------------------------------------------------------------
    # Escalation and structural review
    # ------------------------------------------------------------------

    # =======================================================================
    # ACT VI, SCENE 1 — THE ALARM
    # Open a structural review (or add to the one already open).
    # =======================================================================

    def _escalate(self, condition: E, scope: str, detail: str,
                  signal_ids: list[str], actor: str, trigger: Optional[O] = None,
                  decision_id: Optional[str] = None) -> StructuralReview:
        """
        Open a structural review for one of the escalation conditions.

        Enter:   condition    which escalation condition fired
                 scope        what it is about (see StructuralReview.scope)
                 detail       human-readable explanation
                 signal_ids   signals to hold in `escalated` (may be empty)
                 actor        the agent whose operation triggered it
                 trigger      for OFF_ENVELOPE_OR_CONTAINMENT, which state
                              opened it (part of the "same review" test)
                 decision_id  for a post-event review, the executed decision
        Exit:    the StructuralReview (new, or the existing open one)

        Spec: Layer 2, Escalation Conditions: these "automatically escalate
        to structural review". Rule 7 ("What to do"): "mandatory and
        automatic — not a judgment call subject to schedule pressure or
        institutional momentum." Layer 4 state machine: "under_review ->
        escalated".

        IMPLEMENTATION DECISION (one open review per condition, scope and
        trigger): if an unresolved review already exists for the same
        condition, scope and trigger, the new signals are added to it, a REVIEW_JOINED entry is
        logged instead of a new ESCALATION, and any added signal that is
        under_review is escalated at once; the others escalate when they
        reach review (ACT VI, Scene 2).

        For a new review, only the named signals currently under_review are
        moved to `escalated` now. Others named by the review are escalated
        when they reach review (ACT VI, Scene 2).
        """
        # PLAYERS IN THIS SCENE
        #   existing   each review already on file
        #   added      named signals not yet on that review
        #   sid        each signal id named
        #   review     the new StructuralReview
        #   sig        each named signal, or None if the id is unknown

        # One open review per (condition, scope, trigger): a repeat adds to it.
        for existing in self.reviews:
            if (not existing.resolved and existing.condition == condition
                    and existing.scope == scope and existing.trigger == trigger):
                added = [sid for sid in signal_ids if sid not in existing.signal_ids]
                existing.signal_ids.extend(added)
                if added:
                    self._log("REVIEW_JOINED", actor, review=existing.review_id,
                              condition=condition, scope=scope, detail=detail,
                              signals=added)
                # A joining signal already under review escalates now, as it
                # would have if it had been named when the review opened.
                for sid in added:
                    sig = self.signals.get(sid)
                    if sig is not None and sig.state == S.UNDER_REVIEW:
                        self._move(sig, S.ESCALATED, actor, review=existing.review_id)
                return existing
        # --- Open a new review ---------------------------------------------
        review = StructuralReview(f"R{len(self.reviews) + 1}", condition, scope, detail,
                                  self.clock, list(signal_ids), trigger=trigger,
                                  decision_id=decision_id)
        self.reviews.append(review)
        self._log("ESCALATION", actor, review=review.review_id, condition=condition,
                  scope=scope, detail=detail, signals=list(signal_ids), trigger=trigger)
        # --- Escalate the named signals that are under review now ----------
        # dict.get(key) returns None for a missing key instead of raising.
        for sid in signal_ids:
            sig = self.signals.get(sid)
            if sig is not None and sig.state == S.UNDER_REVIEW:
                self._move(sig, S.ESCALATED, actor, review=review.review_id)
        return review

    # =======================================================================
    # ACT VI, SCENE 2 — THE ALARM WAS ALREADY RINGING
    # Escalate a signal that arrives in review while a review names it.
    # =======================================================================

    def _apply_pending_escalations(self, sig: Signal, actor: str) -> None:
        """
        A signal that reaches review while an unresolved escalation names it is escalated.

        Enter:   sig     a signal that has just entered under_review
                 actor   the agent responsible
        Exit:    None; the signal may now be `escalated`

        Why: a review can name a signal that was not under review when the
        review opened (for example, classified off-envelope before review
        opened). Without this, the signal could slip into review and be
        closed while its escalation is still unresolved. Only the first
        matching review moves it; after that its state is no longer
        under_review, so the loop does nothing more.
        """
        # PLAYERS IN THIS SCENE
        #   review   each review on file

        # The trailing backslash `\` continues the `if` condition on the
        # next line.
        for review in self.reviews:
            if not review.resolved and sig.signal_id in review.signal_ids \
                    and sig.state == S.UNDER_REVIEW:
                self._move(sig, S.ESCALATED, actor, review=review.review_id)

    # =======================================================================
    # ACT VI, SCENE 3 — THE THIRD TIME
    # Rule 7: has this recurrence group crossed the threshold?
    # =======================================================================

    def _check_recurrence(self, sig: Signal, actor: str) -> None:
        """
        Escalate a recurrence group when it reaches the threshold.

        Enter:   sig     a newly registered signal
                 actor   the registering agent
        Exit:    None; may open a RECURRENCE_THRESHOLD review on
                 "group:<id>", or add the signal to the one already open

        Spec: Rule 7, Recurring Coordination Failures Trigger Structural
        Review: "Recurrence is structural evidence
        ... When a recurrence group crosses the escalation threshold ...
        structural review is mandatory and automatic". Why: each recurrence
        "closed by authority" separately means "the pattern never
        accumulates into a recognized signal" (seven Challenger O-ring
        erosion missions). Recurrence Group (Key Definitions):
        "linked coordination signals sharing a common failure mode".
        Threshold: D1 (Settings.recurrence_threshold, default 3). The test
        is "members >= threshold", so the third member triggers it.

        Effect (Rule 8, "What counts as an update"): "An update is a claim
        that the failure mode will stop recurring. If the same recurrence
        group recurs after the update, the update is recorded as ineffective
        and a new structural review opens. The earlier resolution stays in
        the record, beside the recurrence that contradicted it." So a new
        member of a group whose review was resolved logs UPDATE_INEFFECTIVE
        naming that review, takes the group out of reviewed_groups, and
        opens a new RECURRENCE_THRESHOLD review on "group:<id>" over every
        member, at once and whatever the threshold.
        """
        # PLAYERS IN THIS SCENE
        #   group         the signal's recurrence group (or None)
        #   members       ids of every registered signal in that group
        #   open_review   the group's unresolved review, or None
        #   resolved      the review whose resolution last reviewed the group

        group = sig.recurrence_group
        if group is None:
            return
        members = [s.signal_id for s in self.signals.values() if s.recurrence_group == group]
        # --- Effect: the group recurred after its update -------------------
        if group in self.reviewed_groups:
            resolved = self.group_resolutions.get(group)
            self.reviewed_groups.discard(group)
            self._log("UPDATE_INEFFECTIVE", actor, group=group, review=resolved,
                      signal=sig.signal_id,
                      reason=f"recurrence group {group!r} recurred after the Rule 8 "
                             f"update that resolved {resolved}")
            self._escalate(E.RECURRENCE_THRESHOLD, f"group:{group}",
                           f"recurrence group {group!r} recurred after review {resolved} was "
                           "resolved: the update is recorded as ineffective", members, actor)
            return
        # --- Is the group already under review? ----------------------------
        # next(generator, None) returns the first match, or None if there is
        # none (the second argument is the default).
        open_review = next((r for r in self.reviews if r.scope == f"group:{group}"
                            and not r.resolved), None)
        if open_review is not None:
            if sig.signal_id not in open_review.signal_ids:
                open_review.signal_ids.append(sig.signal_id)
            return
        # --- Threshold reached: escalate the whole group -------------------
        if len(members) >= self.settings.recurrence_threshold:
            self._escalate(E.RECURRENCE_THRESHOLD, f"group:{group}",
                           f"{len(members)} signals in recurrence group {group!r} "
                           f"(threshold {self.settings.recurrence_threshold})",
                           members, actor)

    # =======================================================================
    # ACT VI, SCENE 4 — TOO MANY OVERRIDES
    # Authority closures on an irreversible decision above the threshold?
    # =======================================================================

    def _check_authority_count(self, d: Decision, actor: str) -> None:
        """
        Escalation condition: authority closure count exceeds the threshold on
        an irreversible decision. Checked whenever an authority closure
        happens, when a decision is registered, and whenever a decision
        gains signals, so the order of events does not matter.

        Enter:   d       a decision
                 actor   the agent whose operation triggered the check
        Exit:    None; may open an AUTHORITY_CLOSURE_COUNT review on
                 "decision:<id>" (with no signals held)

        "Irreversible" here is the APPLIED class (_applied_class, ACT VIII,
        Scene 1b): a decision declared elevated or routine without a tested
        reversal path is counted too.

        Spec: Layer 2, Escalation Conditions. Why: rising authority closure
        frequency is an observable indicator of lock-in pressure (Key
        Definitions, Lock-in Pressure), and Rule 7 names authority
        closure of recurring anomalies as "the organizational signature of a
        system adapting to incoherence". Threshold: D5 (default 1, so the
        second authority closure triggers it).

        Counted: real (not attempted) authority closures across all of the
        decision's registered signals, including earlier closures of signals
        that were later reopened. IMPLEMENTATION DECISION (fires once per
        decision): if this decision has ever had such a review, resolved or
        not, no new one is opened.
        """
        # PLAYERS IN THIS SCENE
        #   count     number of real authority closures on the decision's signals
        #   already   True if this decision has had this review before

        if self._applied_class(d) != ExecutionClass.IRREVERSIBLE:
            return
        # --- Count authority closures --------------------------------------
        # sum(1 for ... for ... if ...) counts matches. A generator can have
        # two `for` clauses: for each signal id, for each of its closures.
        count = sum(1 for sid in d.signal_ids if sid in self.signals
                    for c in self.signals[sid].closures
                    if c.closure_type == ClosureType.AUTHORITY and not c.attempted_only)
        already = any(r.scope == f"decision:{d.decision_id}" and
                      r.condition == E.AUTHORITY_CLOSURE_COUNT for r in self.reviews)
        if count > self.settings.authority_closure_threshold and not already:
            self._escalate(E.AUTHORITY_CLOSURE_COUNT, f"decision:{d.decision_id}",
                           f"{count} authority closures on irreversible decision "
                           f"{d.decision_id}", [], actor)

    # =======================================================================
    # ACT VI, SCENE 5 — THE REVIEW IS RESOLVED
    # Each trigger by what it requires; never by those closest to the decision.
    # =======================================================================

    def _review_decisions(self, review: StructuralReview) -> list[Decision]:
        """
        The decisions whose people may not resolve this review.

        Enter:   review   a structural review
        Exit:    every not-yet-executed decision applied irreversible that the
                 review touches (its scope names the decision, or it holds
                 one of the decision's signals), plus the decision a
                 post-event review is about and every decision an Emergency
                 Justification executed while suspending this review

        Spec (Layer 4, Overrides): "Each resolution is documented by an
        agent who neither accepted the decision nor requested its execution
        and, where reporting lines are registered, sits outside the
        accepting agent's". IMPLEMENTATION DECISION: the reviews an
        Emergency Justification suspended, and its post-event review, keep
        the decision they were about even after it executed: "Each still
        produces its resolution afterward", by the same independent hands.
        """
        # PLAYERS IN THIS SCENE
        #   suspended_for   decisions executed under a justification that
        #                   suspended this review
        #   d               each registered decision

        suspended_for = {dec for (ej, dec, _, _, _) in self.emergencies
                         if ej in review.suspended_by}
        return [d for d in self.decisions.values()
                if (not d.executed
                    and self._applied_class(d) == ExecutionClass.IRREVERSIBLE
                    and (review.scope == f"decision:{d.decision_id}"
                         or set(review.signal_ids) & set(d.signal_ids)))
                or d.decision_id == review.decision_id
                or d.decision_id in suspended_for]

    def _acceptors(self, d: Decision) -> list[str]:
        """
        Every agent who has ever accepted the decision.

        Enter:   d   the decision
        Exit:    the acceptors, oldest first (the current one included)
        """
        return list(d.acceptors) + ([d.accepted_by] if d.accepted_by
                                    and d.accepted_by not in d.acceptors else [])

    def _independence_failures(self, by: str, decisions: Iterable[Decision]) -> list[str]:
        """
        Why `by` may not act as the independent agent for these decisions.

        Enter:   by          the agent who would resolve, override, justify
                             or attest
                 decisions   the decisions concerned
        Exit:    one reason per conflict found (empty: no conflict). A
                 conflict is having EVER accepted a decision, having
                 requested it, or reporting (directly or through others,
                 as the lines stand now) to any agent who ever accepted it.

        Spec: Layer 4, Execution Gates, Overrides ("Separation of
        acceptance and override"; "Structural review holds irreversible
        execution"). IMPLEMENTATION DECISION: the acceptor history counts,
        not only the current acceptor, so a re-acceptance by a subordinate
        cannot hand an earlier acceptor the override, the review or the
        attestation.
        """
        # PLAYERS IN THIS SCENE
        #   reasons     the conflicts found
        #   d           each decision
        #   acceptors   every agent who ever accepted it
        #   boss        an acceptor `by` reports to, if any

        reasons = []
        for d in decisions:
            acceptors = self._acceptors(d)
            if by in acceptors or by in d.requesters:
                reasons.append(f"{by} accepted or requested irreversible decision "
                               f"{d.decision_id}")
                continue
            boss = next((a for a in acceptors if self.in_reporting_line(by, a)), None)
            if boss is not None:
                reasons.append(f"{by} reports to {boss}, who accepted {d.decision_id}, and "
                               "would repeat the acceptor's judgment under another name")
        return reasons

    def _resolution_conflicts(self, review: StructuralReview,
                              decisions: Iterable[Decision]) -> list[str]:
        """
        Is a resolved review's resolution still independent of these
        decisions, judged now?

        Enter:   review      a resolved StructuralReview
                 decisions   the decisions to judge it against
        Exit:    the conflicts found (empty: still independent, or the
                 review is not resolved)

        Independence is judged when it matters, not only when the review
        was resolved: an agent can resolve a review and later accept or
        request the decision it holds, or be placed in its acceptor's
        reporting line. Such a resolution "counts as unresolved and holds"
        (the gate, ACT VIII, Scene 8), and resolve_review() lets an
        independent agent resolve it again.
        """
        if not review.resolved:
            return []
        return self._independence_failures(review.resolved_by, decisions)

    def resolve_review(self, review_id: str, by: str, model_update: str = "",
                       elements_changed: Iterable[str] = (), level: Optional[str] = None,
                       finding: str = "", elements_held: Optional[bool] = None,
                       no_model_change: bool = False) -> None:
        """
        Resolve a structural review by what its trigger requires.
        Escalated signals named by the review that no other open review
        holds recover to under_review.

        Enter:   review_id         an open review ("R<n>"), or a resolved one
                                   whose resolution is no longer independent
                                   of a decision it holds (re-resolution)
                 by                the resolving agent
                 model_update      the documented Rule 8 coordination model
                                   update
                 elements_changed  the registered elements of the
                                   coordination model the update changes,
                                   named (Rule 8 update; at least one)
                 level             for a recurrence review: the level at
                                   which the recurring instances are
                                   generated (Rule 8, "Scope")
                 finding           the written finding (off-envelope,
                                   containment and post-event reviews, and a
                                   no-change finding)
                 elements_held     for a post-event review: True or False,
                                   whether every element of the Emergency
                                   Justification held
                 no_model_change   True to resolve a review of the "every
                                   other condition" kind by an independent
                                   finding, with `finding` as its rationale,
                                   that no model element requires change
        Exit:    None; the review is resolved, a group review marks its
                 group as reviewed, and released signals return to review.
                 Refused (TransitionRefused, and REVIEW_RESOLUTION_REFUSED
                 logged once the review is found) when its trigger's
                 requirement is not met, when `by` lacks obligation
                 capacity, or when `by` is not independent of a decision the
                 review concerns.

        What each trigger requires (Layer 4, Overrides, "Structural review
        holds irreversible execution": "A review opened by an off-envelope
        classification is resolved only by reclassification to nominal or
        elevated uncertainty, supported by an External Evidence Source that
        the condition lies within validated parameters; one opened by a
        containment classification, by independent steward review. A review
        opened by a count crossing its threshold — recurrence (Rule 7),
        authority closures, AP-G — or by relabeling after refusal is
        resolved only by a Rule 8 update. A review opened by any other
        condition is resolved by that update, or by a documented finding
        from the independent reviewer, with rationale, that the event was
        handled on its own record and no model element requires change."):
          off-envelope   every signal it names has been reclassified, after
                         the review opened, to nominal or elevated
                         uncertainty (not containment, not experimental),
                         citing an EES for the reclassifying agent's claim
                         (no acceptor of a decision concerned may produce
                         it); plus a written finding. That reclassification
                         is recorded as resolving, so it does not count as
                         a lowering (_lowerings)
          containment    an independent steward review: a written finding
                         by an agent who passes the independence checks,
                         recorded as the reviewing steward
          post-event     a written finding on whether every element of the
                         Emergency Justification held
          a count or relabeling (RULE8_ONLY_CONDITIONS)
                         a Rule 8 update meeting "What counts as an
                         update": model_update and elements_changed; a
                         recurrence review also names the level
          every other    that Rule 8 update, or no_model_change with a
                         written finding
        The runtime checks that each element is documented, not that the
        update is a real change rather than a re-approval in other words.

        Independence (Layer 4, Overrides): the resolver has never accepted
        and has not requested a decision the review concerns
        (_review_decisions), does not report to any agent who accepted one,
        and has obligation capacity (Agent Admissibility: resolving a review
        is a stewardship act). Layer 4 recovery transition: "escalated ->
        under_review (review resolved as its trigger requires; suspension
        under an Emergency Justification does not release it)" happens only
        here.
        """
        # PLAYERS IN THIS SCENE
        #   review       the review being resolved
        #   tainted      conflicts of its earlier resolution, for a
        #                re-resolution
        #   problems     every unmet requirement found
        #   decisions    the decisions it concerns (_review_decisions)
        #   acceptors    every agent who ever accepted one (excluded from EES)
        #   kind         which trigger rule applies, for the log
        #   rule8        whether a complete Rule 8 update was documented
        #   rule8_gaps   what is missing from it
        #   resolving    (signal, classification tick) pairs that resolve an
        #                off-envelope review
        #   sid, sig     each signal it names
        #   last         that signal's latest classification record
        #   why          the refusal message
        #   still_held   True if another unresolved review also names a signal

        self._require_actor(by)
        elements_changed = tuple(elements_changed)
        review = next((r for r in self.reviews if r.review_id == review_id), None)
        if review is None:
            raise TransitionRefused(f"unknown review {review_id!r}")
        decisions = self._review_decisions(review)
        tainted = self._resolution_conflicts(review, decisions)
        if review.resolved and not tainted:
            raise TransitionRefused(f"review {review_id} is already resolved")
        self._tick()
        problems: list[str] = []
        acceptors = {a for d in decisions for a in self._acceptors(d)}
        resolving: list[tuple[Signal, int]] = []
        # --- A complete Rule 8 update, whichever trigger accepts one --------
        rule8_gaps = []
        if not model_update.strip():
            rule8_gaps.append("Rule 8: a structural review must document a coordination "
                              "model update")
        if not elements_changed or not all(str(x).strip() for x in elements_changed):
            rule8_gaps.append("Rule 8: the update must name the registered elements of the "
                              "coordination model it changes (a re-approval of existing "
                              "practice is not an update)")
        if review.condition == E.RECURRENCE_THRESHOLD and not (level and level.strip()):
            rule8_gaps.append("Rule 8 (Scope): a recurrence review's update must name the "
                              "level at which the recurring instances are generated")
        rule8 = not rule8_gaps
        # --- What the trigger requires --------------------------------------
        if review.condition == E.OFF_ENVELOPE_OR_CONTAINMENT and \
                review.trigger == O.OFF_ENVELOPE:
            kind = "evidence-based reclassification"
            for sid in review.signal_ids:
                sig = self.signals.get(sid)
                last = sig.classification_records[-1] if sig and \
                    sig.classification_records else None
                if last is None or last.at <= review.opened_at or last.state not in (
                        O.NOMINAL, O.ELEVATED_UNCERTAINTY):
                    problems.append(f"{sid} has not been reclassified out of off-envelope "
                                    "to nominal or elevated uncertainty")
                elif not any(self.is_ees(self.evidence[e], sig, last.by, acceptors)
                             for e in last.evidence_ids if e in self.evidence):
                    problems.append(f"{sid}'s reclassification cites no External Evidence "
                                    f"Source for {last.by}'s claim")
                else:
                    resolving.append((sig, last.at))
            if not finding.strip():
                problems.append("the resolution needs a written finding")
        elif review.condition == E.OFF_ENVELOPE_OR_CONTAINMENT:
            kind = "independent steward review"
            if not finding.strip():
                problems.append("an independent steward review needs a written finding")
        elif review.condition == E.EMERGENCY_POST_EVENT:
            kind = "post-event finding"
            if not finding.strip() or elements_held is None:
                problems.append("the post-event review needs a written finding on whether "
                                "every element held (finding and elements_held)")
        elif review.condition in RULE8_ONLY_CONDITIONS:
            kind = "Rule 8 model update"
            problems += rule8_gaps
        elif no_model_change:
            kind = "independent finding: no model element requires change"
            if not finding.strip():
                problems.append("a no-change finding must state its rationale (finding)")
        else:
            kind = "Rule 8 model update"
            problems += rule8_gaps + (
                [] if rule8 else ["or resolve by an independent finding that no model element "
                                  "requires change (no_model_change=True with a finding)"])
        # --- Who may resolve it --------------------------------------------
        if not self.obligation_capable(by):
            problems.append(f"{by} has no obligation capacity (Agent Admissibility) and "
                            "cannot resolve a structural review")
        conflicts = self._independence_failures(by, decisions)
        if conflicts:
            problems.append("; ".join(conflicts) + f"; review {review_id} must be resolved "
                            "by someone else: " + NO_QUALIFYING_AGENT)
        if problems:
            why = "; ".join(problems)
            self._log("REVIEW_RESOLUTION_REFUSED", by, review=review_id, reason=why)
            raise TransitionRefused(why)
        # --- A re-resolution keeps the earlier one in the record ------------
        if review.resolved:
            review.history.append({"resolved_by": review.resolved_by,
                                   "resolved_at": review.resolved_at,
                                   "model_update": review.model_update,
                                   "finding": review.finding, "conflicts": tainted})
            self._log("RESOLUTION_SUPERSEDED", by, review=review_id,
                      previous=review.resolved_by, conflicts=tainted)
        # --- Resolve it ----------------------------------------------------
        review.resolved_by = by
        review.resolved_at = self.clock
        review.model_update = model_update
        review.elements_changed = elements_changed
        review.level = level
        review.finding = finding
        review.elements_held = elements_held
        review.no_model_change = kind.startswith("independent finding")
        if kind == "independent steward review":
            review.reviewing_steward = by
        for sig, at in resolving:
            if at not in sig.resolving_reclassifications:
                sig.resolving_reclassifications.append(at)
        # A resolved group review marks the group as reviewed: this is what
        # the irreversible gate's "recurrence groups reviewed" relies on.
        # review.scope[len("group:"):] slices off the "group:" prefix.
        if review.scope.startswith("group:"):
            self.reviewed_groups.add(review.scope[len("group:"):])
            self.group_resolutions[review.scope[len("group:"):]] = review_id
        self._log("STRUCTURAL_REVIEW_RESOLVED", by, review=review_id,
                  condition=review.condition, trigger=review.trigger, resolved_by_kind=kind,
                  model_update=model_update, elements_changed=list(elements_changed),
                  level=level, finding=finding, elements_held=elements_held,
                  reviewing_steward=review.reviewing_steward,
                  resolving_reclassifications=[(s.signal_id, t) for s, t in resolving])
        # --- Release escalated signals no other review still holds --------
        for sid in review.signal_ids:
            sig = self.signals.get(sid)
            still_held = any(not r.resolved and sid in r.signal_ids for r in self.reviews)
            if sig is not None and sig.state == S.ESCALATED and not still_held:
                self._move(sig, S.UNDER_REVIEW, by, review=review_id)

    # ###########################################################################
    # ACT VII — SOURCE STANDING (AP.7, CREDIBILITY DISCOUNTING, AP-G)
    # Is a messenger being judged on their track record, or on who they are?
    # ###########################################################################

    # ------------------------------------------------------------------
    # Source standing (AP.7 / credibility discounting / AP-G)
    # ------------------------------------------------------------------

    # =======================================================================
    # ACT VII, SCENE 1 — WERE THEY RIGHT?
    # Record whether one of an agent's signals proved correct, and who says so.
    # =======================================================================

    def record_signal_outcome(self, agent: str, correct: bool, by: str,
                              signal_id: Optional[str] = None,
                              evidence_ids: Iterable[str] = ()) -> OutcomeRecord:
        """
        Record whether one of an agent's signals later proved correct.

        Enter:   agent         the agent whose signal it was
                 correct       True if the signal's technical claim was
                               confirmed, False if refuted
                 by            the scoring agent (recorded as scored_by)
                 signal_id     the signal, if known
                 evidence_ids  evidence cited for the score (already added;
                               unknown ids are refused)
        Exit:    the OutcomeRecord, appended to self.outcomes[agent] and
                 logged as SIGNAL_OUTCOME. Whether it COUNTS is decided when
                 a discount is judged (_counted_outcomes, Scene 2).

        Spec: Layer 0, AP.7 Source Standing ("What to do"): "Track the
        correlation between a registering agent's contemporaneous
        characterization ... and that agent's actual signal accuracy,
        measured independently." Layer 4, Execution Gates, "Stable or
        improving accuracy rate": "An outcome is correct when the signal's
        technical claim — the condition it asserted, not the harm it feared
        — is confirmed by an External Evidence Source, and wrong when one
        refutes it".
        """
        # PLAYERS IN THIS SCENE
        #   rec   the new OutcomeRecord

        self._require_actor(by)
        evidence_ids = tuple(evidence_ids)
        self._check_evidence_ids(evidence_ids, "evidence cited for the outcome")
        self._tick()
        rec = OutcomeRecord(agent, correct, by, evidence_ids, signal_id, self.clock)
        # setdefault(key, []) returns the existing list for the key, or
        # stores and returns a new empty list if there is none yet.
        self.outcomes.setdefault(agent, []).append(rec)
        self._log("SIGNAL_OUTCOME", by, agent=agent, correct=correct, signal=signal_id,
                  evidence=list(evidence_ids))
        return rec

    def _counted_outcomes(self, agent: str, discounter: Optional[str] = None) -> list[bool]:
        """
        The outcomes that count, oldest first, when judging a discount.

        Enter:   agent        the agent whose record it is
                 discounter   the agent whose discount is being judged, if any
        Exit:    the `correct` values of the outcomes that count

        An outcome counts only if (a) it was scored by neither the discounting
        agent ("the agent whose discount is being judged cannot score the
        record that judges it") nor the agent whose record it is (an agent
        cannot score their own signals); and (b) it cites at least one item
        that is an External Evidence Source for the scorer's claim: an
        eligible kind, produced by none of the scorer, the discounting agent
        and the target ("confirmed by an External Evidence Source"; Layer 2,
        EES: the producer is not "the agent making the claim it is offered
        for", and a party to the dispute cannot supply the confirmation).

        IMPLEMENTATION DECISION: the target is excluded as scorer and as
        producer whether or not a discounter is named, because a record
        that judges a source must be "measured independently" of it (AP.7).
        """
        # PLAYERS IN THIS SCENE
        #   parties   the target and the discounting agent

        parties = {agent} | ({discounter} if discounter else set())
        return [o.correct for o in self.outcomes.get(agent, [])
                if o.scored_by not in parties
                and any(self.is_ees(self.evidence[e], None, o.scored_by, parties)
                        for e in o.evidence_ids if e in self.evidence)]

    # =======================================================================
    # ACT VII, SCENE 2 — THE TRACK RECORD
    # Is this agent's accuracy stable or improving?
    # =======================================================================

    def accuracy_stable_or_improving(self, agent: str,
                                     discounter: Optional[str] = None) -> bool:
        """
        The spec's definition (the project label D7), over the outcomes that
        count (_counted_outcomes).

        Enter:   agent        the agent
                 discounter   the agent whose discount is being judged; their
                              own scores are left out
        Exit:    True if the counted accuracy is stable or improving; False
                 with no counted outcome at all

        Spec (Layer 4, Execution Gates, "Stable or improving accuracy
        rate"): "With at least four scored outcomes, the rate is stable or
        improving when accuracy over the later half is no lower than over
        the earlier half (with an odd count, the later half takes the extra
        outcome) and overall accuracy is at least one half. With one to
        three, the halves are too small to compare, and only the second
        condition applies. ... An agent with no scored outcomes has no
        record against which a discount could be earned, so a discount
        against them is unsupported and counts toward the AP-G threshold."

        Worked example: [False, True, True, True] -> early half [F, T] = 0.5,
        late half [T, T] = 1.0, overall 0.75 -> True. [False, True] -> fewer
        than four, overall 0.5 -> True.
        """
        # PLAYERS IN THIS SCENE
        #   record   the counted outcomes, oldest first
        #   half     size of the earlier half
        #   early    accuracy over the earlier half
        #   late     accuracy over the later half
        #   overall  accuracy over all of them

        record = self._counted_outcomes(agent, discounter)
        if not record:
            return False
        # sum() of a list of booleans counts the Trues (True == 1, False == 0).
        overall = sum(record) / len(record)
        if len(record) < 4:
            return overall >= 0.5
        # record[:half] is the first `half` items; record[half:] the rest,
        # so with an odd count the later half has the extra one.
        half = len(record) // 2
        early = sum(record[:half]) / half
        late = sum(record[half:]) / (len(record) - half)
        return late >= early and overall >= 0.5

    # =======================================================================
    # ACT VII, SCENE 3 — EARNED OR APPLIED?
    # Is a credibility discount supported by the agent's record?
    # =======================================================================

    def discount_supported_by_record(self, agent: str,
                                     discounter: Optional[str] = None) -> bool:
        """
        AP.7: credibility judgments must be traceable to demonstrated accuracy.
        A discount is supported only by a counted accuracy record that is
        poor or declining. With no counted outcome at all, the discount
        characterizes the person rather than their track record, so it is
        not supported (D7).

        Enter:   agent        the discounted agent
                 discounter   the agent whose discount is being judged
        Exit:    True only if there is a counted record and it is not
                 stable/improving

        Spec: AP.7 ("What to do"): "Where negative characterization tracks
        accurately with genuinely poor signal quality, no void exists."
        """
        return (bool(self._counted_outcomes(agent, discounter))
                and not self.accuracy_stable_or_improving(agent, discounter))

    # =======================================================================
    # ACT VII, SCENE 4 — SHOOTING THE MESSENGER
    # Record a credibility discount; escalate it, and detect AP-G.
    # =======================================================================

    def record_credibility_discount(self, target: str, by: str, characterization: str,
                                    signal_id: Optional[str] = None) -> None:
        """
        A registering agent is characterized instead of their signal being
        evaluated. Escalates unless the discount is supported by the agent's
        record (a counted record that exists and is not stable/improving;
        outcomes scored by `by` itself do not count), so a discount against
        an agent with no counted record escalates too; repeated
        unsupported discounting at threshold is AP-G, a Layer 0 void for
        that sender's signals.

        Enter:   target             the agent being characterized
                 by                 the agent doing it (as recorded)
                 characterization   the words used, e.g. "difficult"
                 signal_id          the signal involved, if any
        Exit:    None. Always logs CREDIBILITY_DISCOUNT and counts it. If the
                 discount is not supported by the record, opens (or joins) a
                 CREDIBILITY_DISCOUNTING review on "agent:<target>"; at the
                 D6 threshold the agent is also put under AP-G and a
                 SENDER_DISCOUNT_RECURRENCE review opens.

        Spec: Layer 2, Credibility Discounting: it "operates not on the
        signal ... but on the standing of the agent who registered it",
        relocating the question "from 'is this true' to 'is this person a
        problem'". It is not a closure type. Escalation conditions (Layer 2,
        Escalation Conditions): discounting against an agent whose accuracy
        is "stable or improving", and its recurrence (AP-G). AP-G (Layer 0,
        The Eight Void Types, AP-G: Sender Discount; Key Definitions, Sender
        Discount (AP-G)) makes evaluation of that agent's future signals "not
        meaningful until the channel is repaired"; architecture_check()
        reports it as a void.

        Counting: every discount is counted in `discounts` and logged, but
        only unsupported ones count toward AP-G, in `unsupported_discounts`
        ("Discounts earned by a declining accuracy record do not count
        toward the threshold", Layer 2, Credibility Discounting, "AP-G
        threshold"). The spec states the threshold as three; here it is
        Settings.sender_discount_threshold (D6, default 3), and the test is
        "unsupported count >= threshold". AP-G is entered once per agent;
        nothing in this file removes an agent from it.
        """
        # PLAYERS IN THIS SCENE
        #   affected   [signal_id] if a signal was named, else []

        self._require_actor(by)
        self._tick()
        # dict.get(key, 0) + 1: start from 0 if the agent has no count yet.
        self.discounts[target] = self.discounts.get(target, 0) + 1
        self._log("CREDIBILITY_DISCOUNT", by, target=target,
                  characterization=characterization, signal=signal_id,
                  count=self.discounts[target])
        # --- Earned by a poor record? Then no void, nothing more to do -----
        if self.discount_supported_by_record(target, by):
            return
        # --- Escalation: discount despite stable/improving accuracy -------
        self.unsupported_discounts[target] = self.unsupported_discounts.get(target, 0) + 1
        affected = [signal_id] if signal_id else []
        self._escalate(E.CREDIBILITY_DISCOUNTING, f"agent:{target}",
                       f"{target} discounted ({characterization!r}) despite stable or "
                       f"improving signal accuracy", affected, by)
        # --- AP-G: recurrence at threshold ---------------------------------
        if (self.unsupported_discounts[target] >= self.settings.sender_discount_threshold
                and target not in self.sender_discount_void):
            self.sender_discount_void.add(target)
            self._escalate(E.SENDER_DISCOUNT_RECURRENCE, f"agent:{target}",
                           f"AP-G Sender Discount: {self.unsupported_discounts[target]} "
                           f"unsupported discounts against {target}", [], by)

    # ###########################################################################
    # ACT VIII — DECISIONS, COHERENCE AND EXECUTION GATES
    # The interlock: may this decision execute, and on what record?
    # ###########################################################################

    # ------------------------------------------------------------------
    # Decisions, coherence and execution gates
    # ------------------------------------------------------------------

    # =======================================================================
    # ACT VIII, SCENE 1 — A DECISION IS TABLED
    # Create a decision node over a set of signals.
    # =======================================================================

    def register_decision(self, decision_id: str, description: str,
                          execution_class: ExecutionClass, signal_ids: Iterable[str],
                          by: str, reversal_path: Optional[str] = None,
                          reversal_evidence_ids: Iterable[str] = (),
                          scope: Optional[str] = None) -> Decision:
        """
        Register an execution-class decision node.

        Enter:   decision_id       the decision's id
                 description       what is being decided
                 execution_class   irreversible, elevated or routine
                                   (Layer 4, Execution Gates)
                 signal_ids        the signals the decision depends on
                 by                the registering agent
                 reversal_path     how its effects could be undone (needed for
                                   a declared class below irreversible to apply)
                 reversal_evidence_ids  evidence that the path was tested
                 scope             the authority scope (Scene 2b); default:
                                   the decision id. With authority
                                   enforced, a scope other than the default
                                   needs `by` to be a root or to hold
                                   AUTHORIZE over it delegably (else
                                   SCOPE_REFUSED and TransitionRefused);
                                   see also assign_scope()
        Exit:    the new Decision (not yet accepted or executed); logs
                 DECISION_REGISTERED with both the declared and the applied
                 class. A used decision id or an unknown evidence id is
                 refused and nothing is registered.

        The declared class is stored as given. Whether it APPLIES is decided
        when needed by effective_class(): "Every execution-class decision is
        irreversible unless shown otherwise" (Execution Class Assignment).

        An id already in use is refused, so an accepted decision cannot be
        silently replaced. Signal ids are not checked here; unknown ones are
        caught at the gate as "signal registration incomplete". The
        authority-count check runs at once, in case the signals already
        carry authority closures.

        IMPLEMENTATION DECISION (registration as relabeling): Execution
        Class Assignment says "registering the same commitment under a new
        decision identifier does not avoid" the downgrade-after-block
        escalation. So a new decision LINKED to a blocked one (_linked) and
        registered at a lower declared or applied class than that decision
        escalates EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK on itself at once,
        as a lowering of an existing decision would.
        """
        # PLAYERS IN THIS SCENE
        #   d                       the new Decision
        #   reversal_evidence_ids   the offered ids, frozen into a tuple

        self._require_actor(by)
        if decision_id in self.decisions:
            raise TransitionRefused(f"decision {decision_id!r} already registered")
        # --- Who may put a decision in a scope (Scene 2b) -----------------
        # A scope decides whose authority applies, so choosing it is itself
        # an act of authority: otherwise anyone could label a production
        # launch "sandbox" and approve it with sandbox powers.
        if scope is not None and scope != decision_id:
            self._require_scope_owner(scope, by, decision_id)
        reversal_evidence_ids = tuple(reversal_evidence_ids)
        self._check_evidence_ids(reversal_evidence_ids, "reversal evidence")
        self._tick()
        d = Decision(decision_id, description, execution_class, list(signal_ids),
                     class_setters=(by,), reversal_path=reversal_path,
                     reversal_evidence=reversal_evidence_ids, scope=scope or decision_id)
        self.decisions[decision_id] = d
        self._log("DECISION_REGISTERED", by, decision=decision_id, scope=d.scope,
                  execution_class=execution_class, signals=d.signal_ids,
                  reversal_path=reversal_path, reversal_evidence=list(reversal_evidence_ids),
                  applied_class=self._applied_class(d))
        self._check_authority_count(d, by)
        # --- Relabeling under a new identifier (Execution Class Assignment)
        # "registering the same commitment under a new decision identifier
        # does not avoid it": a new decision linked to a blocked one, at a
        # lower class than that one, is a lowering after a block.
        self._check_below_blocked(d, [o for o in self.decisions.values()
                                      if self._linked(d, o)], by, "registered")
        return d

    # =======================================================================
    # ACT VIII, SCENE 1b — IS IT REALLY REVERSIBLE?
    # Execution Class Assignment: irreversible by default; a lower class
    # needs a tested reversal path; relabeling after a refusal escalates.
    # =======================================================================

    def _check_evidence_ids(self, evidence_ids: tuple, what: str) -> None:
        """
        Refuse unknown evidence ids before anything changes.

        Enter:   evidence_ids   ids to check
                 what           how to name them in the refusal
        Exit:    None; raises TransitionRefused naming the unknown ids
        """
        # PLAYERS IN THIS SCENE
        #   unknown   the ids not in the evidence record

        unknown = [e for e in evidence_ids if e not in self.evidence]
        if unknown:
            raise TransitionRefused(f"unknown {what}: {unknown}")

    def _reversal_supported(self, d: Decision) -> bool:
        """
        Is the decision's reversal path registered and shown to be tested?

        Enter:   d   the decision
        Exit:    True if it has a reversal path and at least one item of its
                 reversal evidence is an External Evidence Source for it

        Spec: Layer 4, Execution Class Assignment: "supported by at least one
        External Evidence Source (Layer 2) showing that the path has been
        tested. The claim is the registering or reclassifying agent's, so
        neither that agent, nor the agent accepting the decision, nor a
        process under evaluation in its loops may produce the evidence. An
        untested reversal path counts as absent." Assessed when needed, so a
        later acceptance by the evidence's producer withdraws the support.
        """
        # PLAYERS IN THIS SCENE
        #   excluded   producers whose evidence cannot count

        if not d.reversal_path:
            return False
        excluded = (set(d.class_setters) | {d.accepted_by}
                    | {s.evaluated_process for s in self._decision_signals(d)})
        return any(self.evidence[e].kind in EES_ELIGIBLE_KINDS
                   and self.evidence[e].produced_by not in excluded
                   for e in d.reversal_evidence)

    def _applied_class(self, d: Decision) -> ExecutionClass:
        """
        The class the gate applies: the declared one if it is irreversible
        or its reversal path is supported, otherwise irreversible.

        Enter:   d   the decision
        Exit:    an ExecutionClass
        """
        if d.execution_class == ExecutionClass.IRREVERSIBLE or self._reversal_supported(d):
            return d.execution_class
        return ExecutionClass.IRREVERSIBLE

    def effective_class(self, decision_id: str) -> ExecutionClass:
        """
        Public view of _applied_class().

        Enter:   decision_id   the decision
        Exit:    the class the gate would apply now
        """
        return self._applied_class(self._decision(decision_id))

    def reclassify_decision(self, decision_id: str, execution_class: ExecutionClass,
                            by: str, rationale: str, reversal_path: Optional[str] = None,
                            reversal_evidence_ids: Optional[Iterable[str]] = None) -> None:
        """
        Change a decision's declared execution class, never silently.

        Enter:   decision_id      the decision
                 execution_class  the new declared class
                 by               the reclassifying agent
                 rationale        required
                 reversal_path, reversal_evidence_ids
                                  replace the stored ones if given; kept if
                                  left out (None)
        Exit:    None. Refused (TransitionRefused) with no rationale, for an
                 unknown or executed decision, or for unknown evidence ids,
                 before anything changes. Otherwise records `by` among the
                 decision's class setters and logs
                 DECISION_RECLASSIFIED. A lowering after a blocked request
                 escalates.

        Spec: Layer 4, Execution Class Assignment: "every change is logged
        with the agent, rationale, and any reversal evidence. Raising the
        class needs no evidence. Lowering it needs the same reversal-path
        support as registering at the lower class, and a lowering made
        after an execution request for the same decision was blocked
        escalates to structural review automatically ... A lowering is any
        change that lowers either the declared class or the class the gate
        would apply."

        A lowering without support is accepted, not refused: like a
        registration at that class, it is simply gated as irreversible.

        Linked decisions (same section): "two decisions are linked when they
        name a failure mode in common and share a signal, and a lowering
        made after any linked decision was blocked escalates the same way".
        _blocked_linked() finds the decision itself if it was blocked, and
        every blocked decision linked to it.
        """
        # PLAYERS IN THIS SCENE
        #   d                         the decision
        #   old_declared, old_applied its classes before the change
        #   new_applied               the class the gate applies after it (for
        #                             the log; the lowering test is
        #                             _check_lowering)

        self._require_actor(by)
        if not rationale:
            raise TransitionRefused("reclassification must be logged with a rationale")
        d = self._decision(decision_id)
        if d.executed:
            raise TransitionRefused(f"decision {decision_id} has already executed")
        if reversal_evidence_ids is not None:
            reversal_evidence_ids = tuple(reversal_evidence_ids)
            self._check_evidence_ids(reversal_evidence_ids, "reversal evidence")
        self._tick()
        old_declared, old_applied = d.execution_class, self._applied_class(d)
        # --- Apply the change ----------------------------------------------
        d.execution_class = execution_class
        if by not in d.class_setters:
            d.class_setters = d.class_setters + (by,)
        if reversal_path is not None:
            d.reversal_path = reversal_path
        if reversal_evidence_ids is not None:
            d.reversal_evidence = reversal_evidence_ids
        new_applied = self._applied_class(d)
        self._log("DECISION_RECLASSIFIED", by, decision=decision_id,
                  **{"from": old_declared}, to=execution_class, rationale=rationale,
                  reversal_path=d.reversal_path, evidence=list(d.reversal_evidence),
                  applied_from=old_applied, applied_to=new_applied)
        # --- Escalation: relabeling after a refusal ------------------------
        self._check_lowering(d, old_declared, old_applied, by, "reclassified")

    def _check_lowering(self, d: Decision, old_declared: ExecutionClass,
                        old_applied: ExecutionClass, by: str, cause: str) -> None:
        """
        Escalate a lowering of either class made after a block on the
        decision or on a linked one, whatever operation made it.

        Enter:   d              the decision, after the change
                 old_declared   its declared class before the change
                 old_applied    the class the gate applied before it
                 by             the agent whose operation made the change
                 cause          what changed it, for the detail ("reclassified",
                                "re-accepted")
        Exit:    None; may open EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK on
                 "decision:<id>"

        Spec (Layer 4, Execution Class Assignment): "A lowering is any
        change that lowers either the declared class or the class the gate
        would apply". A re-acceptance can lower the applied class: reversal
        evidence the old acceptor produced counts again once someone else
        accepts. So reclassify_decision() and accept_decision() both call
        this.
        """
        # PLAYERS IN THIS SCENE
        #   new_applied   the class the gate applies now
        #   lowered       True if either class went down
        #   blocked       it, and decisions linked to it, that were ever blocked

        new_applied = self._applied_class(d)
        lowered = (CLASS_RANK[d.execution_class] < CLASS_RANK[old_declared]
                   or CLASS_RANK[new_applied] < CLASS_RANK[old_applied])
        blocked = [o.decision_id for o in self._blocked_linked(d)]
        if lowered and blocked:
            self._escalate(E.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK, f"decision:{d.decision_id}",
                           f"{d.decision_id} {cause}: lowered from {old_declared.value}/"
                           f"{old_applied.value} to {d.execution_class.value}/"
                           f"{new_applied.value} after a blocked execution request on "
                           f"{blocked}", [], by)

    def _check_below_blocked(self, d: Decision, others: list[Decision], by: str,
                             cause: str) -> None:
        """
        Escalate a decision that sits below a blocked decision it is linked to.

        Enter:   d        the decision that may be the relabeled commitment
                 others   the decisions to compare it with (those linked to
                          it, or newly linked by a link_signal())
                 by       the agent whose operation made the link
                 cause    "registered" or "linked", for the detail
        Exit:    None; may open EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK on
                 "decision:<id of d>"

        Spec (Layer 4, Execution Class Assignment): "a lowering made after
        any linked decision was blocked escalates the same way; registering
        the same commitment under a new decision identifier does not avoid
        it." Registration and linking can each make d the same commitment
        at a lower class than a blocked decision, without any reclassify.
        """
        # PLAYERS IN THIS SCENE
        #   lower_than   blocked decisions in `others` that d sits below

        lower_than = [o.decision_id for o in others
                      if o.ever_blocked and self._linked(d, o)
                      and (CLASS_RANK[self._applied_class(d)] < CLASS_RANK[self._applied_class(o)]
                           or CLASS_RANK[d.execution_class] < CLASS_RANK[o.execution_class])]
        if lower_than:
            self._escalate(E.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK, f"decision:{d.decision_id}",
                           f"{d.decision_id} {cause} at {d.execution_class.value}/"
                           f"{self._applied_class(d).value}, below linked decision(s) "
                           f"{lower_than} whose execution request was blocked", [], by)

    def _linked(self, a: Decision, b: Decision) -> bool:
        """
        Are two different decisions linked, for the relabeling test?

        Enter:   a, b   two decisions
        Exit:    True if they are different, name a failure mode in common
                 (Signal.mode of their registered signals), and share a
                 signal id

        Spec: Layer 4, Execution Class Assignment: "two decisions are
        linked when they name a failure mode in common and share a signal".
        """
        # PLAYERS IN THIS SCENE
        #   modes_a, modes_b   the failure modes each decision's signals name

        if a.decision_id == b.decision_id:
            return False
        modes_a = {s.mode for s in self._decision_signals(a)}
        modes_b = {s.mode for s in self._decision_signals(b)}
        return bool(modes_a & modes_b) and bool(set(a.signal_ids) & set(b.signal_ids))

    def _blocked_linked(self, d: Decision) -> list[Decision]:
        """
        The decision itself if it was ever blocked, and every linked
        decision that was.

        Enter:   d   a decision
        Exit:    the ever-blocked decisions among d and those linked to it
        """
        return [o for o in self.decisions.values()
                if o.ever_blocked and (o is d or self._linked(d, o))]

    # =======================================================================
    # ACT VIII, SCENE 2 — ANOTHER SIGNAL JOINS THE DECISION
    # Attach a signal to an existing decision.
    # =======================================================================

    def link_signal(self, decision_id: str, signal_id: str, by: str) -> None:
        """
        Make a decision depend on one more signal.

        Enter:   decision_id   an existing decision
                 signal_id     an existing signal
                 by            the linking agent
        Exit:    None; the signal is added (once), the authority count
                 re-checked, and the relabeling test run for every link the
                 new signal creates: if it makes this decision linked to a
                 blocked one while applying a lower class, this decision
                 escalates; if it makes a lower decision linked to this
                 one, blocked, that decision escalates

        Spec (Layer 4, Execution Class Assignment): two decisions are
        linked "when they name a failure mode in common and share a
        signal". Linking a signal after registration is one way to become
        linked, so it gets the same test as registration (_check_below_blocked).
        Only links the new signal creates are tested, so linking again
        after the review was resolved does not re-open it.
        """
        # PLAYERS IN THIS SCENE
        #   d        the decision
        #   before   ids of the decisions linked to it before the link
        #   new      decisions linked to it only since the link
        #   o        each of them

        self._require_actor(by)
        # Called only for its check: refuses if the signal is unknown.
        self._signal(signal_id)
        d = self._decision(decision_id)
        self._tick()
        before = {o.decision_id for o in self.decisions.values() if self._linked(d, o)}
        if signal_id not in d.signal_ids:
            d.signal_ids.append(signal_id)
        self._log("SIGNAL_LINKED", by, decision=decision_id, signal=signal_id)
        self._check_authority_count(d, by)
        # --- Relabeling through a new link ---------------------------------
        new = [o for o in self.decisions.values()
               if self._linked(d, o) and o.decision_id not in before]
        self._check_below_blocked(d, new, by, "linked")
        for o in new:
            self._check_below_blocked(o, [d], by, "linked")

    # =======================================================================
    # ACT VIII, SCENE 2b — WHO MAY RECOMMEND, AUTHORIZE, EXECUTE
    # Authority is granted, never inferred: not from a handoff, not from a
    # recommendation, not from being the next agent in a pipeline.
    # =======================================================================

    @property
    def authority_enforced(self) -> bool:
        """
        Are powers checked? Only once Settings.authority_roots names someone.

        Enter:   (none)
        Exit:    True if authority roots are set
        """
        return bool(self.settings.authority_roots)

    def _grant_valid(self, g: Grant, now: float) -> bool:
        """
        Is this grant in force: not revoked, not expired, and every grant
        above it in its chain in force too?

        Enter:   g     the Grant
                 now   the wall-clock time to judge expiry at
        Exit:    True if the whole chain from a root down to g holds
        """
        # PLAYERS IN THIS SCENE
        #   parent   the grant g was derived from

        if g.grant_id in self.revoked:
            return False
        if g.expires_at is not None and now >= g.expires_at:
            return False
        if g.parent is None:
            return g.granted_by in self.settings.authority_roots
        parent = self._grant(g.parent)
        return self._grant_valid(parent, now)

    def _grant(self, grant_id: str) -> Grant:
        """
        Look a grant up by id.

        Enter:   grant_id   "G1", ...
        Exit:    the Grant; raises TransitionRefused if unknown
        """
        for g in self.grants:
            if g.grant_id == grant_id:
                return g
        raise TransitionRefused(f"unknown grant {grant_id!r}")

    def _backing(self, agent: str, power: Power, scope: str, delegable: bool = False
                 ) -> Optional[Grant]:
        """
        The grant in force that gives this agent this power over this scope.

        Enter:   agent, power, scope   as in holds()
                 delegable             also require the right to grant it on
        Exit:    the first such Grant, or None
        """
        # PLAYERS IN THIS SCENE
        #   now   the wall clock, read once

        now = self.now()
        return next((g for g in self.grants
                     if g.grantee == agent and g.power == Power(power)
                     and g.scope in (scope, "*") and (g.delegable or not delegable)
                     and self._grant_valid(g, now)), None)

    def holds(self, agent: str, power: Power, scope: str, delegable: bool = False) -> bool:
        """
        Does this agent hold this power over this scope, right now?

        Enter:   agent       the agent
                 power       a Power
                 scope       a decision scope
                 delegable   also require the right to grant it on
        Exit:    True if the agent is a root, or holds a grant in force
                 (scope equal or "*"; delegable if asked; not revoked or
                 expired, and nor is any grant above it). Always True when
                 authority is not enforced.

        IMPLEMENTATION DECISION: Rule 4 says a single agent must "explicitly
        accept authorization"; the draft does not say who may. Here the
        answer is: an authority root, or whoever a root's chain of grants
        in force reaches. A recommendation is never an authorization: the
        powers are separate, and holding one implies no other.
        """
        if not self.authority_enforced or agent in self.settings.authority_roots:
            return True
        return self._backing(agent, power, scope, delegable) is not None

    def _refuse_power(self, event: str, by: str, power: Power, scope: str, what: str,
                      **payload) -> None:
        """
        Log a refusal for want of a power, then raise.

        Enter:   event     the event name to log (e.g. ACCEPTANCE_REFUSED)
                 by        the agent who lacked it
                 power     the Power needed
                 scope     the scope
                 what      what was attempted, for the message
                 payload   extra details for the log
        Exit:    never returns; raises TransitionRefused
        """
        reason = (f"{by} does not hold {Power(power).value} over {scope!r}: "
                  f"{what} refused (authority is granted, never inferred)")
        self._tick()
        self._log(event, by, power=Power(power), scope=scope, reason=reason, **payload)
        raise TransitionRefused(reason)

    def grant(self, grantee: str, power: Power, scope: str, by: str,
              delegable: bool = False, expires_at: Optional[float] = None) -> Grant:
        """
        Grant a power. Only someone who holds it, delegably, can grant it,
        and never for longer than they hold it.

        Enter:   grantee      the agent receiving the power
                 power        a Power
                 scope        the scope it covers ("*" for all)
                 by           the granting agent
                 delegable    may the grantee grant it on?
                 expires_at   when it lapses (wall clock), or None
        Exit:    the Grant, linked to the grant that backs `by` (its
                 parent); logs AUTHORITY_GRANTED. Refused, with
                 GRANT_REFUSED logged and TransitionRefused raised, if `by`
                 does not hold the power delegably over that scope (for "*":
                 a root or a "*" grant), or if the new grant would outlive
                 its parent. Nothing is granted then.

        Delegation can only pass on what the delegator holds: no grant can
        exceed its grantor's power, scope, right to delegate or lifetime.
        And because a grant is valid only while its parent is, revoking or
        expiring any link voids everything below it.
        """
        # PLAYERS IN THIS SCENE
        #   parent   the grant in force that lets `by` grant this (None: root)
        #   g        the new Grant

        self._require_actor(by)
        self._require_actor(grantee)
        power = Power(power)
        if not self.holds(by, power, scope, delegable=True):
            self._refuse_power("GRANT_REFUSED", by, power, scope, f"granting it to {grantee}",
                               grantee=grantee, delegable=delegable, expires_at=expires_at)
        root = not self.authority_enforced or by in self.settings.authority_roots
        parent = None if root else self._backing(by, power, scope, delegable=True)
        if parent is not None and parent.expires_at is not None and (
                expires_at is None or expires_at > parent.expires_at):
            reason = (f"{by}'s authority ({parent.grant_id}) lapses at {parent.expires_at}; "
                      f"a grant to {grantee} cannot outlive it (requested: "
                      f"{'no expiry' if expires_at is None else expires_at})")
            self._tick()
            self._log("GRANT_REFUSED", by, power=power, scope=scope, reason=reason,
                      grantee=grantee, delegable=delegable, expires_at=expires_at)
            raise TransitionRefused(reason)
        self._tick()
        g = Grant(f"G{len(self.grants) + 1}", grantee, power, scope, delegable, by,
                  parent.grant_id if parent else None, expires_at, self.clock)
        self.grants.append(g)
        self._log("AUTHORITY_GRANTED", by, grant=g.grant_id, grantee=grantee, power=power,
                  scope=scope, delegable=delegable, parent=g.parent, expires_at=expires_at)
        return g

    def revoke(self, grant_id: str, by: str, reason: str) -> list[str]:
        """
        Withdraw a grant, and with it every grant derived from it.

        Enter:   grant_id   the grant
                 by         its grantor, any grantor above it in its chain,
                            or a root
                 reason     why
        Exit:    the ids of the grants this voids (it and its descendants);
                 logs AUTHORITY_REVOKED. Anyone else is refused
                 (REVOCATION_REFUSED, TransitionRefused).

        Takes effect for every later check: an acceptance made under the
        revoked authority no longer lets the decision execute (see
        request_execution).
        """
        # PLAYERS IN THIS SCENE
        #   g         the grant
        #   chain     grantors from g up to its root
        #   up        walking up the chain
        #   voided    g and every grant whose chain passes through it

        self._require_actor(by)
        g = self._grant(grant_id)
        chain, up = [g.granted_by], g
        while up.parent is not None:
            up = self._grant(up.parent)
            chain.append(up.granted_by)
        if by not in chain and by not in self.settings.authority_roots:
            why = f"{by} is not in the chain of grantors for {grant_id} ({chain})"
            self._tick()
            self._log("REVOCATION_REFUSED", by, grant=grant_id, reason=why)
            raise TransitionRefused(why)
        voided = [x.grant_id for x in self.grants if self._descends(x, grant_id)]
        self._tick()
        self.revoked.setdefault(grant_id, (by, self.clock))
        self._log("AUTHORITY_REVOKED", by, grant=grant_id, reason=reason, voids=voided)
        return voided

    def _descends(self, g: Grant, ancestor_id: str) -> bool:
        """
        Is ancestor_id this grant, or above it in its chain?

        Enter:   g             a Grant
                 ancestor_id   a grant id
        Exit:    True or False
        """
        while True:
            if g.grant_id == ancestor_id:
                return True
            if g.parent is None:
                return False
            g = self._grant(g.parent)

    def _require_scope_owner(self, scope: str, by: str, decision_id: str) -> None:
        """
        Refuse unless `by` may put decisions in this scope: a root, or a
        holder of delegable AUTHORIZE over it.

        Enter:   scope, by, decision_id
        Exit:    None; or logs SCOPE_REFUSED and raises TransitionRefused
        """
        if not self.holds(by, Power.AUTHORIZE, scope, delegable=True):
            self._refuse_power("SCOPE_REFUSED", by, Power.AUTHORIZE, scope,
                               f"putting {decision_id} in scope {scope!r}", decision=decision_id)

    def assign_scope(self, decision_id: str, scope: str, by: str) -> None:
        """
        Put a decision in an authority scope.

        Enter:   decision_id   the decision (not yet accepted)
                 scope         the scope
                 by            a root, or a holder of delegable AUTHORIZE over
                               the scope
        Exit:    None; logs SCOPE_ASSIGNED. Refused once the decision is
                 accepted (the acceptance was given for its old scope).
        """
        self._require_actor(by)
        d = self._decision(decision_id)
        if d.accepted_by:
            raise TransitionRefused(f"{decision_id} is already accepted; its scope is fixed")
        self._require_scope_owner(scope, by, decision_id)
        self._tick()
        previous, d.scope = d.scope, scope
        self._log("SCOPE_ASSIGNED", by, decision=decision_id, scope=scope, previous=previous)

    def recommend(self, decision_id: str, by: str, rationale: str) -> None:
        """
        Record a recommendation. It changes no gate and authorizes nothing.

        Enter:   decision_id   the decision
                 by            the recommending agent
                 rationale     why
        Exit:    None; logs DECISION_RECOMMENDED. Refused (and logged as
                 RECOMMENDATION_REFUSED) if authority is enforced and `by`
                 does not hold RECOMMEND over the decision's scope.
        """
        self._require_actor(by)
        d = self._decision(decision_id)
        if not self.holds(by, Power.RECOMMEND, d.scope):
            self._refuse_power("RECOMMENDATION_REFUSED", by, Power.RECOMMEND, d.scope,
                               "recommending", decision=decision_id)
        self._tick()
        self._log("DECISION_RECOMMENDED", by, decision=decision_id, rationale=rationale)

    # =======================================================================
    # ACT VIII, SCENE 3 — SOMEONE MUST OWN IT
    # Rule 4: a single named agent accepts the decision.
    # =======================================================================

    def accept_decision(self, decision_id: str, by: str, rationale: str,
                        evidence_ids: Iterable[str] = (), risk_claim: str = "",
                        known: str = "", assumed: str = "", uncertain: str = "") -> None:
        """
        Rule 4: a single named agent accepts authorization, risk and rationale.

        Enter:   decision_id   the decision
                 by            the accepting agent
                 rationale     required; the rationale they take on
                 evidence_ids  evidence cited in the acceptance (already
                               added): the External Evidence Source for the
                               principal risk claim must be among it
                 risk_claim    the principal risk claim: "what must be true
                               for the decision to be safe to execute"
                 known, assumed, uncertain
                               the Rule 3 registration: "what is known, what
                               is assumed, and what remains genuinely
                               uncertain"
        Exit:    None; the decision records `by`, the rationale, the cited
                 evidence, the risk claim and the Rule 3 registration; an
                 unknown evidence id is refused and nothing changes. With
                 authority enforced, an agent without AUTHORIZE over the
                 decision's scope is refused (ACCEPTANCE_REFUSED) and nothing
                 changes; so is an agent without obligation capacity
                 (ACCEPTANCE_REFUSED), whatever the authority setting.

        Spec: Rule 4, Decisions Have Living Ownership: "Before any execution-class decision,
        a single agent must explicitly accept authorization, risk
        acceptance, and rationale documentation as their responsibility."
        Why: "Diffused ownership is functionally equivalent to no
        ownership" (Challenger was "owned by no one cleanly"). Layer 0,
        Agent Admissibility: "Stewardship (AP.1) requires obligation
        capacity. So do Rule 4 acceptance and open-loop authorization".

        The risk claim, its evidence and the Rule 3 registration are not
        required to accept: the irreversible gate checks them ("At least one
        External Evidence Source for the principal risk claim";
        "Classification stabilized", second condition), so an acceptance
        without them is recorded and simply fails that gate.

        The decision holds one accepting agent; a later acceptance replaces
        the earlier one, with everything it records (both are in the audit
        trail). Every acceptor is also kept in `acceptors`: none of them may
        later override the decision, give an off-scene Emergency
        Justification for it, resolve a review holding it or attest its risk
        evidence, so a re-acceptance by a subordinate cannot hand the gate
        back to the agent it was addressed to (Layer 4, Overrides,
        "Separation of acceptance and override"). A re-acceptance voids any
        risk-evidence attestation, which was given for the earlier
        acceptance and its evidence. And because the applied class depends
        on who accepted (reversal evidence may not come from the acceptor),
        a re-acceptance that lowers it after a block escalates
        (_check_lowering).
        """
        # PLAYERS IN THIS SCENE
        #   d              the decision
        #   evidence_ids   the cited ids, frozen into a tuple
        #   unknown        any of them not in the evidence record
        #   reason         the refusal text for want of obligation capacity
        #   old_declared, old_applied   its classes before the acceptance
        #   voided         the attestation this acceptance voids, if any
        #   backing        the grant that backs the acceptance, if any

        self._require_actor(by)
        if not rationale:
            raise TransitionRefused("Rule 4: acceptance requires rationale documentation")
        d = self._decision(decision_id)
        # --- Only an agent with obligation capacity can accept -------------
        # An instrument, a model or a role with no successor can be a
        # signal source, never the owner of a decision.
        if not self.obligation_capable(by):
            reason = (f"Rule 4: {by} has no obligation capacity (Agent Admissibility: "
                      f"{self.agent_kinds.get(by, AgentKind.PERSON).value} without it) and "
                      "cannot accept a decision")
            self._tick()
            self._log("ACCEPTANCE_REFUSED", by, decision=decision_id, reason=reason,
                      rationale=rationale)
            raise TransitionRefused(reason)
        # --- Only a holder of AUTHORIZE can accept (Scene 2b) --------------
        # A recommendation, a handoff, or a request to execute is not an
        # authorization, whoever it came from.
        if not self.holds(by, Power.AUTHORIZE, d.scope):
            self._refuse_power("ACCEPTANCE_REFUSED", by, Power.AUTHORIZE, d.scope,
                               "Rule 4 acceptance", decision=decision_id, rationale=rationale)
        evidence_ids = tuple(evidence_ids)
        unknown = [e for e in evidence_ids if e not in self.evidence]
        if unknown:
            raise TransitionRefused(f"unknown evidence cited in acceptance: {unknown}")
        self._tick()
        old_declared, old_applied = d.execution_class, self._applied_class(d)
        # `a, b, c = x, y, z` assigns all three fields in one line.
        d.accepted_by, d.acceptance_rationale, d.acceptance_evidence = (
            by, rationale, evidence_ids)
        if by not in d.acceptors:
            d.acceptors = d.acceptors + (by,)
        voided = d.risk_attestation
        d.risk_attestation = None
        d.risk_claim = risk_claim
        d.rule3_known, d.rule3_assumed, d.rule3_uncertain = known, assumed, uncertain
        # The grant that backs this acceptance; it must stay in force.
        backing = (self._backing(by, Power.AUTHORIZE, d.scope)
                   if self.authority_enforced and by not in self.settings.authority_roots
                   else None)
        d.acceptance_grant = backing.grant_id if backing else None
        self._log("DECISION_ACCEPTED", by, decision=decision_id, rationale=rationale,
                  evidence=list(evidence_ids), grant=d.acceptance_grant,
                  risk_claim=risk_claim, known=known, assumed=assumed, uncertain=uncertain,
                  acceptors=list(d.acceptors),
                  attestation_voided=voided.by if voided else None)
        self._check_lowering(d, old_declared, old_applied, by, "re-accepted")

    # =======================================================================
    # ACT VIII, SCENE 3b — A SECOND PAIR OF EYES
    # Attest that the acceptance's evidence bears on the risk claim.
    # =======================================================================

    def _attester_failures(self, d: Decision, by: str) -> list[str]:
        """
        Why `by` may not attest (or no longer validly attests) the
        decision's risk evidence.

        Enter:   d    the decision
                 by   the attesting agent
        Exit:    one reason per unmet condition (empty: may attest)

        Spec (Layer 4, Execution Gates, "At least one External Evidence
        Source for the principal risk claim"): attested "by an agent other
        than the acceptor who meets the independence conditions under
        Overrides": not an agent who ever accepted the decision, not a
        requester, not in the reporting line of any acceptor; with
        obligation capacity; and, with authority enforced, holding OVERRIDE
        over the decision's scope (the independence conditions include
        "the authority to override is registered separately").
        """
        # PLAYERS IN THIS SCENE
        #   reasons   the unmet conditions

        reasons = self._independence_failures(by, [d])
        if not self.obligation_capable(by):
            reasons.append(f"{by} has no obligation capacity (Agent Admissibility)")
        if not self.holds(by, Power.OVERRIDE, d.scope):
            reasons.append(f"{by} does not hold override over {d.scope!r} "
                           "(authority is granted, never inferred)")
        return reasons

    def attest_risk_evidence(self, decision_id: str, by: str, rationale: str) -> RiskAttestation:
        """
        Attest that the evidence cited in the decision's Rule 4 acceptance
        bears on its principal risk claim.

        Enter:   decision_id   an accepted decision naming a risk claim
                 by            the attesting agent (see _attester_failures)
                 rationale     required; why the evidence bears on the claim
        Exit:    the RiskAttestation, stored on the decision and logged as
                 RISK_EVIDENCE_ATTESTED. Refused (RISK_ATTESTATION_REFUSED
                 logged, TransitionRefused) without a rationale, before an
                 acceptance with a risk claim, or when `by` is not
                 independent.

        The irreversible gate requires a valid attestation and re-checks the
        attester's independence when it runs (_attestation_failures), since
        reporting lines, requests and acceptances can change afterward. A
        new acceptance voids it.
        """
        # PLAYERS IN THIS SCENE
        #   d         the decision
        #   problems  why the attestation is refused
        #   att       the new RiskAttestation

        self._require_actor(by)
        d = self._decision(decision_id)
        self._tick()
        problems = []
        if not rationale or not rationale.strip():
            problems.append("an attestation must state its rationale")
        if not d.accepted_by or not d.risk_claim.strip():
            problems.append(f"{decision_id} has no Rule 4 acceptance naming a principal risk "
                            "claim to attest")
        problems += self._attester_failures(d, by)
        if problems:
            why = "; ".join(problems)
            self._log("RISK_ATTESTATION_REFUSED", by, decision=decision_id, reason=why)
            raise TransitionRefused(why)
        att = RiskAttestation(by, rationale, self.clock, d.accepted_by, d.acceptance_evidence)
        d.risk_attestation = att
        self._log("RISK_EVIDENCE_ATTESTED", by, decision=decision_id, rationale=rationale,
                  acceptor=d.accepted_by, evidence=list(d.acceptance_evidence),
                  risk_claim=d.risk_claim)
        return att

    def _attestation_failures(self, d: Decision) -> list[str]:
        """
        Is the decision's risk-evidence attestation present and still valid?

        Enter:   d   the decision
        Exit:    reasons it is not (empty: valid)

        Valid means: given for the current acceptance (same acceptor and
        evidence; a re-acceptance already voids it), and the attester still
        meets every condition of _attester_failures, judged now.
        """
        # PLAYERS IN THIS SCENE
        #   att   the attestation, or None

        att = d.risk_attestation
        if att is None:
            return ["the risk evidence is not attested by an independent agent"]
        if att.acceptor != d.accepted_by or att.evidence_ids != d.acceptance_evidence:
            return ["the risk-evidence attestation was given for another acceptance"]
        return [f"the risk-evidence attestation by {att.by} is no longer independent: {r}"
                for r in self._attester_failures(d, att.by)]

    # =======================================================================
    # ACT VIII, SCENE 4 — THE DECISION'S CAST LIST
    # The decision's signals that are actually registered.
    # =======================================================================

    def _decision_signals(self, d: Decision) -> list[Signal]:
        """
        The Signal objects a decision depends on.

        Enter:   d   the decision
        Exit:    its signals, in order; ids not registered are skipped
        """
        return [self.signals[s] for s in d.signal_ids if s in self.signals]

    # =======================================================================
    # ACT VIII, SCENE 5 — HAS THE STORY SETTLED?
    # Classification stabilized: no lowering of caution since review opened.
    # =======================================================================

    def _lowerings(self, sig: Signal) -> list[tuple[int, O, O]]:
        """
        Every reclassification of this signal toward a less cautious state.

        Enter:   sig   the signal
        Exit:    (clock tick, from state, to state) for each change in its
                 classification history that LOWERINGS names a lowering,
                 except a reclassification that resolved an off-envelope
                 review under its trigger's standard

        zip(history, history[1:]) pairs each classification with the one
        after it, so each pair is one change (or one re-confirmation).

        Spec (Layer 4, Execution Gates, "Classification stabilized"): "...
        neither does a reclassification that resolves an off-envelope or
        containment review under the standard its trigger requires
        (Overrides)." resolve_review() records those ticks in
        Signal.resolving_reclassifications. A containment review is
        resolved by steward review, not by reclassification, so only
        off-envelope resolutions are recorded.
        """
        # PLAYERS IN THIS SCENE
        #   history   the (tick, state) pairs, oldest first
        #   before    the earlier state of a pair
        #   t, after  the later pair's tick and state

        history = sig.classification_history
        return [(t, before, after)
                for (_, before), (t, after) in zip(history, history[1:])
                if before in LOWERINGS.get(after, frozenset())
                and t not in sig.resolving_reclassifications]

    def _classification_stable(self, sig: Signal, now: Optional[int] = None) -> bool:
        """
        Classification stabilized, first condition: classified, and not
        reclassified toward a less cautious state since its first review
        opened (or, with a stabilization window registered, within that
        window before `now`).

        Enter:   sig   the signal
                 now   the clock time the test is run for (default: now)
        Exit:    True if its classification counts as stabilized

        Spec: Rule 3, Interpretive Stability Precedes Execution: "Execution
        cannot proceed while interpretive uncertainty remains unresolved and
        unstabilized ... Interpretive stability is achieved by naming the
        uncertainty, not by eliminating it." Layer 4, Execution Gates,
        "Classification stabilized": "no signal has been reclassified
        toward a less cautious state since its first review opened: to
        nominal from any other state, or to elevated uncertainty from
        off-envelope, experimental, or containment. A domain may register a
        stabilization window instead, in which case the test covers that
        window before the execution request. The test runs over the
        signal's whole history, so closing and reopening a loop does not
        restart it. A reclassification toward greater caution does not
        destabilize ... re-confirming the same state does not destabilize
        either." The second condition, the decision's Rule 3 registration,
        is checked by the gate (Scene 8), since it belongs to the decision.

        IMPLEMENTATION DECISION D8, the measurement:
          - never classified -> not stable (the gate also reports it as
            "classification not acknowledged")
          - no window: a lowering counts if made after the first review
            opened; a signal never put under review has none that count
          - window of w ticks: a lowering counts if made after now - w
        """
        # PLAYERS IN THIS SCENE
        #   now     the clock time judged against
        #   since   lowerings made after this tick count
        #   t       each lowering's tick

        if not sig.classification_history:
            return False
        now = self.clock if now is None else now
        if self.settings.stabilization_window is not None:
            since = now - self.settings.stabilization_window
        elif sig.first_review_opened_at < 0:
            return True
        else:
            since = sig.first_review_opened_at
        return not any(since < t <= now for t, _, _ in self._lowerings(sig))

    # =======================================================================
    # ACT VIII, SCENE 6 — THE COHERENCE SCORE
    # How much confidence does this decision's record actually warrant?
    # =======================================================================

    def coherence(self, decision_id: str) -> tuple[float, dict[str, float]]:
        """
        Coherence score for a decision node (Layer 4): five factors, each in
        [0, 1] with 1 healthy, weighted as in v0.2. Factor formulas are
        implementation decision D3.

        Enter:   decision_id   the decision
        Exit:    (score, factors): the weighted score and each factor's
                 value, all rounded to 4 decimal places. A decision with no
                 registered signals scores 1.0 on everything. Raises
                 TransitionRefused for an unknown decision.

        Spec: Layer 4, Coherence Score: "a continuous
        0.0-1.0 measure of decision integrity at a given decision node ...
        a running assessment of how much epistemic confidence the current
        decision state actually warrants." The five factor names and weights
        are the spec's (COHERENCE_WEIGHTS); the spec calls the weights
        "provisional and illustrative" and gives no formulas.

        IMPLEMENTATION DECISION D3, the factor formulas:
          open_loops                1 - (signals open, in trajectory_lock
                                    or in executed_open) / signals. The two
                                    latched states count as open: each
                                    records a loop carried open through
                                    irreversible execution (Layer 4,
                                    Commitment State Machine).
          classification_stability  share of signals that pass D8 (no
                                    lowering since the first review opened)
          closure_quality           chain-sound evidence closures / (real
                                    closures + reopens); 1.0 if there are
                                    neither. An evidence closure that is not
                                    chain-sound counts as non-evidence
                                    (Layer 2, Closure Chain), and evidence
                                    the accepting agent produced does not
                                    count (Layer 2, EES). Attempted
                                    closures are left out; each reopen
                                    counts as a closure that did not hold
                                    (Layer 4, Commitment State Machine:
                                    reopen history feeds the coherence
                                    score).
          recurrence_pressure       1 - the largest min(1, members /
                                    threshold) over the decision's
                                    recurrence groups not yet reviewed;
                                    members are counted across all signals,
                                    not only this decision's
          authority_compression     1 - the largest share of all real
                                    closures made by one agent's
                                    non-evidence closures (anything but a
                                    chain-sound evidence closure, lock-in
                                    included); 0 compression unless there
                                    are at least two closures and at least
                                    one non-evidence closure
        """
        # PLAYERS IN THIS SCENE
        #   d                   the decision
        #   sigs                the decision's registered signals
        #   excluded            producers whose evidence cannot count (the
        #                       accepting agent)
        #   open_or_locked      those open, or latched (trajectory_lock or
        #                       executed_open)
        #   pairs               (signal, closure) for every real closure on them
        #   closures            just the closures
        #   evidence_closures   the chain-sound evidence closures among those
        #   groups              the recurrence groups they belong to
        #   pressure            the highest recurrence pressure found (0..1)
        #   g, n                a group, and its member count
        #   reopens             total reopens across the signals
        #   non_evidence        the real closures that are not evidence closures
        #   top                 most non-evidence closures made by one agent
        #   compression         top / all real closures (or 0.0)
        #   factors             factor name -> value in [0, 1]
        #   score               the weighted sum

        d = self._decision(decision_id)
        sigs = self._decision_signals(d)
        if not sigs:
            # {k: 1.0 for k in ...} is a dict comprehension: every factor -> 1.0.
            return 1.0, {k: 1.0 for k in COHERENCE_WEIGHTS}
        # The accepting agent's own evidence cannot support the decision it
        # accepted (Layer 2, EES: "the agent accepting the decision it
        # supports"), so it is excluded when closures are judged here.
        excluded = frozenset({d.accepted_by}) if d.accepted_by else frozenset()
        # --- Gather what the factors are computed from ---------------------
        open_or_locked = [s for s in sigs if s.is_open or s.state in (S.TRAJECTORY_LOCK,
                                                                      S.EXECUTED_OPEN)]
        # Two `for` clauses: for each signal, for each of its closures. The
        # (signal, closure) pairs let each closure be judged against its own
        # signal; only chain-sound evidence closures count as evidence
        # (Layer 2, Closure Chain).
        pairs = [(s, c) for s in sigs for c in s.closures if not c.attempted_only]
        closures = [c for _, c in pairs]
        evidence_closures = [c for s, c in pairs
                             if self._closure_sound(c, s, frozenset(), excluded)]
        # {... for ...} with no colon is a set comprehension: duplicates
        # collapse, so each group appears once. `if s.recurrence_group`
        # skips signals with no group.
        groups = {s.recurrence_group for s in sigs if s.recurrence_group}
        # --- Recurrence pressure: the worst unreviewed group ---------------
        pressure = 0.0
        for g in groups:
            if g in self.reviewed_groups:
                continue
            n = sum(1 for s in self.signals.values() if s.recurrence_group == g)
            pressure = max(pressure, min(1.0, n / self.settings.recurrence_threshold))
        reopens = sum(s.reopen_count for s in sigs)
        # --- Authority compression: one closer dominating non-evidence ----
        non_evidence = [c for s, c in pairs
                        if not self._closure_sound(c, s, frozenset(), excluded)]
        if len(closures) >= 2 and non_evidence:
            # For each distinct closer (a set comprehension), count their
            # non-evidence closures; keep the largest count.
            top = max(sum(1 for c in non_evidence if c.closed_by == a)
                      for a in {c.closed_by for c in non_evidence})
            compression = top / len(closures)
        else:
            compression = 0.0
        # --- The five factors ----------------------------------------------
        factors = {
            "open_loops": 1.0 - len(open_or_locked) / len(sigs),
            # sum() over booleans counts the stable signals.
            "classification_stability":
                sum(self._classification_stable(s) for s in sigs) / len(sigs),
            # each reopen is a closure that did not hold (Layer 4: reopen history
            # feeds the coherence score)
            "closure_quality": (len(evidence_closures) / (len(closures) + reopens))
                               if closures or reopens else 1.0,
            "recurrence_pressure": 1.0 - pressure,
            "authority_compression": 1.0 - compression,
        }
        # --- Weighted sum, rounded -----------------------------------------
        # round(x, 4) rounds to 4 decimal places, so scores print cleanly
        # and compare predictably in tests and audit entries.
        score = sum(COHERENCE_WEIGHTS[k] * v for k, v in factors.items())
        return round(score, 4), {k: round(v, 4) for k, v in factors.items()}

    # =======================================================================
    # ACT VIII, SCENE 7 — IS THE STAGE ITSELF SOUND?
    # Layer 0: the architecture voids a runtime can check.
    # =======================================================================

    def architecture_check(self, decision_id: str) -> list[str]:
        """
        Layer 0 sub-conditions a runtime can check from registered facts.
        Returns the list of voids found (empty = no void detected). AP.3,
        AP.4, AP.5 and AP.8 need interviews or document review and are not
        checked here (docs/DECISIONS.md, D9).

        Enter:   decision_id   the decision
        Exit:    a sorted list of void descriptions, without duplicates

        Spec: Layer 0, Architecture Precondition. With the precondition
        unmet, execution gates are "Structurally void" (Why This Matters):
        "When the Architecture Precondition fails, the architecture itself
        is the open loop" (same section).

        Checked, per high-consequence signal of the decision (constraint
        and anomaly signals; IMPLEMENTATION DECISION D9, in types.py), for
        its failure mode (Signal.mode):
          AP-A / AP.1  no steward, in the architecture or on the signal
                       (The Eight Sub-Conditions, AP.1 and AP.1a; The Eight
                       Void Types, AP-A); or a steward, or a successor,
                       without obligation capacity (Agent Admissibility,
                       "Admissibility criterion")
          AP.1b        no successor, in the architecture or on the signal,
                       or a successor who is the steward (The Eight
                       Sub-Conditions, AP.1b)
          AP-F / AP.6  reporters are registered for the mode and every one
                       of them is an interested party (The Eight
                       Sub-Conditions, AP.6; The Eight Void Types, AP-F)
          AP-G         the signal's registrant is under Sender Discount
                       (The Eight Void Types, AP-G)
        And for the whole architecture (every registered channel, whatever
        the decision's signals are):
          AP.2         every registered channel not tested under load:
                       "Untested channels are treated as absent" (The Eight
                       Sub-Conditions, AP.2)
        """
        # PLAYERS IN THIS SCENE
        #   voids        the void descriptions found so far
        #   arch         the registered architecture
        #   sig          each of the decision's signals
        #   mode         its failure mode
        #   steward, successor   who is named for that mode (or None)
        #   reporters    registered reporters for that mode (or None)
        #   interested   parties interested in denying it (default empty set)
        #   channel, tested   each registered channel and whether it was tested

        voids = []
        arch = self.architecture
        for sig in self._decision_signals(self._decision(decision_id)):
            if not sig.high_consequence:
                continue
            mode = sig.mode
            # --- AP-A: is anyone the steward? ------------------------------
            steward = arch.stewards.get(mode) or sig.steward
            successor = arch.successors.get(mode) or sig.successor
            if not steward:
                voids.append(f"AP-A stewardship void: no steward for failure mode {mode!r}")
            # --- AP-A: can the steward hold the obligation at all? ---------
            # "A stewardship function assigned to a component without
            # obligation capacity is a stewardship void (AP-A) for the
            # failure mode it guards, whatever the component's reliability"
            # (Layer 0, Agent Admissibility).
            elif not self.obligation_capable(steward, successor):
                voids.append(f"AP-A stewardship void: steward {steward!r} for failure mode "
                             f"{mode!r} has no obligation capacity (Agent Admissibility)")
            # --- AP.1b: is a successor registered, and someone else? -------
            # A "successor" who is the steward is still "a single point of
            # failure" (AP.1b, Stewardship Succession, which since October
            # 2026 says so explicitly). Found by the Alloy model
            # (verification/alloy, NoSinglePointOfStewardship).
            if not successor:
                voids.append(f"AP.1b: no registered successor for failure mode {mode!r}")
            elif successor == steward:
                voids.append(f"AP.1b: the successor for failure mode {mode!r} is the "
                             "steward (single point of failure)")
            elif not self.obligation_capable(successor):
                voids.append(f"AP-A stewardship void: successor {successor!r} for failure "
                             f"mode {mode!r} has no obligation capacity (Agent "
                             "Admissibility)")
            # --- AP-F: is the only reporting route captured? ---------------
            # For sets, `a <= b` means "a is a subset of b": every reporter
            # is also an interested party.
            reporters = arch.reporters.get(mode)
            interested = arch.interested_parties.get(mode, set())
            if reporters is not None and reporters and reporters <= interested:
                voids.append(f"AP-F captured channel: every reporter for {mode!r} is an "
                             "interested party")
            # --- AP-G: is the sender discounted? ---------------------------
            if sig.registered_by in self.sender_discount_void:
                voids.append(f"AP-G sender discount against {sig.registered_by}")
        # --- AP.2: untested channels count as absent -----------------------
        for channel, tested in arch.channels_tested.items():
            if not tested:
                voids.append(f"AP.2: channel {channel!r} untested (treated as absent)")
        # set(...) drops duplicates (two signals sharing a mode); sorted(...)
        # turns it back into a list in a fixed order.
        return sorted(set(voids))

    def unverified_preconditions(self, decision_id: str) -> list[str]:
        """
        The Layer 0 sub-conditions AP.2-AP.8 with no check behind them for
        this decision: reported in the gate record as unverified.

        Enter:   decision_id   the decision
        Exit:    a list of sub-condition labels, in order, e.g.
                 ["AP.3", "AP.4", "AP.5", "AP.8"]

        Spec (Layer 4, Execution Gates, "Architecture Precondition met"):
        "each of AP.2-AP.8 either passes its registered check or is
        reported in the gate record as unverified; some, such as AP.4's
        unprompted-recall audit, cannot be checked from inside the system
        at all." Reporting only: nothing blocks on it.

        IMPLEMENTATION DECISION, what counts as a check (D9):
          AP.2  checked when at least one channel is registered (an
                untested one is already a void); unverified with none
          AP.6  checked when reporters are registered for every failure
                mode the decision's constraint and anomaly signals name;
                unverified otherwise
          AP.7  checked by the runtime itself (credibility discounts and
                AP-G are tracked for every agent), so never listed
          AP.3, AP.4, AP.5, AP.8   no check from registered facts
                (RUNTIME_UNCHECKABLE): always listed
        """
        # PLAYERS IN THIS SCENE
        #   d       the decision
        #   modes   failure modes its constraint and anomaly signals name
        #   out     the labels found

        d = self._decision(decision_id)
        modes = {s.mode for s in self._decision_signals(d) if s.high_consequence}
        out = []
        if not self.architecture.channels_tested:
            out.append("AP.2")
        out += [x for x in RUNTIME_UNCHECKABLE if x < "AP.6"]
        if any(not self.architecture.reporters.get(m) for m in modes):
            out.append("AP.6")
        out += [x for x in RUNTIME_UNCHECKABLE if x > "AP.6"]
        return out

    # =======================================================================
    # ACT VIII, SCENE 7b — WHAT THE IRREVERSIBLE GATE ASKS OF LOOPS AND EVIDENCE
    # Is each loop resolved, and is the principal risk claim checked from
    # outside?
    # =======================================================================

    def _gate_resolved(self, sig: Signal, excluded: frozenset = frozenset()) -> bool:
        """
        Does a constraint or anomaly loop meet the irreversible gate?

        Enter:   sig        a constraint or anomaly signal
                 excluded   producers whose evidence cannot count (the
                            decision's accepting agent)
        Exit:    True if it is closed by a chain-sound evidence closure, or
                 exited as superseded with an External Evidence Source

        Spec: Layer 4, Execution Gates, "Constraint and anomaly loops
        evidence-closed": "every constraint and anomaly signal the decision
        depends on is closed by a chain-sound evidence closure, or has exited
        as superseded with an External Evidence Source showing that the
        context that generated it no longer exists. ... A loop that is open,
        closed by authority or role switch, latched, closed by evidence that
        is not chain-sound, or exited by any other type does not meet it.
        That includes the terminal, timeout, whistleblower, and legal exits".
        """
        return self._loop_resolved(sig.signal_id, frozenset(), excluded)

    @staticmethod
    def _other_loop_closed(sig: Signal) -> bool:
        """
        Is a loop of the other types (uncertainty, dissent, classification,
        framing) closed, for "none left open"?

        Enter:   sig   the signal
        Exit:    True if it is in a closed state (any closure type) or has
                 exited as superseded (CLOSING_EXITS); a terminal exit, and
                 every other exit, leaves it open

        Spec: Layer 4, Execution Gates: "none remains open: each is closed,
        by whatever closure type, or has exited as superseded. A loop
        exited as terminal counts as open for this test, since the exit
        records the loop's open state rather than resolving it." No External
        Evidence Source is needed for these types (that test is only for
        constraint and anomaly loops).
        """
        if sig.state == S.EXITED and sig.exit is not None:
            return sig.exit.exit_type in CLOSING_EXITS
        return sig.state in CLOSED_STATES

    def _unresolved_at_gate(self, d: Decision, sigs: list[Signal]) -> list[Signal]:
        """
        The loops the irreversible gate does not count as resolved: the
        ones an open-loop authorization carries open.

        Enter:   d      the decision
                 sigs   its registered signals
        Exit:    the constraint and anomaly signals that fail
                 _gate_resolved (in any state), and the other-type signals
                 that are not closed (_other_loop_closed)

        Spec: Layer 4, Commitment State Machine, the `executed_open`
        paragraph: "That covers a constraint or anomaly loop not
        evidence-closed, whatever state it was in — open, closed by
        authority or role switch, or exited — and a loop of another type
        still open."
        """
        # PLAYERS IN THIS SCENE
        #   excluded   the accepting agent, whose evidence cannot count

        excluded = frozenset({d.accepted_by}) if d.accepted_by else frozenset()
        return [s for s in sigs
                if (s.high_consequence and not self._gate_resolved(s, excluded))
                or (not s.high_consequence and not self._other_loop_closed(s))]

    def _decision_ees(self, d: Decision, sigs: list[Signal]) -> bool:
        """
        Does the Rule 4 acceptance cite an External Evidence Source for the
        principal risk claim?

        Enter:   d      the decision
                 sigs   its registered signals
        Exit:    True if some evidence cited in the acceptance is of an
                 eligible kind and produced by neither the accepting agent
                 nor a process under evaluation in the decision's loops

        Spec: Layer 4, Execution Gates, "At least one External Evidence
        Source for the principal risk claim": "the Rule 4 acceptance names
        the decision's principal risk claim ... and cites at least one
        External Evidence Source bearing on it (Layer 2). Evidence elsewhere
        in the decision's support, in its loops' closures, does not
        substitute ... Whether the cited evidence bears on the claim is
        attested by an agent other than the acceptor who meets the
        independence conditions under Overrides, and the attestation stays
        in the record." The attestation is attest_risk_evidence() (ACT VIII,
        Scene 3b), checked at the gate. The accepting agent is the claimant
        here ("the accepting agent, for a Rule 4 acceptance", Layer 2, EES).

        IMPLEMENTATION DECISION: the spec states no novelty or chain test
        for evidence cited in the acceptance, so none is applied to it.
        Whether a risk claim was named at all is checked by the gate.
        """
        # PLAYERS IN THIS SCENE
        #   processes   the processes under evaluation in its loops

        processes = {s.evaluated_process for s in sigs}
        return any(self.is_ees(self.evidence[e], None, d.accepted_by, processes)
                   for e in d.acceptance_evidence if e in self.evidence)

    def _nominal_unvalidated(self, d: Decision, sigs: list[Signal]) -> list[str]:
        """
        The signals classified nominal without an External Evidence Source
        for the classifying agent's claim.

        Enter:   d      the decision (its accepting agent is excluded too)
                 sigs   its registered signals
        Exit:    ids of nominal signals whose latest classification cites no
                 EES, judged now

        Spec: Layer 4, Execution Gates, "Classification acknowledged":
        "every signal classified nominal cites an External Evidence Source
        that the condition lies within validated parameters (Rule 2:
        unvalidated conditions cannot be classified as nominal). A label
        alone does not meet it." classify() already refuses an unvalidated
        nominal; this re-checks it with the accepting agent excluded, since
        the acceptance may come after the classification.
        """
        # PLAYERS IN THIS SCENE
        #   excluded   the accepting agent
        #   bad        the failing signal ids
        #   s, last    each nominal signal and its latest classification

        excluded = {d.accepted_by} if d.accepted_by else set()
        bad = []
        for s in sigs:
            if s.operational_state != O.NOMINAL:
                continue
            last = s.classification_records[-1] if s.classification_records else None
            if last is None or not any(self.is_ees(self.evidence[e], s, last.by, excluded)
                                       for e in last.evidence_ids if e in self.evidence):
                bad.append(s.signal_id)
        return bad

    # =======================================================================
    # ACT VIII, SCENE 7c — THE LATCH
    # Carry the unresolved loops into executed_open, signed for.
    # =======================================================================

    def _latch(self, d: Decision, sigs: list[Signal], by: str, rationale: str,
               emergency_id: Optional[str]) -> tuple[list[str], list[str]]:
        """
        The POST-EXECUTION LATCH: move every loop the gate did not count as
        resolved into executed_open, with the authorization record, and make
        the authorizer its steward; annotate a loop in an external exit.

        Enter:   d              the irreversible decision about to execute
                 sigs           its registered signals
                 by             the overrider, or the agent giving the
                                Emergency Justification
                 rationale      their rationale
                 emergency_id   "EJ<n>" for an Emergency Justification, else
                                None
        Exit:    (latched, annotated): ids of the signals latched, and of
                 those annotated. A latched signal gets an
                 OpenLoopAuthorization, moves to executed_open (a TRANSITION
                 entry) unless it is already there, and its steward becomes
                 `by` (STEWARD_ASSIGNED, with the previous steward). An
                 annotated signal (exited whistleblower or legal) keeps its
                 exit state and steward and gets the OpenLoopAuthorization
                 as an annotation (OPEN_LOOP_ANNOTATED). One
                 OPEN_LOOP_IRREVERSIBLE_EXECUTION entry lists them all.

        Spec: Layer 4, Commitment State Machine: "any loop not resolved at
        irreversible execution -> executed_open (open-loop authorization
        recorded)", "carrying the authorization record: who authorized, as
        steward of those loops, and on what rationale". Overrides: an
        override is "one act, not two: an agent other than the acceptor
        judges the failures the gate names acceptable, and registers as
        steward (AP.1) of every loop the decision carries open."

        Spec, same paragraph: "A loop exited to an external process
        (whistleblower, legal) keeps that exit state, because it continues
        elsewhere, and carries the authorization record as an annotation."
        IMPLEMENTATION DECISION: its steward is not changed either; the loop
        is stewarded in the external process it continues in.

        A loop already in executed_open (latched by an earlier decision) is
        signed for again, without a move. A loop in trajectory_lock cannot
        move (the state is terminal); it is listed under `not_latched` in
        the log. No LOCK_IN closure record and no
        LOCK_IN_WITH_OPEN_CONSTRAINTS escalation are made here: "The runtime
        refuses such overrides, so it does not produce `trajectory_lock` at
        execution".
        """
        # PLAYERS IN THIS SCENE
        #   latched, not_latched   ids moved (or re-signed), and ids that
        #                          could not move
        #   annotated              ids in an external exit, annotated
        #   s                      each unresolved signal
        #   auth                   its OpenLoopAuthorization
        #   previous               its steward before

        latched, not_latched, annotated = [], [], []
        for s in self._unresolved_at_gate(d, sigs):
            if s.state == S.TRAJECTORY_LOCK:
                not_latched.append(s.signal_id)
                continue
            auth = OpenLoopAuthorization(d.decision_id, by, rationale, self.clock,
                                         emergency_id, s.state.value)
            # --- An external exit: annotate, do not move -------------------
            if s.state == S.EXITED and s.exit is not None and \
                    s.exit.exit_type in EXTERNAL_EXITS:
                s.open_loop_authorizations.append(auth)
                self._log("OPEN_LOOP_ANNOTATED", by, signal=s.signal_id,
                          decision=d.decision_id, exit_type=s.exit.exit_type,
                          emergency=emergency_id, rationale=rationale,
                          reason="the loop continues in an external process; it keeps "
                                 "its exit state and carries the authorization")
                annotated.append(s.signal_id)
                continue
            if s.state != S.EXECUTED_OPEN:
                self._move(s, S.EXECUTED_OPEN, by, decision=d.decision_id, authorized_by=by,
                           rationale=rationale, emergency=emergency_id,
                           prior_state=auth.prior_state)
            s.open_loop_authorizations.append(auth)
            previous, s.steward = s.steward, by
            self._log("STEWARD_ASSIGNED", by, signal=s.signal_id, steward=by,
                      previous=previous, decision=d.decision_id, emergency=emergency_id,
                      reason="the open-loop authorizer registers as steward of every loop "
                             "the decision carries open (AP.1)")
            latched.append(s.signal_id)
        self._log("OPEN_LOOP_IRREVERSIBLE_EXECUTION", by, decision=d.decision_id,
                  latched=latched, annotated=annotated, not_latched=not_latched,
                  rationale=rationale, emergency=emergency_id)
        return latched, annotated

    # =======================================================================
    # ACT VIII, SCENE 8 — THE INTERLOCK
    # May this decision execute? Check the gates, and handle overrides.
    # =======================================================================

    def request_execution(self, decision_id: str, by: str,
                          override_rationale: Optional[str] = None,
                          emergency: Optional[EmergencyJustification] = None) -> GateResult:
        """
        Execution gate (Layer 4). Requirements by class (cumulative):
        The class used is the APPLIED one (_applied_class): the declared
        class only if a tested reversal path supports it, else irreversible.
          irreversible  constraint and anomaly loops evidence-closed (weakest
                        link, chain-sound, or superseded with an EES);
                        minimum evidence closure ratio met for the other
                        loops, none left open; a principal risk claim with
                        an External Evidence Source in the Rule 4
                        acceptance; classification stabilized (no lowering;
                        Rule 3 registration); recurrence groups reviewed;
                        coherence at or above threshold; plus the
                        implementation checks listed below (no unresolved
                        structural reviews, no open off-envelope/containment
                        signals)
          elevated      classification acknowledged (every signal has a
                        state; every nominal one cites an EES); open loops
                        documented (none merely registered; every open loop
                        has a steward)
          routine       signal registration complete; Architecture
                        Precondition met (no Layer 0 void)
        Order of checks: an already-executed decision is refused; then a
        requester without EXECUTE power, a missing Rule 4 acceptance, or an
        acceptance no longer backed by authority returns at once
        (EXECUTION_REFUSED); then an unresolved
        EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK review on the decision returns
        at once (EXECUTION_BLOCKED). None of those can be overridden or
        suspended, and each marks the decision `ever_blocked`. Only then are
        the gates above evaluated. Failures with neither an override nor an
        Emergency Justification mark the decision `ever_blocked`, so a later
        lowering of its class escalates (reclassify_decision, ACT VIII,
        Scene 1b).

        Enter:   decision_id          the decision asking to execute
                 by                   the requesting agent (and, with an
                                      override or emergency, the agent
                                      authorizing the open loops)
                 override_rationale   if given, asks to override the gate's
                                      failures, within the limits below
                 emergency            an EmergencyJustification, for an
                                      irreversible decision held only by
                                      off-envelope or containment reviews
                                      (see _emergency_execution)
        Exit:    a GateResult. On permission (clean, overridden or under an
                 Emergency Justification) the decision is marked executed.
                 Raises TransitionRefused if the decision is unknown or has
                 already executed (the latter after the clock has ticked).

        Spec sources:
          Execution Gates table and "Operational definitions" (Layer 4),
            summarized above. "Signal registration complete — every signal
            the decision names has been registered." "Architecture
            Precondition met — no Layer 0 void is found for the failure
            modes the decision's signals name ... At an irreversible
            decision a void cannot be overridden ... At the other classes a
            void is reported and may be overridden." "Open loops documented
            — no such signal remains merely registered, and every loop
            still open has a named steward." The ratio applies to
            "uncertainty, dissent, classification, and framing signals":
            "the share closed by chain-sound evidence closure meets the
            domain-configured minimum (one half by default), and none
            remains open ... A loop left open counts against the ratio ...
            With no such signals, the requirement is met." "Recurrence
            groups reviewed — no recurrence group among the decision's
            signals has a structural review still awaiting its Rule 8 model
            update".
          Overrides (same section): "An override is the open-loop
            authorization of Reversibility Logic — one act, not two ...
            Every override is permanently logged with the agent's identity,
            rationale, and timestamp." Its limits: the acceptor cannot
            override; nor can an agent in the acceptor's reporting line;
            the authority to override is registered separately; "While a
            structural review touching an irreversible decision remains
            unresolved ... the decision cannot execute, and this cannot be
            overridden"; relabeling after refusal cannot be overridden.
          Agent Admissibility (Layer 0): open-loop authorization is a
            stewardship act and requires obligation capacity.
          Coherence (Layer 4, Coherence Score): "A score below the
            domain-configured threshold blocks irreversible execution
            pending acknowledgment, given as an override".
          Reversibility Logic: "Irreversible decisions require
            evidence-based closure for all constraint and anomaly loops, and
            every other loop closed, or an explicit open-loop authorization
            with permanent audit logging for the loops that are not."
          The POST-EXECUTION LATCH (Layer 4, Commitment State Machine; see
            _latch): at an irreversible override, the loops the gate did not
            count as resolved move to executed_open. "The limits leave no
            state in which an irreversible decision has executed over a
            suppressed loop, or over a loop escalated by any review other
            than an off-envelope or containment review suspended under an
            Emergency Justification".
          Escalation conditions (Layer 2, Escalation Conditions): suppressed
            signal before irreversible execution.

        IMPLEMENTATION DECISIONS made here (not in the spec):
          - Unresolved structural reviews on the decision's signals, or on
            the decision itself, block irreversible execution and hold it
            against any override (the spec's hold; how "touching" is read).
          - Open off-envelope or containment signals block irreversible
            execution. This reads Key Definitions (Operational State:
            Off-Envelope and Containment): off-envelope needs
            "Evidence-based classification ... before irreversible
            execution"; containment: "Irreversible execution requires
            independent steward review, or, where the review cannot
            complete in time, an Emergency Justification". It is an overridable failure (the
            review the classification opened is the hold).
          - A suppressed signal at an irreversible request opens the
            SUPPRESSED_BEFORE_EXECUTION review first, before the other
            irreversible checks run, so that review's "unresolved
            structural review" failure blocks this same request.
          - The gate's tests that depend on who produced evidence (loop
            resolution, nominal classification, the risk claim's EES)
            exclude the accepting agent, judged now, so an acceptance made
            after a closure can withdraw that closure's standing for this
            decision ("the agent accepting the decision it supports").
          - Given with an override_rationale, an emergency takes precedence
            (the request is judged as an Emergency Justification).
        """
        # PLAYERS IN THIS SCENE
        #   d                  the decision
        #   applied            the class the gate applies (Execution Class
        #                      Assignment): declared, or irreversible
        #   relabel            unresolved downgrade-after-block reviews on it
        #   reason             the failure text when one blocks it
        #   sigs               its registered signals
        #   score, factors     its coherence score and factor values
        #   failures           every unmet requirement, as text
        #   voids              Layer 0 voids found (also added to failures)
        #   missing            decision signal ids that are not registered
        #   unclassified       signals with no operational state
        #   unvalidated        nominal signals without a cited EES
        #   undocumented       signals still only `registered`
        #   unstewarded        open signals with no named steward
        #   suppressed         signals currently suppressed
        #   excluded           the accepting agent, as an excluded producer
        #   unresolved         constraint/anomaly signals failing the gate
        #   unstable           signals reclassified toward less caution
        #   groups             the signals' recurrence groups
        #   unreviewed         groups with an unresolved recurrence review
        #   others             the uncertainty/dissent/classification/framing
        #                      signals
        #   ratio              share of those closed by chain-sound evidence
        #   left_open          those not closed
        #   pending            unresolved reviews touching this decision
        #   hold               the same, when they hold irreversible execution
        #   off                open signals classified off-envelope/containment
        #   result             the GateResult being returned
        #   refusals           why an override is refused
        #   independence       refusals that only another agent could answer
        #   latched            signals latched into executed_open

        self._require_actor(by)
        d = self._decision(decision_id)
        self._tick()
        d.requesters.add(by)
        sigs = self._decision_signals(d)
        score, factors = self.coherence(decision_id)
        failures: list[str] = []
        # Execution Class Assignment: the gate applies the declared class
        # only if a tested reversal path supports it.
        applied = self._applied_class(d)

        # --- A decision executes once --------------------------------------
        if d.executed:
            raise TransitionRefused(f"decision {decision_id} has already executed")
        # --- Only a holder of EXECUTE may ask (never overridable) ----------
        # Scene 2b. Checked before everything else, and override_rationale
        # and emergency are ignored: an override cannot supply a power
        # nobody granted.
        if not self.holds(by, Power.EXECUTE, d.scope):
            d.ever_blocked = True
            reason = (f"{by} does not hold execute over {d.scope!r} "
                      "(authority is granted, never inferred)")
            self._log("EXECUTION_REFUSED", by, decision=decision_id, reason=reason,
                      declared_class=d.execution_class, execution_class=applied)
            return GateResult(decision_id, applied, False, False, False, [reason], score,
                              declared_class=d.execution_class)
        # --- Rule 4: someone must have accepted it (never overridable) -----
        # Returned at once: no other gate is evaluated and neither an
        # override nor an emergency is considered.
        if not d.accepted_by:
            d.ever_blocked = True
            self._log("EXECUTION_REFUSED", by, decision=decision_id,
                      reason="Rule 4: no agent has accepted this decision",
                      declared_class=d.execution_class, execution_class=applied)
            return GateResult(decision_id, applied, False, False, False,
                              ["Rule 4: no named agent has accepted authorization, risk "
                               "acceptance and rationale"], score,
                              declared_class=d.execution_class)
        # --- The acceptance must still be backed (never overridable) -------
        # Scene 2b. Authority is checked when it is used, not only when it
        # was given: an acceptance made under a grant since revoked or
        # expired no longer authorizes anything, even if the acceptor has
        # been given authority again since (that calls for a new acceptance).
        if self.authority_enforced and d.accepted_by not in self.settings.authority_roots and (
                d.acceptance_grant is None
                or not self._grant_valid(self._grant(d.acceptance_grant), self.now())):
            d.ever_blocked = True
            reason = (f"Rule 4: {d.accepted_by}'s acceptance is no longer backed by "
                      f"authority in force over {d.scope!r} (revoked or expired); "
                      "a new acceptance is needed")
            self._log("EXECUTION_REFUSED", by, decision=decision_id, reason=reason,
                      declared_class=d.execution_class, execution_class=applied)
            return GateResult(decision_id, applied, False, False, False, [reason], score,
                              declared_class=d.execution_class)
        # --- The acceptor must still be able to hold the obligation --------
        # Agent Admissibility, judged when it is used: an acceptor later
        # registered as automation, or as a role whose successor lapsed, no
        # longer owns the decision. Never overridable: a new acceptance is
        # needed.
        if not self.obligation_capable(d.accepted_by):
            d.ever_blocked = True
            reason = (f"Rule 4: {d.accepted_by} no longer has obligation capacity (Agent "
                      "Admissibility); a new acceptance is needed")
            self._log("EXECUTION_REFUSED", by, decision=decision_id, reason=reason,
                      declared_class=d.execution_class, execution_class=applied)
            return GateResult(decision_id, applied, False, False, False, [reason], score,
                              declared_class=d.execution_class)
        # --- Relabeled after a refusal: blocked at every class -------------
        # Never overridable or suspendable: "Until that review is resolved,
        # the decision cannot execute at any class, and this cannot be
        # overridden" (Layer 4, Execution Class Assignment).
        relabel = sorted(r.review_id for r in self.reviews if not r.resolved
                         and r.condition == E.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK
                         and r.scope == f"decision:{decision_id}")
        if relabel:
            d.ever_blocked = True
            reason = (f"unresolved structural reviews: {relabel} (execution class lowered "
                      "after a blocked request; cannot execute at any class until resolved)")
            self._log("EXECUTION_BLOCKED", by, decision=decision_id, failures=[reason],
                      declared_class=d.execution_class, execution_class=applied,
                      architecture_void=False, coherence=score, factors=factors)
            return GateResult(decision_id, applied, False, False, False, [reason], score,
                              declared_class=d.execution_class)

        # --- Routine requirements (every class) ----------------------------
        # Architecture Precondition met: no Layer 0 void. The sub-conditions
        # with no check are reported as unverified, and block nothing.
        voids = self.architecture_check(decision_id)
        failures += voids
        unverified = self.unverified_preconditions(decision_id)
        # Signal registration complete.
        missing = [sid for sid in d.signal_ids if sid not in self.signals]
        if missing or any(s.state == S.UNREGISTERED for s in sigs):
            failures.append(f"signal registration incomplete: {missing}")
        # --- Elevated requirements (elevated and irreversible) -------------
        if applied in (ExecutionClass.ELEVATED, ExecutionClass.IRREVERSIBLE):
            # Classification acknowledged: a state on every signal, and an
            # EES behind every nominal one.
            unclassified = [s.signal_id for s in sigs if s.operational_state is None]
            if unclassified:
                failures.append(f"classification not acknowledged: {unclassified}")
            unvalidated = self._nominal_unvalidated(d, sigs)
            if unvalidated:
                failures.append(f"classification not acknowledged: nominal without an "
                                f"External Evidence Source: {unvalidated}")
            # Open loops documented: none merely registered, every open
            # loop with a named steward.
            undocumented = [s.signal_id for s in sigs if s.state == S.REGISTERED]
            if undocumented:
                failures.append(f"open loops not documented: {undocumented}")
            unstewarded = [s.signal_id for s in sigs if s.is_open and not s.steward]
            if unstewarded:
                failures.append(f"open loops not documented: no named steward: {unstewarded}")
        suppressed = [s.signal_id for s in sigs if s.state == S.SUPPRESSED]
        pending: list[StructuralReview] = []
        hold: list[str] = []          # reviews that hold irreversible execution
        # --- Irreversible requirements -------------------------------------
        if applied == ExecutionClass.IRREVERSIBLE:
            # Escalation first: a suppressed signal before irreversible
            # execution escalates automatically (Layer 2), and the review it
            # opens must block this very request, so it is raised before the
            # unresolved-review check below.
            if suppressed:
                self._escalate(E.SUPPRESSED_BEFORE_EXECUTION, f"decision:{decision_id}",
                               f"suppressed signals at execution request: {suppressed}",
                               [], by)
            excluded = frozenset({d.accepted_by})
            # Constraint and anomaly loops evidence-closed: weakest link,
            # so one failing loop fails the gate (Reversibility Logic).
            unresolved = [s.signal_id for s in sigs
                          if s.high_consequence and not self._gate_resolved(s, excluded)]
            if unresolved:
                failures.append(f"constraint/anomaly loops not evidence-closed: {unresolved}")
            # Classification stabilized (Rule 3; D8): no lowering, and the
            # decision's Rule 3 registration.
            unstable = [s.signal_id for s in sigs if not self._classification_stable(s)]
            if unstable:
                failures.append(f"classification not stabilized: {unstable}")
            if not (d.rule3_known.strip() and d.rule3_assumed.strip()
                    and d.rule3_uncertain.strip()):
                failures.append("classification not stabilized: the Rule 4 acceptance "
                                "carries no Rule 3 registration (what is known, assumed and "
                                "uncertain)")
            # Recurrence groups reviewed (Rules 7-8).
            groups = {s.recurrence_group for s in sigs if s.recurrence_group}
            unreviewed = sorted(g for g in groups
                                if any(r.scope == f"group:{g}" and not r.resolved
                                       for r in self.reviews))
            if unreviewed:
                failures.append(f"recurrence groups not reviewed: {unreviewed}")
            # The other loop types: minimum evidence closure ratio (D4),
            # over every such signal (open ones count against it), and
            # none left open. sum() over booleans counts the signals now
            # closed by a chain-sound evidence closure.
            others = [s for s in sigs if not s.high_consequence]
            if others:
                ratio = (sum(self._signal_sound(s.signal_id, frozenset(), excluded)
                             for s in others) / len(others))
                if ratio < self.settings.min_evidence_closure_ratio:
                    failures.append(f"evidence closure ratio {ratio:.2f} below "
                                    f"{self.settings.min_evidence_closure_ratio:.2f}")
                left_open = [s.signal_id for s in others if not self._other_loop_closed(s)]
                if left_open:
                    failures.append(f"other loops left open: {left_open}")
            # At least one External Evidence Source for the principal risk
            # claim, cited in the Rule 4 acceptance.
            if not d.risk_claim.strip():
                failures.append("no principal risk claim named in the Rule 4 acceptance")
            elif not self._decision_ees(d, sigs):
                failures.append("no External Evidence Source for the principal risk claim")
            else:
                # ... and an independent attestation that it bears on it.
                failures += [f"no External Evidence Source for the principal risk claim: {r}"
                             for r in self._attestation_failures(d)]
            # Unresolved structural reviews (implementation decision).
            # `set(a) & set(b)` is set intersection: the signal ids both
            # lists share; an empty set is falsy. A review resolved by an
            # agent who is not independent of this decision, judged now,
            # counts as unresolved (its resolution is reported).
            touching = [r for r in self.reviews if set(r.signal_ids) & set(d.signal_ids)
                        or r.scope == f"decision:{decision_id}"]
            tainted = {r.review_id: self._resolution_conflicts(r, [d]) for r in touching}
            pending = [r for r in touching if not r.resolved or tainted[r.review_id]]
            if pending:
                hold = sorted(r.review_id for r in pending)
                failures.append(f"unresolved structural reviews: {hold}")
            for rid, why in sorted(tainted.items()):
                if why:
                    failures.append(f"unresolved structural reviews: {rid} counts as "
                                    f"unresolved: its resolution is not independent of "
                                    f"{decision_id} ({'; '.join(why)})")
            # Open off-envelope/containment signals (implementation decision).
            off = [s.signal_id for s in sigs if s.is_open and s.operational_state in
                   (O.OFF_ENVELOPE, O.CONTAINMENT)]
            if off:
                failures.append(f"open off-envelope/containment signals need evidence-based "
                                f"reclassification or independent steward review: {off}")
            # Coherence at or above threshold (D3). `:.2f` formats a number
            # with two decimal places.
            if score < self.settings.coherence_threshold:
                failures.append(f"coherence {score:.2f} below threshold "
                                f"{self.settings.coherence_threshold:.2f}")

        # --- Clean pass: execute -------------------------------------------
        # `not failures` is True when the list is empty.
        result = GateResult(decision_id, applied, not failures, False,
                            bool(voids), failures, score, declared_class=d.execution_class,
                            unverified=unverified)
        if not failures:
            d.executed = True
            self._log("EXECUTION_PERMITTED", by, decision=decision_id,
                      declared_class=d.execution_class, execution_class=applied,
                      coherence=score, factors=factors, unverified=unverified)
            return result

        # --- An Emergency Justification is judged on its own terms ---------
        if emergency is not None:
            result = self._emergency_execution(d, by, emergency, override_rationale, sigs,
                                               applied, failures, voids, pending, score,
                                               factors)
            result.unverified = unverified
            return result

        # --- Failures and no override: blocked -----------------------------
        if not override_rationale:
            d.ever_blocked = True
            self._log("EXECUTION_BLOCKED", by, decision=decision_id,
                      declared_class=d.execution_class, execution_class=applied,
                      failures=failures, unverified=unverified,
                      architecture_void=bool(voids), coherence=score, factors=factors)
            return result

        # --- Limits on overriding (Layer 4, Overrides) ----------------------
        # Each refusal is logged with every reason that applies; nothing
        # executes.
        refusals, independence = [], []
        if hold:
            suspendable = all(r.suspendable for r in pending)
            refusals.append(f"unresolved structural reviews {hold} hold irreversible "
                            "execution until each is resolved by what its trigger requires; "
                            "this cannot be overridden" +
                            ("; only an Emergency Justification can suspend these "
                             "off-envelope/containment holds" if suspendable else ""))
        if applied == ExecutionClass.IRREVERSIBLE and voids:
            refusals.append("a Layer 0 void cannot be overridden at an irreversible "
                            "decision: the architecture must exist before irreversible "
                            "execution, and an override cannot supply it")
        boss = next((a for a in self._acceptors(d) if self.in_reporting_line(by, a)), None)
        if by in self._acceptors(d):
            independence.append(f"{by} accepted this decision and cannot override its gate; "
                                "an override must come from another agent")
        elif boss is not None:
            independence.append(f"{by} reports to {boss}, who accepted this decision, and "
                                "cannot override its gate")
        if not self.obligation_capable(by):
            independence.append(f"{by} has no obligation capacity (Agent Admissibility) and "
                                "cannot give an open-loop authorization")
        if independence:
            refusals += independence
            refusals.append(NO_QUALIFYING_AGENT)
        if not self.holds(by, Power.OVERRIDE, d.scope):
            refusals.append(f"{by} does not hold override over {d.scope!r} "
                            "(authority is granted, never inferred)")
        if refusals:
            d.ever_blocked = True
            self._log("OVERRIDE_REFUSED", by, decision=decision_id, reasons=refusals,
                      failures=failures, rationale=override_rationale,
                      declared_class=d.execution_class, execution_class=applied,
                      coherence=score, factors=factors)
            return GateResult(decision_id, applied, False, False, bool(voids),
                              failures + [f"override refused: {r}" for r in refusals],
                              score, declared_class=d.execution_class, unverified=unverified)

        # Override: permitted, but permanent, attributed and consequential.
        self._log("GATE_OVERRIDE", by, decision=decision_id,
                  declared_class=d.execution_class, execution_class=applied,
                  failures=failures,
                  architecture_void=bool(voids), rationale=override_rationale,
                  coherence=score, factors=factors, unverified=unverified)
        latched: list[str] = []
        annotated: list[str] = []
        # --- Irreversible override: open-loop irreversible execution -------
        if applied == ExecutionClass.IRREVERSIBLE:
            latched, annotated = self._latch(d, sigs, by, override_rationale, None)
        # --- Execute under override ----------------------------------------
        d.executed = True
        result.permitted, result.overridden, result.latched_signals = True, True, latched
        result.annotated_signals = annotated
        return result

    # =======================================================================
    # ACT VIII, SCENE 9 — THE EMERGENCY
    # Proceed before off-envelope or containment reviews resolve, element by
    # element, or not at all.
    # =======================================================================

    def _emergency_execution(self, d: Decision, by: str, ej: EmergencyJustification,
                             override_rationale: Optional[str], sigs: list[Signal],
                             applied: ExecutionClass, failures: list[str],
                             voids: list[str], pending: list[StructuralReview],
                             score: float, factors: dict) -> GateResult:
        """
        Judge an Emergency Justification, and execute under it if every
        element holds.

        Enter:   d                    the decision (its gate has failures)
                 by                   the agent giving the justification
                 ej                   the EmergencyJustification
                 override_rationale   used as the rationale if ej has none
                 sigs                 the decision's registered signals
                 applied              the class the gate applies
                 failures             the gate's failures
                 voids                its Layer 0 voids
                 pending              the unresolved reviews touching it
                 score, factors       its coherence score and factors
        Exit:    a GateResult. Refused (EMERGENCY_REFUSED logged, decision
                 marked ever_blocked, nothing executed) with every reason
                 that applies. Otherwise: EMERGENCY_JUSTIFICATION logged with
                 every element, each holding review marked suspended
                 (REVIEW_SUSPENDED) but left unresolved, the unresolved loops
                 latched into executed_open with the giver as steward, a
                 post-event review opened over the decision and its signals,
                 and the decision executed (permitted, overridden, with
                 emergency_id set).

        Spec: Layer 4, Execution Gates, Overrides, "Emergency
        Justification": "An irreversible decision held only by off-envelope
        or containment reviews may proceed before those reviews are
        resolved under an Emergency Justification, and under no other
        condition. ... Every element below is required and, except under
        the on-scene proviso in element 5, documented before execution",
        elements 1-5; "The justification suspends the holding reviews; it
        does not resolve them. Each still produces its resolution
        afterward, and a mandatory post-event review records whether every
        element held. The post-event review holds later irreversible
        decisions on the same loops as an off-envelope review does, and a
        further Emergency Justification may suspend it. Emergency
        Justifications are counted per failure mode, and recurring ones
        escalate under Rule 7: the third on the same failure mode since its
        last structural review is treated as recurrence, whatever threshold
        the domain sets for ordinary recurrence, and opens a review no
        Emergency Justification can suspend. The justification is judged by
        its elements, never by its outcome." Key Definitions, Open-Loop
        Irreversible Execution: permitted "only once every structural
        review touching the decision is resolved, or suspended under an
        Emergency Justification".

        What it never bypasses: a missing Rule 4 acceptance, the EXECUTE
        power, and an unresolved relabeling review (all returned before
        this is reached); a Layer 0 void (refused here: "At an irreversible
        decision a void cannot be overridden"); any holding review that is
        not off-envelope, containment or post-event (SUSPENDABLE_CONDITIONS).

        Element 4: "An off-envelope condition is classified Experimental ...
        or containment, if it has since become one; a containment condition
        stays in containment." Checked for the signals behind off-envelope
        and containment reviews; a post-event review has no trigger state,
        and its loops answer to the earlier reviews still holding them.

        Element 5: without on_scene, the giver has never accepted the
        decision and is not in the reporting line of any agent who has; on
        scene, the giver may be the acceptor ("the agent on scene may act
        alone; the contemporaneous record ... then stands in for the
        documentation of every element and for the separate open-loop
        authorization the gate would otherwise require. The on-scene agent
        is registered as steward of the loops carried open"). Either way
        the giver needs obligation capacity and, with authority enforced,
        OVERRIDE power, and becomes steward of the loops carried open and
        of the off-envelope and containment loops behind the holds.

        IMPLEMENTATION DECISIONS: Emergency Justifications are counted per
        failure mode (Signal.mode: failure_mode, else recurrence group, else
        signal id) over the signals behind every holding review, the
        post-event review included, counting justifications given (not
        refused ones) since the failure mode's last resolved Rule 7 review
        (a RECURRENCE_THRESHOLD review on "emergency:<mode>", or one naming
        a signal of that mode). The third (EMERGENCY_RECURRENCE_COUNT, not
        Settings.recurrence_threshold) is refused and opens a
        RECURRENCE_THRESHOLD review on "emergency:<mode>" over every signal
        naming that mode, which no justification can suspend. The runtime
        still requires every element in the EmergencyJustification record
        under the on-scene proviso: the record is its copy of the
        contemporaneous record. A justification offered for a decision with
        no failures is not needed and the decision executes cleanly (Scene
        8).
        """
        # PLAYERS IN THIS SCENE
        #   refusals      every reason the justification fails
        #   independence  refusals only another agent could answer
        #   rationale     the stated rationale
        #   consequence   element 1, as an EmergencyConsequence (or None)
        #   holding       the reviews holding the decision
        #   behind        the signals behind them (counted per failure mode)
        #   held          the signals behind its off-envelope and
        #                 containment reviews (element 4; stewarded by the
        #                 giver)
        #   acceptors     every agent who ever accepted the decision
        #   boss          an acceptor the giver reports to, if any
        #   modes         their failure modes
        #   since         failure mode -> clock of its last resolved Rule 7
        #                 review (-1 if none)
        #   r, sid, sig   each review, signal id and signal
        #   state         a signal's operational state, for the message
        #   prior         failure mode -> justifications already given for it
        #   recurring     modes that have reached the recurrence threshold
        #   ej_id         "EJ<n>"
        #   latched       the loops carried open
        #   annotated     the loops in external exits, annotated
        #   previous      a steward replaced by the giver
        #   result        the GateResult returned

        refusals: list[str] = []
        independence: list[str] = []
        rationale = (getattr(ej, "rationale", "") or override_rationale or "").strip()
        # --- The justification itself: elements 1-4 as documented ---------
        if not isinstance(ej, EmergencyJustification):
            refusals.append("an Emergency Justification must be an EmergencyJustification "
                            "record documenting every element")
            consequence = None
        else:
            try:
                consequence = EmergencyConsequence(ej.consequence)
            except ValueError:
                consequence = None
            if consequence is None:
                refusals.append(f"element 1: consequence {ej.consequence!r} does not qualify; "
                                "only death or permanent total disability (MIL-STD-882E "
                                "Category 1, life-safety criteria) or an actively exploited "
                                "CVSS-Critical weakness in a safety-critical function do. "
                                "Schedule, cost, contract, and reputation never qualify")
            if not str(ej.time_estimate or "").strip():
                refusals.append("element 2: no documented time estimate showing the harm "
                                "would arrive before the review could be resolved")
            if not ej.options_considered or not all(str(o).strip()
                                                    for o in ej.options_considered):
                refusals.append("element 3: the intermediate options Rule 6 requires are "
                                "not documented")
            if not ej.best_evidence:
                refusals.append("element 4: no best engineering evidence is recorded with it")
            else:
                unknown = [e for e in ej.best_evidence if e not in self.evidence]
                if unknown:
                    refusals.append(f"element 4: best evidence not on record: {unknown}")
            if not isinstance(ej.on_scene, bool):
                refusals.append("element 5: on_scene must be stated (True or False)")
        if not rationale:
            refusals.append("the justification must state its rationale")
        # --- Where it applies: irreversible, held only by suspendable reviews
        if applied != ExecutionClass.IRREVERSIBLE:
            refusals.append("an Emergency Justification applies only to an irreversible "
                            "decision; use an override at this class")
        if voids:
            refusals.append("a Layer 0 void cannot be suspended by an Emergency "
                            "Justification (the architecture must exist before "
                            "irreversible execution)")
        holding = list(pending)
        if not holding:
            refusals.append("the decision is not held by an off-envelope, containment or "
                            "post-event review; an Emergency Justification applies only to "
                            "such holds")
        not_suspendable = sorted(r.review_id for r in holding if not r.suspendable)
        if not_suspendable:
            refusals.append(f"reviews {not_suspendable} record failures of the coordination "
                            "process itself, not conditions of the world; no emergency "
                            "justifies proceeding past them")
        # --- Element 4: registered, not reclassified -------------------------
        behind, held = [], []
        for r in holding:
            if not r.suspendable:
                continue
            for sid in r.signal_ids:
                sig = self.signals.get(sid)
                if sig is None:
                    continue
                if sig not in behind:
                    behind.append(sig)
                if r.condition != E.OFF_ENVELOPE_OR_CONTAINMENT:
                    continue
                if sig not in held:
                    held.append(sig)
                if r.trigger == O.OFF_ENVELOPE and sig.operational_state not in (
                        O.EXPERIMENTAL, O.CONTAINMENT):
                    state = sig.operational_state.value if sig.operational_state else None
                    refusals.append(f"element 4: {sid} is behind off-envelope review "
                                    f"{r.review_id} but is classified {state}, "
                                    "not experimental (or containment)")
                if r.trigger == O.CONTAINMENT and sig.operational_state != O.CONTAINMENT:
                    refusals.append(f"element 4: {sid} is behind containment review "
                                    f"{r.review_id} but is no longer classified containment")
        # --- Element 5: separate authorization and stewardship ---------------
        on_scene = isinstance(ej, EmergencyJustification) and ej.on_scene is True
        if not on_scene:
            acceptors = self._acceptors(d)
            boss = next((a for a in acceptors if self.in_reporting_line(by, a)), None)
            if by in acceptors:
                independence.append(f"element 5: {by} accepted this decision; the "
                                    "justification must be given by another agent unless "
                                    "the agent on scene must act alone (on_scene)")
            elif boss is not None:
                independence.append(f"element 5: {by} reports to {boss}, who "
                                    "accepted this decision")
        if not self.obligation_capable(by):
            independence.append(f"element 5: {by} has no obligation capacity (Agent "
                                "Admissibility) and cannot steward the loops carried open")
        if independence:
            refusals += independence
            refusals.append(NO_QUALIFYING_AGENT)
        if not self.holds(by, Power.OVERRIDE, d.scope):
            refusals.append(f"{by} does not hold override over {d.scope!r} "
                            "(authority is granted, never inferred)")
        # --- Counting: a third emergency on one failure mode is a pattern ----
        modes = sorted({sig.mode for sig in behind})
        if not refusals:
            since = {m: max([r.resolved_at for r in self.reviews
                             if r.resolved and r.condition == E.RECURRENCE_THRESHOLD
                             and (r.scope == f"emergency:{m}"
                                  or any(self.signals[x].mode == m for x in r.signal_ids
                                         if x in self.signals))], default=-1)
                     for m in modes}
            prior = {m: sum(1 for (_, _, ms, _, at) in self.emergencies
                            if m in ms and at > since[m]) for m in modes}
            recurring = [m for m in modes if prior[m] + 1 >= EMERGENCY_RECURRENCE_COUNT]
            for m in recurring:
                self._escalate(E.RECURRENCE_THRESHOLD, f"emergency:{m}",
                               f"Emergency Justification {prior[m] + 1} on failure mode "
                               f"{m!r}: a pattern, not a black swan (Rule 7)",
                               sorted(s.signal_id for s in self.signals.values()
                                      if s.mode == m), by)
                refusals.append(f"Emergency Justification {prior[m] + 1} on failure mode "
                                f"{m!r} is refused: recurring emergencies escalate under "
                                "Rule 7 (a structural review is now open)")
        # --- Refused --------------------------------------------------------
        if refusals:
            d.ever_blocked = True
            self._log("EMERGENCY_REFUSED", by, decision=d.decision_id, reasons=refusals,
                      failures=failures, declared_class=d.execution_class,
                      execution_class=applied, coherence=score, factors=factors)
            return GateResult(d.decision_id, applied, False, False, bool(voids),
                              failures + [f"emergency justification refused: {r}"
                                          for r in refusals],
                              score, declared_class=d.execution_class)
        # --- Given: record every element, suspend, latch, open post-event ---
        ej_id = f"EJ{len(self.emergencies) + 1}"
        self.emergencies.append((ej_id, d.decision_id, tuple(modes), by, self.clock))
        self._log("EMERGENCY_JUSTIFICATION", by, emergency=ej_id, decision=d.decision_id,
                  consequence=consequence, time_estimate=ej.time_estimate,
                  options_considered=list(ej.options_considered),
                  best_evidence=list(ej.best_evidence), on_scene=ej.on_scene,
                  given_by=by, accepted_by=d.accepted_by, rationale=rationale,
                  holding_reviews=[r.review_id for r in holding], failure_modes=modes,
                  failures=failures, declared_class=d.execution_class,
                  execution_class=applied, coherence=score, factors=factors)
        for r in holding:
            r.suspended_by.append(ej_id)
            self._log("REVIEW_SUSPENDED", by, review=r.review_id, emergency=ej_id,
                      decision=d.decision_id,
                      reason="suspended, not resolved: it still produces its resolution "
                             "afterward")
        latched, annotated = self._latch(d, sigs, by, rationale, ej_id)
        # Element 5: the giver "is registered as steward of the off-envelope
        # loops for its duration (AP.1)". The latch already made the giver
        # steward of every loop it carried open; a loop behind an
        # off-envelope or containment hold that the gate counted as
        # resolved gets the same steward.
        for sig in held:
            if sig.signal_id not in latched + annotated and sig.steward != by:
                previous, sig.steward = sig.steward, by
                self._log("STEWARD_ASSIGNED", by, signal=sig.signal_id, steward=by,
                          previous=previous, decision=d.decision_id, emergency=ej_id,
                          reason="element 5: the giver stewards the loops behind the "
                                 "holding reviews for the emergency's duration")
        self._escalate(E.EMERGENCY_POST_EVENT, f"decision:{d.decision_id}",
                       f"mandatory post-event review of {ej_id}: did every element hold?",
                       list(d.signal_ids), by, decision_id=d.decision_id)
        d.executed = True
        result = GateResult(d.decision_id, applied, True, True, False, failures, score,
                            latched_signals=latched, declared_class=d.execution_class,
                            emergency_id=ej_id, annotated_signals=annotated)
        return result

    # ###########################################################################
    # ACT IX — READ-ONLY VIEWS
    # Look, don't touch: summaries for callers, reports and dashboards.
    # ###########################################################################

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------

    # =======================================================================
    # ACT IX, SCENE 1 — WHAT IS STILL UNDER REVIEW?
    # The unresolved structural reviews.
    # =======================================================================

    def open_reviews(self) -> list[StructuralReview]:
        """
        Every structural review not yet resolved.

        Enter:   (nothing)
        Exit:    a new list of the open StructuralReview objects, oldest first
        """
        return [r for r in self.reviews if not r.resolved]

    # =======================================================================
    # ACT IX, SCENE 2 — THE CURTAIN CALL
    # Counts of signals, closures, open reviews and audit entries.
    # =======================================================================

    def summary(self) -> dict:
        """
        A small dictionary of counts for reports and dashboards.

        Enter:   (nothing)
        Exit:    {"signals": commitment state -> count,
                  "closures": closure type -> count (attempted closures are
                              counted separately as "<type> (attempted)"),
                  "open_reviews": number of unresolved reviews,
                  "audit_entries": number of audit entries}
        Changes nothing.
        """
        # PLAYERS IN THIS SCENE
        #   by_state   commitment state name -> number of signals in it
        #   closures   closure type label -> number of closure records
        #   s, c       each signal, and each of its closure records
        #   key        the label a closure is counted under

        by_state: dict[str, int] = {}
        for s in self.signals.values():
            by_state[s.state.value] = by_state.get(s.state.value, 0) + 1
        closures: dict[str, int] = {}
        for s in self.signals.values():
            for c in s.closures:
                key = c.closure_type.value + (" (attempted)" if c.attempted_only else "")
                closures[key] = closures.get(key, 0) + 1
        # len(self.audit) works because AuditTrail defines __len__.
        return {"signals": by_state, "closures": closures,
                "open_reviews": len(self.open_reviews()), "audit_entries": len(self.audit)}

# EXEUNT — end of file.

"""
THE VOCABULARY
A Play in Two Acts
==================

PROLOGUE
--------
CCL-F v0.2 vocabulary as Python types.

Every name here comes from the CCL-F v0.2 working draft (Layer 2, Layer 4
and Key Definitions). Where the draft leaves a value open, the choice made
here is recorded in docs/DECISIONS.md and marked "implementation decision".

This file holds no behaviour of its own beyond a few small read-only
properties. It is the shared cast list: supervisor.py, statemachine.py,
advisor.py, graph.py and the tests all import these names so that every
part of the system spells "under_review" or "authority closure" the same way.

THE PLAYBILL (what happens in this file)
    ACT I — THE ENUMERATIONS (fixed lists of named values)
      Scene 1   SignalType            the six coordination signal types
      Scene 2   OperationalState      the five operational states
      Scene 3   CommitmentState       where a signal is in its lifecycle
                CLOSED_STATES         the three closed commitment states
      Scene 4   ExitType              the fourteen loop exit types
                EXIT_LEAVES_LOOP_OPEN exits after which the loop is still open
                CLOSING_EXITS         exits that close a loop of the other types
                EXTERNAL_EXITS        exits that continue in an external process
      Scene 5   LegalSubtype          the four legal-exit sub-types
      Scene 6   ClosureType           the four closure types
      Scene 7   EvidenceKind          what process produced a piece of evidence
                EES_ELIGIBLE_KINDS    kinds that can be External Evidence Sources
      Scene 8   Referent              technical reality vs. customer (Rule 5.3)
      Scene 9   ExecutionClass        irreversible / elevated / routine
      Scene 10  EscalationCondition   the ten automatic escalation conditions,
                                      plus the emergency post-event review
      Scene 11  AgentKind             person / unit / role / automation /
                                      instrument (Agent Admissibility)
                OBLIGATION_KINDS      kinds that can have obligation capacity
      Scene 12  EmergencyConsequence  the consequences an Emergency
                                      Justification may name
    ACT II — THE RECORDS (dataclasses that hold facts)
      Scene 1   Evidence              one item of evidence (frozen)
      Scene 2   ClosureRecord         one typed closure event (frozen)
      Scene 3   ExitRecord            one registered loop exit (frozen)
      Scene 3b  ClassificationRecord  one classification and its basis (frozen)
      Scene 3c  OutcomeRecord         one scored signal outcome (frozen)
      Scene 3d  OpenLoopAuthorization who carried a loop open (frozen)
      Scene 3e  EmergencyJustification  the five elements (frozen)
      Scene 3f  RiskAttestation       the risk evidence, attested (frozen)
      Scene 4   Signal                a coordination signal and its history
      Scene 5   Decision              an execution-class decision node
      Scene 6   Architecture          the registered Layer 0 architecture

READER'S NOTE — str-Enum
    `class SignalType(str, Enum)` makes an enumeration whose members are
    *also* real strings. SignalType.CONSTRAINT == "constraint" is True, and
    the member can be passed anywhere a str is expected (for example to
    json.dumps). SignalType("constraint") looks a member up by its value,
    which is how advisor.py turns a model's text reply into a member, and
    raises ValueError if no member has that value.

READER'S NOTE — frozenset
    A frozenset is a set that cannot be changed after it is made: no add(),
    no remove(). That makes it safe to share as a module-level constant
    (nobody can accidentally edit it) and makes it hashable, so it can be a
    default value in a dataclass. `x in some_frozenset` is a fast lookup.

READER'S NOTE — dataclasses
    @dataclass writes the boring parts of a class for you: an __init__ that
    takes each annotated field in order, a readable __repr__, and __eq__.
    @dataclass(frozen=True) additionally forbids assigning to a field after
    construction (it raises FrozenInstanceError). Frozen records here are
    things the audit trail treats as permanent facts: a piece of evidence,
    a closure, an exit. Signal, Decision and Architecture are *not* frozen
    because the supervisor updates them as events happen.

READER'S NOTE — field(default_factory=list)
    A default like `closures: list = []` would be one single list shared by
    every Signal ever created, so appending to one would append to all.
    field(default_factory=list) tells the dataclass to call list() afresh for
    each new object, so each Signal gets its own empty list.

READER'S NOTE — @property
    A method decorated with @property is read like an attribute, without
    parentheses: `sig.is_open`, not `sig.is_open()`. It is computed every
    time it is read, so it always reflects the signal's current state.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# __future__.annotations  stores type hints as text rather than evaluating
#                         them, so hints like `tuple[str, ...]` cost nothing
#                         at runtime.
# dataclass, field        build the record classes in ACT II (see READER'S
#                         NOTEs above).
# Enum                    base class for the fixed vocabularies in ACT I.
# Optional                Optional[X] means "an X, or None".
# ===========================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# This file has six module-level variables, and none of them can be
# hoisted up here: each is built from members of an Enum class that is
# defined further down the file, and Python runs a module top to bottom, so
# the class must exist before the constant can be made. Each one stays
# directly below the class it depends on, with a comment saying so:
#
#   CLOSED_STATES          (after CommitmentState)  the three closed states
#   EXIT_LEAVES_LOOP_OPEN  (after ExitType)         exits that leave a loop open
#   CLOSING_EXITS          (after ExitType)         exits that close an other-type loop
#   EXTERNAL_EXITS         (after ExitType)         exits to an external process
#   EES_ELIGIBLE_KINDS     (after EvidenceKind)     evidence kinds that can be EES
#   OBLIGATION_KINDS       (after AgentKind)        kinds with obligation capacity
# ===========================================================================


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

# ===========================================================================
# ACT I, SCENE 1 — THE SIX SIGNALS
# What kinds of coordination signal can enter the commitment process?
# ===========================================================================

class SignalType(str, Enum):
    """
    The six coordination signal types (Layer 1, Rule 1).

    Rule 1 ("Signals Needed for Responsible Action Are Visible") names
    exactly these six. A FRAMING signal is special: its content is an
    interpretive frame rather than a technical constraint, and its closure
    mechanism is frame adoption (Key Definitions, Framing Signal).
    """
    CONSTRAINT = "constraint"
    UNCERTAINTY = "uncertainty"
    ANOMALY = "anomaly"
    DISSENT = "dissent"
    CLASSIFICATION = "classification"
    FRAMING = "framing"


# ===========================================================================
# ACT I, SCENE 2 — THE FIVE CONDITIONS
# What condition is the system formally classified as being in?
# ===========================================================================

class OperationalState(str, Enum):
    """
    The five operational states (Rule 2; Key Definitions).

    Rule 2 ("Classification Precedes Action") requires every execution-class
    decision to have one of these explicitly, and says unvalidated conditions
    cannot be classified as NOMINAL. Per Key Definitions, a non-nominal state
    does not itself block execution; it decides which coordination
    requirements apply.
    """
    NOMINAL = "nominal"
    ELEVATED_UNCERTAINTY = "elevated_uncertainty"
    OFF_ENVELOPE = "off_envelope"
    EXPERIMENTAL = "experimental"
    CONTAINMENT = "containment"


# ===========================================================================
# ACT I, SCENE 3 — THE LIFECYCLE
# Where is a signal in the Layer 4 commitment state machine?
# ===========================================================================

class CommitmentState(str, Enum):
    """
    Lifecycle position of a coordination signal (Layer 4, Commitment State
    Machine). Exited signals carry their ExitType separately.

    The legal moves between these states live in statemachine.py
    (TRANSITIONS). Three states deserve a note:
      TRAJECTORY_LOCK  terminal and distinct from closure; it is how the spec
                       represents lock-in closure ("the machine deliberately
                       refuses to represent [it] as any form of closed").
                       The runtime no longer produces it at an override
                       (see EXECUTED_OPEN); the state and its transition
                       stay in the machine for analyses that find lock-in.
                       Since October 2026 the spec types lock: by override
                       (revision capacity existed, even produced a
                       revision, and an authorization reversed or
                       foreclosed it; Challenger) or by exhaustion (no one
                       could any longer revise before execution). Lock
                       describes reachability, not outcome. The runtime's
                       refusal of improper overrides is what stands
                       between an open decision and lock by override.
      EXECUTED_OPEN    terminal and distinct from closure: the POST-EXECUTION
                       LATCH. "When an irreversible decision executes under
                       an open-loop authorization, every loop it depends on
                       that the gate did not count as resolved moves to
                       `executed_open`, carrying the authorization record"
                       (Layer 4, Commitment State Machine).
      EXITED           one state for all fourteen exit types; which type it
                       was is kept in the signal's ExitRecord, not here.
    """
    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    CLASSIFIED = "classified"
    UNDER_REVIEW = "under_review"
    CLOSED_EVIDENCE = "closed_evidence"
    CLOSED_AUTHORITY = "closed_authority"
    CLOSED_ROLE_SWITCH = "closed_role_switch"
    SUPPRESSED = "suppressed"
    ESCALATED = "escalated"
    TRAJECTORY_LOCK = "trajectory_lock"
    EXECUTED_OPEN = "executed_open"
    EXITED = "exited"


# CLOSED_STATES — the three closed commitment states, one per closure type
#   that the state machine represents as "closed" (evidence, authority,
#   role-switch; lock-in is deliberately not among them, see above). Used to
#   ask "is this signal closed?" in one membership test, and by
#   statemachine.py for the blocked-closure and reopen rules ("Closed states
#   are stable but not terminal").
#   Cannot move to DRAMATIS PERSONAE: it is built from CommitmentState
#   members, and that class is only defined just above.
CLOSED_STATES = frozenset({
    CommitmentState.CLOSED_EVIDENCE,
    CommitmentState.CLOSED_AUTHORITY,
    CommitmentState.CLOSED_ROLE_SWITCH,
})


# ===========================================================================
# ACT I, SCENE 4 — FOURTEEN WAYS TO LEAVE
# How did a loop end without genuine closure?
# ===========================================================================

class ExitType(str, Enum):
    """
    The fourteen loop exit types (Layer 2, Loop Exit Taxonomy).

    An exit is how a loop ends *without* genuine evidence-based closure:
    abandoned, suspended, transferred or terminated. Per the taxonomy, the
    exit type decides what obligations survive the exit, what audit trail
    is required, and whether the loop can be re-entered (see
    statemachine.reentry_allowed).
    """
    TERMINAL = "terminal"
    CONTAINMENT = "containment"
    RECOVERABLE = "recoverable"
    SUPERSEDED = "superseded"
    DELEGATED = "delegated"
    DEFERRED = "deferred"
    FORCED = "forced"
    EXHAUSTION = "exhaustion"
    BOUNDARY = "boundary"
    TIMEOUT = "timeout"
    AMBIGUITY = "ambiguity"
    WHISTLEBLOWER = "whistleblower"
    LEGAL = "legal"
    KEY_PERSON = "key_person"


# EXIT_LEAVES_LOOP_OPEN — exit types after which the loop still counts as
#   open. Read by Signal.is_open below, so an exited-but-unresolved loop
#   still counts as open wherever is_open is asked (for example the
#   supervisor's coherence score). The irreversible gate itself asks a
#   different question and uses CLOSING_EXITS (a supersession, for the other
#   loop types) and a supersession with an External Evidence Source (for
#   constraint and anomaly loops) instead.
#   Cannot move to DRAMATIS PERSONAE: it is built from ExitType members,
#   and that class is only defined just above.
# Exit types whose "Loop State After" in the v0.2 Loop Exit Taxonomy is open
# (quarantined, paused, delegated, parked, ownerless or non-closable): the
# hazard the loop named is still unresolved, so the loop still counts as open.
EXIT_LEAVES_LOOP_OPEN = frozenset({
    ExitType.CONTAINMENT, ExitType.RECOVERABLE, ExitType.DELEGATED, ExitType.DEFERRED,
    ExitType.FORCED, ExitType.EXHAUSTION, ExitType.BOUNDARY, ExitType.AMBIGUITY,
    ExitType.KEY_PERSON,
})

# CLOSING_EXITS — exit types after which a loop of the OTHER types
#   (uncertainty, dissent, classification, framing) counts as not open at
#   the irreversible gate. Since the October 2026 cold read, only a
#   supersession: "none remains open: each is closed, by whatever closure
#   type, or has exited as superseded. A loop exited as terminal counts as
#   open for this test, since the exit records the loop's open state rather
#   than resolving it" (Layer 4, Execution Gates). Reversibility Logic says
#   the same: "Of the exits, only a supersession resolves a loop: for a
#   constraint or anomaly loop, one shown by an External Evidence Source"
#   (that stricter test is Supervisor._loop_resolved). TERMINAL and TIMEOUT
#   are therefore not in this set.
#   Cannot move to DRAMATIS PERSONAE: built from ExitType members.
CLOSING_EXITS = frozenset({ExitType.SUPERSEDED})

# EXTERNAL_EXITS — exits to a process outside this automaton: a
#   whistleblower exit continues in an external jurisdiction, a legal exit
#   under the external authority. Spec (Layer 4, Commitment State Machine,
#   the executed_open paragraph): "A loop exited to an external process
#   (whistleblower, legal) keeps that exit state, because it continues
#   elsewhere, and carries the authorization record as an annotation." The
#   latch (Supervisor._latch) annotates such loops instead of moving them.
#   Cannot move to DRAMATIS PERSONAE: built from ExitType members.
EXTERNAL_EXITS = frozenset({ExitType.WHISTLEBLOWER, ExitType.LEGAL})


# ===========================================================================
# ACT I, SCENE 5 — WHEN THE LAW STEPS IN
# Which kind of external authority produced a legal exit?
# ===========================================================================

class LegalSubtype(str, Enum):
    """
    The four legal-exit sub-types (Loop Exit Taxonomy notes).

    The Layer 4 listing says regulatory intervention and investigative hold
    "may resume to under_review when lifted", while judicial orders and
    statutory triggers depend on the order; statemachine.py encodes that.
    """
    REGULATORY_INTERVENTION = "regulatory_intervention"
    JUDICIAL_ORDER = "judicial_order"
    STATUTORY_TRIGGER = "statutory_trigger"
    INVESTIGATIVE_HOLD = "investigative_hold"


# ===========================================================================
# ACT I, SCENE 6 — HOW A LOOP WAS CLOSED
# On what basis was a closure recorded?
# ===========================================================================

class ClosureType(str, Enum):
    """
    The four closure types (Layer 2, Closure Quality).

      EVIDENCE     new data or analysis resolves the constraint     — valid
      AUTHORITY    a senior agent overrides without new evidence   — flagged
      ROLE_SWITCH  the same agent closes their own signal by
                   changing roles                                   — flagged
      LOCK_IN      authorization despite unresolved contradiction  — flagged,
                   trajectory lock indicator
    """
    EVIDENCE = "evidence"
    AUTHORITY = "authority"
    ROLE_SWITCH = "role_switch"
    LOCK_IN = "lock_in"


# ===========================================================================
# ACT I, SCENE 7 — WHERE EVIDENCE COMES FROM
# What kind of process produced this evidence, and can it be independent?
# ===========================================================================

class EvidenceKind(str, Enum):
    """
    What kind of process produced a piece of evidence. Used for the External
    Evidence Source test (Layer 2, EES): the first four kinds can qualify;
    model output never does ("multiple LLM instances ... do not constitute
    independent evidence").

    The first four mirror the spec's "What qualifies" list (formal or
    symbolic verification, primary source documents, direct measurement,
    evaluation by an independent party). A qualifying kind is necessary but
    not sufficient: the supervisor also checks that the evidence was not
    produced by the agent making the claim it is offered for, by the agent
    accepting the decision it supports, or by a process the claim evaluates
    (Supervisor.is_ees).
    """
    PRIMARY_DOCUMENT = "primary_document"
    DIRECT_MEASUREMENT = "direct_measurement"
    FORMAL_VERIFICATION = "formal_verification"
    INDEPENDENT_PARTY = "independent_party"
    INTERNAL_ANALYSIS = "internal_analysis"
    ASSERTION = "assertion"
    MODEL_OUTPUT = "model_output"


# EES_ELIGIBLE_KINDS — the evidence kinds that *can* count as an External
#   Evidence Source. The supervisor's is_ees() checks membership here first.
#   INTERNAL_ANALYSIS, ASSERTION and MODEL_OUTPUT are left out on purpose.
#   Cannot move to DRAMATIS PERSONAE: it is built from EvidenceKind members,
#   and that class is only defined just above.
EES_ELIGIBLE_KINDS = frozenset({
    EvidenceKind.PRIMARY_DOCUMENT,
    EvidenceKind.DIRECT_MEASUREMENT,
    EvidenceKind.FORMAL_VERIFICATION,
    EvidenceKind.INDEPENDENT_PARTY,
})


# ===========================================================================
# ACT I, SCENE 8 — TWO MASTERS
# Which referent is an agent consulting when they register or close?
# ===========================================================================

class Referent(str, Enum):
    """
    The two referents of Rule 5.3 (Dual Referent Divergence): the technical
    reality versus the customer as a contracting party. Role-switch closure is
    closing a signal by consulting a different referent than the one that
    generated it, with nothing new from either.

    The supervisor records ROLE_SWITCH when the closer is the registrant and
    the closer's referent differs from the registrant's (Key Definitions,
    Role-Switch Closure).
    """
    TECHNICAL = "technical"
    CUSTOMER = "customer"


# ===========================================================================
# ACT I, SCENE 9 — HOW MUCH IS AT STAKE
# Which execution gate applies to a decision?
# ===========================================================================

class ExecutionClass(str, Enum):
    """
    Execution classes for gating (Layer 4, Execution Gates).

      IRREVERSIBLE  constraint and anomaly loops evidence-closed; minimum
                    evidence closure ratio met for the other loops, none
                    left open; at least one External Evidence Source for the
                    principal risk claim; classification stabilized;
                    recurrence groups reviewed; coherence at or above
                    threshold
      ELEVATED      classification acknowledged; open loops documented
      ROUTINE       signal registration complete; Architecture
                    Precondition met

    A decision's declared class is not always the class its gate applies:
    per Execution Class Assignment, "Every execution-class decision is
    irreversible unless shown otherwise", so the supervisor gates a decision
    as IRREVERSIBLE unless a tested reversal path supports the lower class.
    """
    IRREVERSIBLE = "irreversible"
    ELEVATED = "elevated"
    ROUTINE = "routine"


# ===========================================================================
# ACT I, SCENE 10 — THE ALARMS
# Which conditions automatically escalate to structural review?
# ===========================================================================

class EscalationCondition(str, Enum):
    """
    The ten automatic escalation conditions (Layer 2), plus the mandatory
    post-event review of an Emergency Justification.

    One member per bullet of the Escalation Conditions list, in the spec's
    order: recurrence threshold (Rule 7); off-envelope or containment
    classification; authority-closure count on an irreversible decision;
    role-switch closure on a constraint; lock-in with open constraints;
    suppression before execution; framing adopted over open constraints;
    credibility discounting; repeated sender discount (AP-G); and an
    execution class lowered after a blocked request (Layer 4, Execution
    Class Assignment; added October 2026).

    EMERGENCY_POST_EVENT is not in the spec's list: it is the review the
    Overrides text makes mandatory after an Emergency Justification ("a
    mandatory post-event review records whether every element held").
    IMPLEMENTATION DECISION: it is modelled as a structural review so it
    sits in the same record, with the same resolver independence, as the
    others. It is opened over an executed decision, so it holds nothing.

    One spec bullet, "off-envelope or containment", is one member here,
    but the two triggers are resolved differently. The review records
    which one fired in StructuralReview.trigger (supervisor.py).
    """
    RECURRENCE_THRESHOLD = "recurrence_threshold"
    OFF_ENVELOPE_OR_CONTAINMENT = "off_envelope_or_containment"
    AUTHORITY_CLOSURE_COUNT = "authority_closure_count"
    ROLE_SWITCH_ON_CONSTRAINT = "role_switch_on_constraint"
    LOCK_IN_WITH_OPEN_CONSTRAINTS = "lock_in_with_open_constraints"
    SUPPRESSED_BEFORE_EXECUTION = "suppressed_before_execution"
    FRAMING_ADOPTED_OVER_OPEN_CONSTRAINTS = "framing_adopted_over_open_constraints"
    CREDIBILITY_DISCOUNTING = "credibility_discounting"
    SENDER_DISCOUNT_RECURRENCE = "sender_discount_recurrence"
    EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK = "execution_class_downgrade_after_block"
    EMERGENCY_POST_EVENT = "emergency_post_event"


# ===========================================================================
# ACT I, SCENE 11 — WHO OR WHAT IS ACTING?
# Which kind of agent is this, and can it hold an obligation?
# ===========================================================================

class AgentKind(str, Enum):
    """
    The kind of an agent, for Agent Admissibility (Layer 0).

      PERSON       a human being
      UNIT         an organizational unit
      ROLE         a role, held by successive occupants
      AUTOMATION   automated software: a monitor, a model at a version
      INSTRUMENT   a measuring instrument

    Spec (Layer 0, Agent Admissibility): "Persons and organizational units
    have obligation capacity. A role has it when a successor is registered
    under AP.1b, so that the obligation survives a change of occupant."
    Instruments, models and monitors have identity persistence but "cannot
    accept an obligation". Supervisor.obligation_capable() applies this;
    an agent never registered with a kind is treated as obligation-capable,
    so registries written before this enum keep working.
    """
    PERSON = "person"
    UNIT = "unit"
    ROLE = "role"
    AUTOMATION = "automation"
    INSTRUMENT = "instrument"


# OBLIGATION_KINDS — the agent kinds that can have obligation capacity.
#   PERSON and UNIT always have it; ROLE only with a registered successor
#   (see AgentKind). AUTOMATION and INSTRUMENT never do.
#   Cannot move to DRAMATIS PERSONAE: built from AgentKind members.
OBLIGATION_KINDS = frozenset({AgentKind.PERSON, AgentKind.UNIT, AgentKind.ROLE})


# ===========================================================================
# ACT I, SCENE 12 — HOW BAD WOULD WAITING BE?
# Which consequences can ground an Emergency Justification?
# ===========================================================================

class EmergencyConsequence(str, Enum):
    """
    Element 1 of an Emergency Justification (Layer 4, Execution Gates,
    Overrides): the consequence the hold would otherwise impose.

      LIFE_SAFETY_CATASTROPHIC       death or permanent total disability
                                     before the review could complete:
                                     MIL-STD-882E Severity Category 1, "by
                                     its life-safety criteria only"
      CVSS_CRITICAL_SAFETY_FUNCTION  for software and cyber-physical
                                     systems: an actively exploited
                                     weakness rated Critical (CVSS 9.0 to
                                     10.0) in a safety-critical function
                                     as MIL-STD-882E defines one

    There is deliberately no member for schedule, cost, contract,
    reputation, or the standard's monetary and environmental criteria:
    "Schedule, cost, contract, and reputation never qualify." A
    justification naming any other consequence cannot be built.
    """
    LIFE_SAFETY_CATASTROPHIC = "life_safety_catastrophic"
    CVSS_CRITICAL_SAFETY_FUNCTION = "cvss_critical_safety_function"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

# ===========================================================================
# ACT II, SCENE 1 — THE EXHIBIT
# Evidence: one permanent item of evidence
# ===========================================================================

@dataclass(frozen=True)
class Evidence:
    """
    One item of evidence.

    `produced_by` names the process that generated it; the EES test asks
    whether that process shares causal ancestry with the process under
    evaluation. `at` is the logical time it entered the record (the
    supervisor's clock), which the novelty test compares with registration.

    Fields:
      evidence_id   unique name for this item
      content       what the evidence says
      source        where it came from (a document, an instrument, a party)
      kind          an EvidenceKind; decides whether it can be EES at all
      produced_by   the process that generated it (EES independence test)
      at            supervisor clock tick when it was added (Evidence Novelty)
      depends_on    ids of the signals (coordination loops) this evidence
                    depends on: its upstream loops (Layer 2, Closure Chain).
                    An evidence closure that cites this item is chain-sound
                    only if every upstream loop is itself resolved: closed
                    by a chain-sound evidence closure, or exited as
                    superseded with an External Evidence Source, all the
                    way up.

    Frozen: once recorded, evidence cannot be edited in place. A dependency
    discovered later is added by Supervisor.add_dependency(), which stores
    a new copy of the record with the longer depends_on and logs it (as
    LATE_DEPENDENCY if a closure already cites the item).
    """
    evidence_id: str
    content: str
    source: str
    kind: EvidenceKind
    produced_by: str
    at: int = 0
    depends_on: tuple[str, ...] = ()


# ===========================================================================
# ACT II, SCENE 2 — THE CLOSURE ON RECORD
# ClosureRecord: one typed closure (or attempted closure)
# ===========================================================================

@dataclass(frozen=True)
class ClosureRecord:
    """
    A typed closure (or attempted closure) event on a signal.

    Fields:
      record_id        unique id for this closure ("C1", "C2", ...)
      signal_id        the signal it closes
      closure_type     a ClosureType (Layer 2, Closure Quality)
      closed_by        the agent who closed it
      closer_referent  which Referent the closer consulted, or None
      evidence_ids     the evidence cited (a tuple, so it cannot change)
      rationale        the stated reason
      at               supervisor clock tick
      attempted_only   True when the closer was outside the signal's closure
                       authority: per Key Definitions, an attempted closure
                       "is recorded as a coordination event but does not
                       constitute loop resolution"
      supersedes       id of an earlier record this one replaces, else None
                       (nothing in this package sets it yet; reopen() logs
                       the superseded record id in the audit trail instead)

    Frozen because reopening "does not erase the original closure record"
    (Commitment State Machine): a reopen adds history, it never edits it.
    `tuple[str, ...]` means "a tuple of any length whose items are str".
    """
    record_id: str
    signal_id: str
    closure_type: ClosureType
    closed_by: str
    closer_referent: Optional[Referent]
    evidence_ids: tuple[str, ...]
    rationale: str
    at: int
    attempted_only: bool = False
    supersedes: Optional[str] = None


# ===========================================================================
# ACT II, SCENE 3 — THE DEPARTURE ON RECORD
# ExitRecord: one registered loop exit and its obligations
# ===========================================================================

@dataclass(frozen=True)
class ExitRecord:
    """
    A registered loop exit, carrying its exit-type obligations.

    Fields (the optional ones answer the spec's "Exit obligations"):
      signal_id         the signal that exited
      exit_type         an ExitType
      by                the agent who registered the exit
      rationale         the stated reason
      open_loop_state   the loop's state at exit ("Terminal, legal, and key
                        person exits require explicit notation of the open
                        loop state at the time of exit")
      at                supervisor clock tick
      successor         new steward ("Delegated exits require successor
                        registration before the exit is valid")
      external_pathway  for whistleblower exits, the external escalation path
      suppression_ref   for whistleblower exits, the suppression event that
                        triggered it
      legal_subtype     for legal exits, which LegalSubtype applies
      resolution_condition  for containment, deferred and ambiguity exits,
                        what the loop is waiting for: "the loop re-enters
                        review when that condition is met"; without one it
                        has no re-entry path (Layer 2, Exit obligations)
      evidence_ids      evidence cited with the exit. For a superseded exit
                        it can show "that the context that generated it no
                        longer exists": with an External Evidence Source
                        among it, a superseded constraint or anomaly loop is
                        resolved at the irreversible gate and in the Closure
                        Chain (Layer 4, Execution Gates; Layer 2, Closure
                        Chain). Any exit may carry evidence; only that one
                        use reads it.
    """
    signal_id: str
    exit_type: ExitType
    by: str
    rationale: str
    open_loop_state: str
    at: int
    successor: Optional[str] = None
    external_pathway: Optional[str] = None
    suppression_ref: Optional[str] = None
    legal_subtype: Optional[LegalSubtype] = None
    resolution_condition: Optional[str] = None
    evidence_ids: tuple[str, ...] = ()


# ===========================================================================
# ACT II, SCENE 3b — THE CLASSIFICATION ON RECORD
# ClassificationRecord: one operational-state classification, with its basis
# ===========================================================================

@dataclass(frozen=True)
class ClassificationRecord:
    """
    One classification of a signal's operational state (Rule 2).

    Fields:
      at            supervisor clock tick
      state         the OperationalState actually applied (a refused
                    nominal is recorded as elevated uncertainty)
      by            the classifying agent: the claimant for the EES test
                    on its evidence ("the registering or reclassifying
                    agent, for a reversal path or a classification")
      evidence_ids  evidence cited for it
      proposed      the state that was asked for (differs from `state`
                    only when a nominal was refused)

    The gate reads the latest record of a nominal signal to check that its
    classification cites an External Evidence Source (Layer 4, Execution
    Gates, "Classification acknowledged").
    """
    at: int
    state: OperationalState
    by: str
    evidence_ids: tuple[str, ...]
    proposed: OperationalState


# ===========================================================================
# ACT II, SCENE 3c — THE OUTCOME ON RECORD
# OutcomeRecord: one scored outcome of an agent's signal (AP.7)
# ===========================================================================

@dataclass(frozen=True)
class OutcomeRecord:
    """
    Whether one of an agent's signals proved correct, and who said so.

    Fields:
      agent         whose signal it was
      correct       True if the signal's technical claim was confirmed
      scored_by     the agent who scored it
      evidence_ids  evidence cited for the score
      signal_id     the signal, if known
      at            supervisor clock tick

    Spec (Layer 4, Execution Gates, "Stable or improving accuracy rate"):
    "An outcome counts only if it was scored by a party that meets the
    External Evidence Source test with respect to the discounting agent:
    the agent whose discount is being judged cannot score the record that
    judges it." Supervisor._counted_outcomes applies that.
    """
    agent: str
    correct: bool
    scored_by: str
    evidence_ids: tuple[str, ...]
    signal_id: Optional[str]
    at: int


# ===========================================================================
# ACT II, SCENE 3d — THE OPEN LOOP, SIGNED FOR
# OpenLoopAuthorization: who carried a loop open through execution
# ===========================================================================

@dataclass(frozen=True)
class OpenLoopAuthorization:
    """
    The authorization record a latched loop carries into `executed_open`.

    Fields:
      decision_id   the irreversible decision that executed
      authorized_by the overrider, or the agent who gave the Emergency
                    Justification; now the loop's steward
      rationale     their stated rationale
      at            supervisor clock tick
      emergency_id  "EJ<n>" if the authorization was an Emergency
                    Justification, else None
      prior_state   the commitment state the loop was latched from (the
                    latch "does not erase a closure by authority or role
                    switch, which stays in the loop's history")

    Spec (Layer 4, Commitment State Machine): the loop moves to
    `executed_open`, "carrying the authorization record: who authorized,
    as steward of those loops, and on what rationale".
    """
    decision_id: str
    authorized_by: str
    rationale: str
    at: int
    emergency_id: Optional[str] = None
    prior_state: str = ""


# ===========================================================================
# ACT II, SCENE 3e — THE EMERGENCY, ARGUED ELEMENT BY ELEMENT
# EmergencyJustification: the five documented elements
# ===========================================================================

@dataclass(frozen=True)
class EmergencyJustification:
    """
    An Emergency Justification (Layer 4, Execution Gates, Overrides): the
    only way an irreversible decision held by off-envelope or containment
    reviews (or by an earlier justification's post-event review) may
    proceed before they are resolved.

    Fields (one per documented element; the agent giving it is the agent
    who calls request_execution):
      consequence         element 1: an EmergencyConsequence
      time_estimate       element 2: "A documented estimate shows the harm
                          would arrive before the review could be resolved"
      options_considered  element 3: "The intermediate options Rule 6
                          requires have been generated, and each is
                          documented as unavailable or worse" (non-empty)
      best_evidence       element 4: ids of "the best engineering evidence
                          available, recorded with it" (at least one; any
                          kind; each must be on record)
      on_scene            element 5: True when "the harm would arrive before
                          any second agent could be consulted" and the agent
                          on scene acts alone
      rationale           the stated rationale, recorded with each loop the
                          justification carries open

    Element 4's other half (an off-envelope condition classified
    experimental, "or containment, if it has since become one"; a
    containment condition kept in containment) is checked against the
    signals, not stated here. Under the on-scene proviso the record still
    carries every field: the contemporaneous record "stands in for the
    documentation of every element", and this record is how the runtime
    keeps it. The supervisor checks every element before execution and
    never reads an outcome: "The justification is judged by its elements,
    never by its outcome."
    """
    consequence: EmergencyConsequence
    time_estimate: str
    options_considered: tuple[str, ...]
    best_evidence: tuple[str, ...]
    on_scene: bool
    rationale: str = ""


# ===========================================================================
# ACT II, SCENE 3f — A SECOND PAIR OF EYES ON THE RISK CLAIM
# RiskAttestation: the evidence bears on the claim, says someone else
# ===========================================================================

@dataclass(frozen=True)
class RiskAttestation:
    """
    An independent attestation that the evidence cited in a Rule 4
    acceptance bears on its principal risk claim.

    Fields:
      by            the attesting agent
      rationale     why the evidence bears on the claim
      at            supervisor clock tick
      acceptor      the acceptance it was given for (the acceptor then)
      evidence_ids  the acceptance evidence it was given for

    Spec (Layer 4, Execution Gates, "At least one External Evidence Source
    for the principal risk claim"): "Whether the cited evidence bears on
    the claim is attested by an agent other than the acceptor who meets the
    independence conditions under Overrides, and the attestation stays in
    the record." Supervisor.attest_risk_evidence() records it; the gate
    re-checks the attester's independence when it runs.
    """
    by: str
    rationale: str
    at: int
    acceptor: str
    evidence_ids: tuple[str, ...]


# ===========================================================================
# ACT II, SCENE 4 — THE PROTAGONIST
# Signal: a coordination signal, its current state and its whole history
# ===========================================================================

@dataclass
class Signal:
    """
    A coordination signal: a safety-relevant input that has entered the
    commitment process and requires evidence-based closure before
    irreversible execution (Key Definitions).

    Fields set at registration:
      signal_id, signal_type, description
      registered_by             the registering agent
      registrant_referent       which Referent they registered from
      evaluated_process         the process the signal is about; evidence
                                produced by it is not EES
      steward, successor        the named steward and registered successor
                                (Key Definitions, Steward; AP.1a / AP.1b)
      closure_authority         agents allowed to close it; empty means any.
                                A closer outside it only *attempts* closure
      recurrence_group          the Recurrence Group it belongs to (Rule 7)
      failure_mode              the failure mode it names (Layer 0 checks)

    Fields the supervisor updates as events happen:
      state                     its CommitmentState
      operational_state         its OperationalState once classified
      registered_at             clock tick of registration (-1 = not yet)
      review_opened_at          clock tick review last opened (-1 = never)
      first_review_opened_at    clock tick review FIRST opened (-1 = never);
                                classification stability is judged from
                                here, so "closing and reopening a loop does
                                not restart it"
      classification_history    (tick, state) pairs; used to judge whether
                                classification was stable (Rule 3)
      classification_records    one ClassificationRecord per classification,
                                with who classified and the evidence cited
      open_loop_authorizations  every OpenLoopAuthorization that carried
                                this loop through an irreversible execution
                                (for a loop in an external exit, an
                                annotation: the loop keeps its exit state)
      resolving_reclassifications  clock ticks of reclassifications that
                                resolved an off-envelope review under its
                                trigger's standard; they do not destabilize
                                the classification (Layer 4, Execution
                                Gates, "Classification stabilized")
      evidence_ids              evidence linked to this signal
      evidence_at_registration  evidence already present at registration;
                                such evidence fails Evidence Novelty
      closures                  every ClosureRecord, including attempted
                                and superseded ones (nothing is erased)
      exit                      its ExitRecord, if it exited
      suppression_events        clock ticks at which it was suppressed
      reopen_count              how many times it has been reopened; the
                                spec calls this history "itself a
                                coordination signal"

    Not frozen: the supervisor changes these fields in place.
    """
    signal_id: str
    signal_type: SignalType
    description: str
    registered_by: str
    registrant_referent: Referent
    evaluated_process: str
    steward: Optional[str] = None
    successor: Optional[str] = None
    # A frozenset() default is safe without default_factory because it is
    # immutable: sharing one empty frozenset between all signals is harmless.
    closure_authority: frozenset[str] = frozenset()
    recurrence_group: Optional[str] = None
    failure_mode: Optional[str] = None
    state: CommitmentState = CommitmentState.UNREGISTERED
    operational_state: Optional[OperationalState] = None
    registered_at: int = -1
    review_opened_at: int = -1
    # Mutable lists need default_factory so each Signal gets its own list.
    classification_history: list[tuple[int, OperationalState]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    evidence_at_registration: frozenset[str] = frozenset()
    closures: list[ClosureRecord] = field(default_factory=list)
    exit: Optional[ExitRecord] = None
    suppression_events: list[int] = field(default_factory=list)
    reopen_count: int = 0
    first_review_opened_at: int = -1
    classification_records: list[ClassificationRecord] = field(default_factory=list)
    open_loop_authorizations: list[OpenLoopAuthorization] = field(default_factory=list)
    resolving_reclassifications: list[int] = field(default_factory=list)

    # -----------------------------------------------------------------------
    # ACT II, SCENE 4a — IS THE LOOP STILL OPEN?
    # -----------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        """
        Open = registered and not resolved: not closed, not latched in
        trajectory lock or executed_open, and not exited by an exit type
        that ends the loop. Exits that leave the loop open
        (EXIT_LEAVES_LOOP_OPEN) still count.

        Enter:   (none; read as `sig.is_open`, no parentheses)
        Exit:    True if the loop is open, else False

        The two latched states are not open: per Layer 4 each is a terminal
        marker of a loop carried open through irreversible execution ("After
        execution, then, no loop the decision depends on stands open, as if
        awaiting a review that can no longer change the outcome"). Callers
        that need them (for example the supervisor's coherence score) count
        them separately.
        """
        # --- Exited: open only if the exit type leaves the loop open -------
        if self.state == CommitmentState.EXITED:
            return self.exit is not None and self.exit.exit_type in EXIT_LEAVES_LOOP_OPEN
        # --- Otherwise: open unless closed, latched, or never registered ---
        return (self.state not in CLOSED_STATES
                and self.state not in (CommitmentState.TRAJECTORY_LOCK,
                                       CommitmentState.EXECUTED_OPEN,
                                       CommitmentState.UNREGISTERED))

    # -----------------------------------------------------------------------
    # ACT II, SCENE 4b — IS IT A CONSTRAINT?
    # -----------------------------------------------------------------------
    @property
    def is_constraint(self) -> bool:
        """
        Is this a constraint signal?

        Enter:   (none)
        Exit:    True for SignalType.CONSTRAINT

        The supervisor asks this for the rules that name constraint signals
        alone: the "Role-switch closure detected on a safety-constraint
        signal" escalation, and framing adopted while constraint signals
        remain open. (The irreversible gate covers constraint *and* anomaly
        loops, so it uses high_consequence instead.)
        """
        return self.signal_type == SignalType.CONSTRAINT

    # -----------------------------------------------------------------------
    # ACT II, SCENE 4c — DOES IT NAME A HIGH-CONSEQUENCE FAILURE MODE?
    # -----------------------------------------------------------------------
    @property
    def high_consequence(self) -> bool:
        """
        Constraint and anomaly signals name a high-consequence failure mode (D9).

        Enter:   (none)
        Exit:    True for CONSTRAINT and ANOMALY signals

        AP.1b and AP-A speak of a "high-consequence failure mode". Under
        implementation decision D9 (which Layer 0 sub-conditions a runtime
        can check), these two signal types are treated as naming one, and
        Supervisor.architecture_check skips the others. The same two types
        are the ones the irreversible gate holds to weakest link
        ("Constraint and anomaly loops evidence-closed").
        """
        return self.signal_type in (SignalType.CONSTRAINT, SignalType.ANOMALY)

    # -----------------------------------------------------------------------
    # ACT II, SCENE 4d — WHICH FAILURE MODE?
    # -----------------------------------------------------------------------
    @property
    def mode(self) -> str:
        """
        The failure mode used for Layer 0 checks.

        Enter:   (none)
        Exit:    failure_mode if set, else recurrence_group, else signal_id

        `a or b or c` returns the first value that is "truthy" (not None and
        not ""), so a signal with no named failure mode or group stands for
        its own failure mode. Architecture's dicts are keyed by this value.
        """
        return self.failure_mode or self.recurrence_group or self.signal_id


# ===========================================================================
# ACT II, SCENE 4b — AUTHORITY
# Power, Grant: who may recommend, authorize or execute a decision
# ===========================================================================

class Power(str, Enum):
    """
    What an agent may do with a decision.

      RECOMMEND   propose it; a recommendation changes no gate
      AUTHORIZE   give the Rule 4 acceptance (authorization, risk, rationale)
      EXECUTE     request execution at the gate
      OVERRIDE    proceed past the gate's overridable failures (open-loop
                  authorization); never held for a decision the same agent
                  accepted

    The three are separate on purpose: holding one never implies another,
    so a recommendation handed on is never an authorization, and an agent
    able to execute still needs someone else's (or its own, granted)
    authorization.
    """
    RECOMMEND = "recommend"
    AUTHORIZE = "authorize"
    EXECUTE = "execute"
    OVERRIDE = "override"


@dataclass(frozen=True)
class Grant:
    """
    One recorded grant of a power.

    Fields:
      grant_id     "G1", "G2", ... in order of granting
      grantee      the agent receiving the power
      power        the Power
      scope        the decision scope it covers ("*" for every scope)
      delegable    may the grantee grant this power on to others?
      granted_by   who granted it (a root, or a holder of a delegable grant)
      parent       the grant that let granted_by grant it; None if a root
                   granted it. A grant is valid only while its parent is.
      expires_at   wall-clock time (seconds since the epoch) after which it
                   is void, or None for no expiry; never later than its
                   parent's
      at           logical clock time it was recorded
    """
    grant_id: str
    grantee: str
    power: Power
    scope: str
    delegable: bool
    granted_by: str
    parent: Optional[str]
    expires_at: Optional[float]
    at: int


# ===========================================================================
# ACT II, SCENE 5 — THE DECISION
# Decision: an execution-class decision node awaiting its gate
# ===========================================================================

@dataclass
class Decision:
    """
    An execution-class decision node. Rule 4 requires a single agent to
    accept authorization, risk acceptance and rationale; `accepted_by` holds
    that agent once they have.

    Fields:
      decision_id            unique name
      description            what is being decided
      execution_class        the declared ExecutionClass; the gate applies
                             IRREVERSIBLE instead unless a tested reversal
                             path supports it (Execution Class Assignment)
      signal_ids             the signals this decision rests on
      accepted_by            the Rule 4 accepting agent, or None until then
      acceptance_rationale   their documented rationale ("" until accepted)
      executed               True once the gate has let it execute
      acceptance_evidence    ids of evidence cited in the Rule 4 acceptance;
                             the only place the irreversible gate looks for
                             the External Evidence Source for the principal
                             risk claim (Layer 4, Execution Gates)
      risk_claim             the principal risk claim named in the Rule 4
                             acceptance: "what must be true for the decision
                             to be safe to execute" ("" until named)
      acceptors              every agent who has ever accepted the decision,
                             in order (a re-acceptance never erases an
                             earlier acceptor: none of them may override,
                             give an off-scene Emergency Justification, or
                             resolve or attest for it)
      risk_attestation       the RiskAttestation that the acceptance's cited
                             evidence bears on the principal risk claim, or
                             None; a new acceptance (which may change the
                             evidence) voids it
      rule3_known, rule3_assumed, rule3_uncertain
                             the Rule 3 registration recorded with the
                             acceptance: "what is known, what is assumed,
                             and what remains genuinely uncertain" ("" until
                             recorded). The irreversible gate's
                             "classification stabilized" needs all three.
      class_setters          every agent who registered or reclassified the
                             decision; their evidence cannot show its
                             reversal path was tested
      reversal_path          the registered reversal path (free text), or None
      reversal_evidence      ids of evidence offered as showing the reversal
                             path was tested (Layer 4, Execution Class
                             Assignment)
      ever_blocked           True once any execution request on it was not
                             permitted; a lowering after that escalates
      scope                  the authority scope its powers are granted for
                             (a category such as "travel-booking"; defaults
                             to the decision id). With authority enforced,
                             only a root or a holder of delegable AUTHORIZE
                             over a scope may put a decision in it
      requesters             every agent who has requested its execution;
                             none of them, nor its accepting agent, may
                             resolve a structural review holding it
      acceptance_grant       the grant that backed the Rule 4 acceptance
                             (None for a root, or with authority not
                             enforced); the acceptance counts only while
                             that grant is in force
    """
    decision_id: str
    description: str
    execution_class: ExecutionClass
    signal_ids: list[str]
    accepted_by: Optional[str] = None
    acceptance_rationale: str = ""
    executed: bool = False
    acceptance_evidence: tuple[str, ...] = ()
    class_setters: tuple[str, ...] = ()
    reversal_path: Optional[str] = None
    reversal_evidence: tuple[str, ...] = ()
    ever_blocked: bool = False
    scope: str = ""
    acceptance_grant: Optional[str] = None
    requesters: set = field(default_factory=set)
    risk_claim: str = ""
    acceptors: tuple[str, ...] = ()
    risk_attestation: Optional[RiskAttestation] = None
    rule3_known: str = ""
    rule3_assumed: str = ""
    rule3_uncertain: str = ""


# ===========================================================================
# ACT II, SCENE 6 — THE STAGE ITSELF
# Architecture: the registered Layer 0 coordination architecture
# ===========================================================================

@dataclass
class Architecture:
    """
    The registered coordination architecture (Layer 0) for the failure modes
    a decision depends on. Only the sub-conditions a runtime can check from
    registered facts are modelled; see docs/DECISIONS.md.

    Each field is a dict keyed by failure mode (Signal.mode) or channel name:
      stewards            failure mode -> steward          (AP.1a / AP-A)
      successors          failure mode -> successor        (AP.1b)
      channels_tested     channel -> tested under load?    (AP.2: "Untested
                                                            channels are
                                                            treated as absent")
      reporters           failure mode -> parties who can report to decision
                          authority                        (AP-F)
      interested_parties  failure mode -> parties structurally interested in
                          denying it                       (AP-F: Captured
                                                            Channel)

    Every field uses field(default_factory=dict) so each Architecture gets
    its own empty dict (see READER'S NOTE above).
    """
    stewards: dict[str, str] = field(default_factory=dict)        # failure mode -> steward
    successors: dict[str, str] = field(default_factory=dict)      # failure mode -> successor
    channels_tested: dict[str, bool] = field(default_factory=dict)  # channel -> tested under load
    # failure mode -> parties with a reporting route to decision authority
    reporters: dict[str, set[str]] = field(default_factory=dict)
    # failure mode -> parties structurally interested in denying it
    interested_parties: dict[str, set[str]] = field(default_factory=dict)

# EXEUNT — end of file.

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
      Scene 5   LegalSubtype          the four legal-exit sub-types
      Scene 6   ClosureType           the four closure types
      Scene 7   EvidenceKind          what process produced a piece of evidence
                EES_ELIGIBLE_KINDS    kinds that can be External Evidence Sources
      Scene 8   Referent              technical reality vs. customer (Rule 5.3)
      Scene 9   ExecutionClass        irreversible / elevated / routine
      Scene 10  EscalationCondition   the ten automatic escalation conditions
    ACT II — THE RECORDS (dataclasses that hold facts)
      Scene 1   Evidence              one item of evidence (frozen)
      Scene 2   ClosureRecord         one typed closure event (frozen)
      Scene 3   ExitRecord            one registered loop exit (frozen)
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
# This file has four module-level variables, and none of them can be
# hoisted up here: each is built from members of an Enum class that is
# defined further down the file, and Python runs a module top to bottom, so
# the class must exist before the constant can be made. Each one stays
# directly below the class it depends on, with a comment saying so:
#
#   CLOSED_STATES          (after CommitmentState)  the three closed states
#   EXIT_LEAVES_LOOP_OPEN  (after ExitType)         exits that leave a loop open
#   RESOLVING_EXITS        (after ExitType)         exits that resolve a loop
#   EES_ELIGIBLE_KINDS     (after EvidenceKind)     evidence kinds that can be EES
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
    (TRANSITIONS). Two states deserve a note:
      TRAJECTORY_LOCK  terminal and distinct from closure; it is how the spec
                       represents lock-in closure ("the machine deliberately
                       refuses to represent [it] as any form of closed").
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
#   still blocks an irreversible gate (Reversibility Logic).
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

# RESOLVING_EXITS — exit types after which a constraint or anomaly loop
#   counts as resolved at the irreversible gate: the two whose Loop State
#   After is closed ("Closed by exit — permanently"; "Void — closed by
#   circumstance"). Every other exit leaves the gate requirement unmet,
#   including timeout, whistleblower and legal exits (Layer 4, Execution
#   Gates, "Constraint and anomaly loops evidence-closed").
#   Cannot move to DRAMATIS PERSONAE: built from ExitType members.
RESOLVING_EXITS = frozenset({ExitType.TERMINAL, ExitType.SUPERSEDED})


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
    produced by the process under evaluation or by the signal's registrant.
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

      IRREVERSIBLE  no open constraint loops; classification stabilized;
                    recurrence groups reviewed; minimum evidence closure
                    ratio met
      ELEVATED      classification acknowledged; open loops documented
      ROUTINE       signal registration complete
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
    The ten automatic escalation conditions (Layer 2).

    One member per bullet of the Escalation Conditions list, in the spec's
    order: recurrence threshold (Rule 7); off-envelope or containment
    classification; authority-closure count on an irreversible decision;
    role-switch closure on a constraint; lock-in with open constraints;
    suppression before execution; framing adopted over open constraints;
    credibility discounting; repeated sender discount (AP-G); and an
    execution class lowered after a blocked request (Layer 4, Execution
    Class Assignment; added October 2026).
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
                    A closure resting on it counts as evidence closure only
                    if every upstream loop is itself evidence-closed.

    Frozen: once recorded, evidence cannot be edited.
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
      classification_history    (tick, state) pairs; used to judge whether
                                classification was stable (Rule 3)
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

    # -----------------------------------------------------------------------
    # ACT II, SCENE 4a — IS THE LOOP STILL OPEN?
    # -----------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        """
        Open = registered and not resolved: not closed, not latched in
        trajectory lock, and not exited by an exit type that ends the loop.
        Exits that leave the loop open (EXIT_LEAVES_LOOP_OPEN) still count.

        Enter:   (none; read as `sig.is_open`, no parentheses)
        Exit:    True if the loop is open, else False

        Trajectory lock is not open: per Layer 4 it is a terminal marker that
        the loop "remained open at the point irreversible execution
        proceeded" — the gate logic counts it separately.
        """
        # --- Exited: open only if the exit type leaves the loop open -------
        if self.state == CommitmentState.EXITED:
            return self.exit is not None and self.exit.exit_type in EXIT_LEAVES_LOOP_OPEN
        # --- Otherwise: open unless closed, locked, or never registered ----
        return (self.state not in CLOSED_STATES
                and self.state not in (CommitmentState.TRAJECTORY_LOCK,
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

        The irreversible gate requires "No open constraint loops", so the
        supervisor asks this often.
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

        AP.1b and AP-A speak of "high-consequence failure modes". Under
        implementation decision D9 (which Layer 0 sub-conditions a runtime
        can check), these two signal types are treated as naming one, and
        Supervisor.architecture_check skips the others.
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
      execution_class        which Execution Gate applies (ExecutionClass)
      signal_ids             the signals this decision rests on
      accepted_by            the Rule 4 accepting agent, or None until then
      acceptance_rationale   their documented rationale ("" until accepted)
      executed               True once the gate has let it execute
      acceptance_evidence    ids of evidence cited in the Rule 4 acceptance;
                             it can supply the decision's External Evidence
                             Source (Layer 4, Execution Gates)
      class_setters          every agent who registered or reclassified the
                             decision; their evidence cannot show its
                             reversal path was tested
      reversal_path          the registered reversal path (free text), or None
      reversal_evidence      ids of evidence offered as showing the reversal
                             path was tested (Layer 4, Execution Class
                             Assignment)
      ever_blocked           True once any execution request on it was not
                             permitted; a lowering after that escalates
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

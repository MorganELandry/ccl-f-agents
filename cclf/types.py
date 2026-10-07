"""
CCL-F v0.2 vocabulary as Python types.

Every name here comes from the CCL-F v0.2 working draft (Layer 2, Layer 4
and Key Definitions). Where the draft leaves a value open, the choice made
here is recorded in docs/DECISIONS.md and marked "implementation decision".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SignalType(str, Enum):
    """The six coordination signal types (Layer 1, Rule 1)."""
    CONSTRAINT = "constraint"
    UNCERTAINTY = "uncertainty"
    ANOMALY = "anomaly"
    DISSENT = "dissent"
    CLASSIFICATION = "classification"
    FRAMING = "framing"


class OperationalState(str, Enum):
    """The five operational states (Rule 2; Key Definitions)."""
    NOMINAL = "nominal"
    ELEVATED_UNCERTAINTY = "elevated_uncertainty"
    OFF_ENVELOPE = "off_envelope"
    EXPERIMENTAL = "experimental"
    CONTAINMENT = "containment"


class CommitmentState(str, Enum):
    """
    Lifecycle position of a coordination signal (Layer 4, Commitment State
    Machine). Exited signals carry their ExitType separately.
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


CLOSED_STATES = frozenset({
    CommitmentState.CLOSED_EVIDENCE,
    CommitmentState.CLOSED_AUTHORITY,
    CommitmentState.CLOSED_ROLE_SWITCH,
})


class ExitType(str, Enum):
    """The fourteen loop exit types (Layer 2, Loop Exit Taxonomy)."""
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


# Exit types whose "Loop State After" in the v0.2 Loop Exit Taxonomy is open
# (quarantined, paused, delegated, parked, ownerless or non-closable): the
# hazard the loop named is still unresolved, so the loop still counts as open.
EXIT_LEAVES_LOOP_OPEN = frozenset({
    ExitType.CONTAINMENT, ExitType.RECOVERABLE, ExitType.DELEGATED, ExitType.DEFERRED,
    ExitType.FORCED, ExitType.EXHAUSTION, ExitType.BOUNDARY, ExitType.AMBIGUITY,
    ExitType.KEY_PERSON,
})


class LegalSubtype(str, Enum):
    """The four legal-exit sub-types (Loop Exit Taxonomy notes)."""
    REGULATORY_INTERVENTION = "regulatory_intervention"
    JUDICIAL_ORDER = "judicial_order"
    STATUTORY_TRIGGER = "statutory_trigger"
    INVESTIGATIVE_HOLD = "investigative_hold"


class ClosureType(str, Enum):
    """The four closure types (Layer 2, Closure Quality)."""
    EVIDENCE = "evidence"
    AUTHORITY = "authority"
    ROLE_SWITCH = "role_switch"
    LOCK_IN = "lock_in"


class EvidenceKind(str, Enum):
    """
    What kind of process produced a piece of evidence. Used for the External
    Evidence Source test (Layer 2, EES): the first four kinds can qualify;
    model output never does ("multiple LLM instances ... do not constitute
    independent evidence").
    """
    PRIMARY_DOCUMENT = "primary_document"
    DIRECT_MEASUREMENT = "direct_measurement"
    FORMAL_VERIFICATION = "formal_verification"
    INDEPENDENT_PARTY = "independent_party"
    INTERNAL_ANALYSIS = "internal_analysis"
    ASSERTION = "assertion"
    MODEL_OUTPUT = "model_output"


EES_ELIGIBLE_KINDS = frozenset({
    EvidenceKind.PRIMARY_DOCUMENT,
    EvidenceKind.DIRECT_MEASUREMENT,
    EvidenceKind.FORMAL_VERIFICATION,
    EvidenceKind.INDEPENDENT_PARTY,
})


class Referent(str, Enum):
    """
    The two referents of Rule 5.3 (Dual Referent Divergence): the technical
    reality versus the customer as a contracting party. Role-switch closure is
    closing a signal by consulting a different referent than the one that
    generated it, with nothing new from either.
    """
    TECHNICAL = "technical"
    CUSTOMER = "customer"


class ExecutionClass(str, Enum):
    """Execution classes for gating (Layer 4, Execution Gates)."""
    IRREVERSIBLE = "irreversible"
    ELEVATED = "elevated"
    ROUTINE = "routine"


class EscalationCondition(str, Enum):
    """The nine automatic escalation conditions (Layer 2)."""
    RECURRENCE_THRESHOLD = "recurrence_threshold"
    OFF_ENVELOPE_OR_CONTAINMENT = "off_envelope_or_containment"
    AUTHORITY_CLOSURE_COUNT = "authority_closure_count"
    ROLE_SWITCH_ON_CONSTRAINT = "role_switch_on_constraint"
    LOCK_IN_WITH_OPEN_CONSTRAINTS = "lock_in_with_open_constraints"
    SUPPRESSED_BEFORE_EXECUTION = "suppressed_before_execution"
    FRAMING_ADOPTED_OVER_OPEN_CONSTRAINTS = "framing_adopted_over_open_constraints"
    CREDIBILITY_DISCOUNTING = "credibility_discounting"
    SENDER_DISCOUNT_RECURRENCE = "sender_discount_recurrence"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Evidence:
    """
    One item of evidence.

    `produced_by` names the process that generated it; the EES test asks
    whether that process shares causal ancestry with the process under
    evaluation. `at` is the logical time it entered the record (the
    supervisor's clock), which the novelty test compares with registration.
    """
    evidence_id: str
    content: str
    source: str
    kind: EvidenceKind
    produced_by: str
    at: int = 0


@dataclass(frozen=True)
class ClosureRecord:
    """A typed closure (or attempted closure) event on a signal."""
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


@dataclass(frozen=True)
class ExitRecord:
    """A registered loop exit, carrying its exit-type obligations."""
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


@dataclass
class Signal:
    """
    A coordination signal: a safety-relevant input that has entered the
    commitment process and requires evidence-based closure before
    irreversible execution (Key Definitions).
    """
    signal_id: str
    signal_type: SignalType
    description: str
    registered_by: str
    registrant_referent: Referent
    evaluated_process: str
    steward: Optional[str] = None
    successor: Optional[str] = None
    closure_authority: frozenset[str] = frozenset()
    recurrence_group: Optional[str] = None
    failure_mode: Optional[str] = None
    state: CommitmentState = CommitmentState.UNREGISTERED
    operational_state: Optional[OperationalState] = None
    registered_at: int = -1
    review_opened_at: int = -1
    classification_history: list[tuple[int, OperationalState]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    evidence_at_registration: frozenset[str] = frozenset()
    closures: list[ClosureRecord] = field(default_factory=list)
    exit: Optional[ExitRecord] = None
    suppression_events: list[int] = field(default_factory=list)
    reopen_count: int = 0

    @property
    def is_open(self) -> bool:
        """
        Open = registered and not resolved: not closed, not latched in
        trajectory lock, and not exited by an exit type that ends the loop.
        Exits that leave the loop open (EXIT_LEAVES_LOOP_OPEN) still count.
        """
        if self.state == CommitmentState.EXITED:
            return self.exit is not None and self.exit.exit_type in EXIT_LEAVES_LOOP_OPEN
        return (self.state not in CLOSED_STATES
                and self.state not in (CommitmentState.TRAJECTORY_LOCK,
                                       CommitmentState.UNREGISTERED))

    @property
    def is_constraint(self) -> bool:
        return self.signal_type == SignalType.CONSTRAINT

    @property
    def high_consequence(self) -> bool:
        """Constraint and anomaly signals name a high-consequence failure mode (D9)."""
        return self.signal_type in (SignalType.CONSTRAINT, SignalType.ANOMALY)

    @property
    def mode(self) -> str:
        """The failure mode used for Layer 0 checks."""
        return self.failure_mode or self.recurrence_group or self.signal_id


@dataclass
class Decision:
    """
    An execution-class decision node. Rule 4 requires a single agent to
    accept authorization, risk acceptance and rationale; `accepted_by` holds
    that agent once they have.
    """
    decision_id: str
    description: str
    execution_class: ExecutionClass
    signal_ids: list[str]
    accepted_by: Optional[str] = None
    acceptance_rationale: str = ""
    executed: bool = False


@dataclass
class Architecture:
    """
    The registered coordination architecture (Layer 0) for the failure modes
    a decision depends on. Only the sub-conditions a runtime can check from
    registered facts are modelled; see docs/DECISIONS.md.
    """
    stewards: dict[str, str] = field(default_factory=dict)        # failure mode -> steward
    successors: dict[str, str] = field(default_factory=dict)      # failure mode -> successor
    channels_tested: dict[str, bool] = field(default_factory=dict)  # channel -> tested under load
    # failure mode -> parties with a reporting route to decision authority
    reporters: dict[str, set[str]] = field(default_factory=dict)
    # failure mode -> parties structurally interested in denying it
    interested_parties: dict[str, set[str]] = field(default_factory=dict)

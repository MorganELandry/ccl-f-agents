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
        Scene 2   Settings                 the tunable thresholds (D1, D3-D6)
        Scene 3   StructuralReview         one automatic escalation (Rules 7-8)
        Scene 4   GateResult               the outcome of an execution request
        Scene 5   Supervisor.__init__      the supervisor's own records
        Scene 6   _tick                    advance the logical clock
        Scene 7   _log                     write one audit entry
        Scene 8   _require_actor           no anonymous operations
        Scene 9   _decision                look up a decision or refuse
        Scene 10  _signal                  look up a signal or refuse
        Scene 11  _move                    the only door through the state machine
    ACT II — EVIDENCE AND ARCHITECTURE
        Scene 1   is_novel                 Evidence Novelty (Layer 2)
        Scene 2   is_ees                   External Evidence Source (Layer 2)
        Scene 2b  _qualifying, _closure_sound, _signal_sound, chain_sound
                                           Closure Chain: sound all the way up?
        Scene 3   register_architecture    record the Layer 0 facts
        Scene 4   add_evidence             record one item of evidence
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
        Scene 3   _check_recurrence        Rule 7: recurrence group threshold
        Scene 4   _check_authority_count   authority closures on irreversible decisions
        Scene 5   resolve_review           Rule 8: a model update, not a re-approval
    ACT VII — SOURCE STANDING (AP.7, CREDIBILITY DISCOUNTING, AP-G)
        Scene 1   record_signal_outcome    log whether an agent's signal proved right
        Scene 2   accuracy_stable_or_improving  the accuracy test (D7)
        Scene 3   discount_supported_by_record  is a discount earned by the record?
        Scene 4   record_credibility_discount   detect shooting the messenger
    ACT VIII — DECISIONS, COHERENCE AND EXECUTION GATES
        Scene 1   register_decision        create a decision node
        Scene 1b  _check_evidence_ids, _reversal_supported, _applied_class,
                  effective_class, reclassify_decision
                                           Execution Class Assignment
        Scene 2   link_signal              attach a signal to a decision
        Scene 2b  holds, grant, revoke,    who may recommend, authorize, execute;
                  recommend                chains of grants, revocation, expiry
        Scene 3   accept_decision          Rule 4: a single named accepting agent
        Scene 4   _decision_signals        the decision's known signals
        Scene 5   _classification_stable   D8: has the classification settled?
        Scene 6   coherence                the Layer 4 coherence score (D3)
        Scene 7   architecture_check       the Layer 0 voids a runtime can see (D9)
        Scene 7b  _gate_resolved, _decision_ees   the irreversible gate's
                                           loop and evidence tests
        Scene 8   request_execution        the execution gates and overrides
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
# dataclass, field        build simple record classes (see ACT I READER'S
#                         NOTEs on dataclasses and field(default_factory)).
# Iterable, Optional      type hints (see the READER'S NOTE above).
# AuditTrail              the append-only, hash-chained log (audit.py).
# check_transition        is current -> target in the v0.2 transition table?
# exit_allowed            may a signal in this state exit?
# reentry_allowed         may an exited signal of this exit type re-enter?
# types                   the v0.2 vocabulary. Three are given short aliases:
#                         S = CommitmentState (lifecycle position),
#                         E = EscalationCondition (the ten Layer 2 triggers),
#                         O = OperationalState (the five Rule 2 states).
#                         EES_ELIGIBLE_KINDS lists the evidence kinds that can
#                         be an External Evidence Source; CLOSED_STATES is the
#                         set of the three closed commitment states;
#                         RESOLVING_EXITS is the exit types whose Loop State
#                         After is closed (terminal, superseded), used by the
#                         irreversible gate (ACT VIII, Scene 7b).
# ===========================================================================

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from .audit import AuditTrail
from .statemachine import check_transition, exit_allowed, reentry_allowed
from .types import (
    Architecture, ClosureRecord, ClosureType, CommitmentState as S, Decision,
    EES_ELIGIBLE_KINDS, EscalationCondition as E, Evidence, ExecutionClass,
    ExitRecord, ExitType, Grant, LegalSubtype, OperationalState as O, Power, Referent,
    Signal, SignalType, CLOSED_STATES, RESOLVING_EXITS,
)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# The five DEFAULT_ thresholds below are labelled implementation decisions
# (D1 and D3-D6, see docs/DECISIONS.md). The spec names each threshold; it
# gives no value for four of them, and since October 2026 it states the
# AP-G threshold (D6) itself as three. They are only the defaults: the
# Settings dataclass (ACT I, Scene 2) copies them, and a caller can pass
# different values per Supervisor. The last three variables are fixed
# lookup tables taken from the spec.
# ===========================================================================

# DEFAULT_RECURRENCE_THRESHOLD — how many signals in one recurrence group
#   trigger the Rule 7 structural review (ACT VI, Scene 3).
#   Spec: Rule 7 ("What to do") says review is "mandatory and automatic"
#   once a group "crosses the escalation threshold" but gives no number.
#   IMPLEMENTATION DECISION D1: 3, taken from the Challenger case in Rule 7
#   ("Cases"): "The escalation threshold was crossed after the third
#   occurrence."
DEFAULT_RECURRENCE_THRESHOLD = 3        # D1: Challenger "crossed after the third occurrence"

# DEFAULT_AUTHORITY_CLOSURE_THRESHOLD — the escalation condition "Authority
#   closure count exceeds threshold on an irreversible decision" (Layer 2,
#   Escalation Conditions) needs a number.
#   IMPLEMENTATION DECISION D5: 1, so the second authority closure on an
#   irreversible decision's signals escalates (the test is "count > 1").
DEFAULT_AUTHORITY_CLOSURE_THRESHOLD = 1  # D5: escalate when count exceeds this

# DEFAULT_SENDER_DISCOUNT_THRESHOLD — how many unsupported credibility
#   discounts against one agent (discounts not earned by a poor or
#   declining accuracy record) turn into AP-G, the Sender Discount void.
#   Spec (Layer 2, Credibility Discounting, "AP-G threshold"): "The
#   threshold is three: AP-G is reached at the third credibility-discounting
#   event against the same registering agent during which that agent's
#   signals show a stable or improving accuracy rate."
#   D6: 3, the spec's own number (and the same number as D1).
DEFAULT_SENDER_DISCOUNT_THRESHOLD = 3   # D6: "The threshold is three"

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

@dataclass
class Settings:
    """
    The tunable thresholds, one Supervisor at a time.

    Each default comes from the DRAMATIS PERSONAE above (labelled
    implementation decisions D1, D3-D6; the spec names the thresholds and
    sets a value only for the AP-G threshold, three, which D6 follows).

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
    practice". `model_update` holds that update once
    resolve_review() (ACT VI, Scene 5) closes the review.

    Fields:
        review_id     "R1", "R2", ... in order of opening
        condition     which of the ten escalation conditions fired
        scope         what the review is about: a signal id, "group:<id>",
                      "agent:<id>" or "decision:<id>"
        detail        human-readable description of why it fired
        opened_at     the logical clock when it opened
        signal_ids    the signals it holds in `escalated` (may be empty)
        resolved_by   the agent who resolved it, or None while open
        model_update  the Rule 8 coordination model update ("" while open)

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
        locked_signals     constraint signals latched into trajectory_lock by
                           an override (see request_execution)
        declared_class     the class the decision declares; execution_class
                           above is the class the gate APPLIED, which is
                           irreversible unless a tested reversal path
                           supports the declared one (Execution Class
                           Assignment)
    """
    decision_id: str
    execution_class: ExecutionClass
    permitted: bool
    overridden: bool
    architecture_void: bool
    failures: list[str]
    coherence: float
    locked_signals: list[str] = field(default_factory=list)
    declared_class: Optional[ExecutionClass] = None


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
    discount_supported_by_record, open_reviews, summary) take no actor and
    write nothing.
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
        Exit:    a Supervisor with no signals, evidence, decisions or reviews

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
            accuracy              agent -> list of True/False signal outcomes (AP.7)
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
        self.accuracy: dict[str, list[bool]] = {}      # agent -> signal outcomes
        self.discounts: dict[str, int] = {}            # agent -> discount count
        self.unsupported_discounts: dict[str, int] = {}  # agent -> AP-G count
        self.sender_discount_void: set[str] = set()    # agents under AP-G
        self.clock = 0
        self._closure_seq = 0

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
        self._log("TRANSITION", actor, signal=sig.signal_id,
                  **{"from": previous, "to": target, "rule": reason}, **payload)

    # ###########################################################################
    # ACT II — EVIDENCE AND ARCHITECTURE
    # The two evidence tests that closure typing relies on, and the
    # operations that record evidence and the Layer 0 architecture.
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

    def is_ees(self, ev: Evidence, sig: Signal) -> bool:
        """
        External Evidence Source: an eligible kind of evidence, produced by a
        process causally independent of the one under evaluation and of the
        signal's registrant. Model output never qualifies.

        Enter:   ev    the evidence
                 sig   the signal it is offered against
        Exit:    True if the evidence counts as an External Evidence Source

        Spec: Layer 2, External Evidence Source (EES). A source
        is an EES "only if the source's output is causally independent of
        the reasoning process that produced the signal being evaluated."
        What qualifies: "Independent formal or symbolic verification,
        primary source documents, direct measurement or observation, and
        evaluation by a party with no causal relationship to the process".
        What does not: "multiple LLM instances ... do not constitute
        independent evidence". Why the spec has it: confirmations that share
        a causal ancestry are "common-mode", "the same non-evidence counted
        more than once".

        IMPLEMENTATION DECISION (EES operationalized as evidence kind +
        producing process): the spec's test is about causal ancestry, which
        a runtime cannot see. Here it becomes two checks on recorded facts:
          1. the evidence's `kind` is in EES_ELIGIBLE_KINDS (primary
             document, direct measurement, formal verification, independent
             party; never model output, internal analysis or assertion), and
          2. the process named in `produced_by` is neither the signal's
             `evaluated_process` nor the agent who registered the signal.
        The result is only as good as the `kind` and `produced_by` that were
        recorded.
        """
        return (ev.kind in EES_ELIGIBLE_KINDS
                and ev.produced_by not in (sig.evaluated_process, sig.registered_by))

    # =======================================================================
    # ACT II, SCENE 2b — IS IT SOUND ALL THE WAY UP?
    # Closure Chain: an evidence closure is only as good as the loops its
    # evidence depends on.
    # =======================================================================

    def _qualifying(self, rec: ClosureRecord, sig: Signal) -> list[Evidence]:
        """
        The cited evidence that made a closure an evidence closure.

        Enter:   rec   a closure record on `sig`
                 sig   the signal it closed
        Exit:    the cited Evidence items that are both novel and EES

        Recomputed from the record rather than stored: evidence is frozen
        and a signal's registration time never changes, so the answer is
        the same as at closure time.
        """
        return [self.evidence[e] for e in rec.evidence_ids
                if e in self.evidence and self.is_novel(self.evidence[e], sig)
                and self.is_ees(self.evidence[e], sig)]

    def _closure_sound(self, rec: ClosureRecord, sig: Signal, seen: frozenset) -> bool:
        """
        Is this closure a chain-sound evidence closure?

        Enter:   rec    a closure record on `sig`
                 sig    the signal it closed
                 seen   signal ids already on the path being checked (to
                        catch cycles)
        Exit:    True only for a real (not attempted) evidence closure with
                 at least one qualifying item whose every upstream loop is
                 itself chain-sound

        Spec: Layer 2, Closure Chain: "An evidence closure is chain-sound
        only if at least one item of qualifying evidence it cites has every
        upstream loop itself chain-sound: closed by evidence closure, all
        the way up. A loop cannot be its own upstream, directly or through
        others."

        `all(...)` over an empty list is True, so evidence with no
        upstream loops is sound on its own.
        """
        # PLAYERS IN THIS SCENE
        #   path   `seen` plus this signal: what the upstream checks must avoid

        if rec.attempted_only or rec.closure_type != ClosureType.EVIDENCE:
            return False
        path = seen | {sig.signal_id}
        return any(all(self._signal_sound(up, path) for up in ev.depends_on)
                   for ev in self._qualifying(rec, sig))

    def _signal_sound(self, signal_id: str, seen: frozenset) -> bool:
        """
        Is this signal currently closed by a chain-sound evidence closure?

        Enter:   signal_id   the signal to check
                 seen        signal ids already on the path (cycle guard)
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
        return self._closure_sound(latest, sig, seen)

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
        one EES-qualifying item among the cited evidence; otherwise the
        classification is recorded as elevated uncertainty and the refusal
        is audited.

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
        passes is_ees(). Novelty is not required here. The runtime cannot
        check what the evidence actually says, only its kind and who
        produced it; a rejected nominal is downgraded to
        elevated_uncertainty rather than refused outright.

        Effects:
          - the first classification moves registered -> classified (Layer 4:
            "registered -> classified (Rule 2: required before review opens)");
            later reclassifications just update the operational state
          - every classification is appended to classification_history,
            which _classification_stable() (ACT VIII, Scene 5) reads
          - off_envelope or containment escalates to structural review
            (Layer 2, Escalation Conditions: "Operational state classified
            as off-envelope or containment")
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
        if state == O.NOMINAL and not any(self.is_ees(ev, sig) for ev in cited):
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
        self._log("CLASSIFIED", by, signal=signal_id, operational_state=applied,
                  evidence=list(evidence_ids), proposed_by_model=proposed_by_model)
        # --- Escalation condition: off-envelope or containment -------------
        # If the signal is not under review yet, _escalate() only records the
        # review; the signal is escalated when it reaches review
        # (_apply_pending_escalations, ACT VI, Scene 2).
        if applied in (O.OFF_ENVELOPE, O.CONTAINMENT):
            self._escalate(E.OFF_ENVELOPE_OR_CONTAINMENT, signal_id,
                           f"classified {applied.value}", [signal_id], by)
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
        analysis opened)". Recording `review_opened_at` matters
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
          - at least one cited item both novel and EES -> evidence closure
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
          (Lock-in closure is created only by a gate override; see ACT VIII,
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
        qualifying = [ev.evidence_id for ev in cited
                      if self.is_novel(ev, sig) and self.is_ees(ev, sig)]
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
        #   broken      upstream loops of its qualifying evidence that are not
        #               chain-sound (the broken links)
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
        # the record". broken_links names each upstream loop of the
        # qualifying evidence that is not itself chain-sound right now.
        chain_ok, broken = None, []
        if ctype == ClosureType.EVIDENCE:
            chain_ok = self._closure_sound(record, sig, frozenset())
            broken = sorted({up for ev in self._qualifying(record, sig)
                             for up in ev.depends_on
                             if not self._signal_sound(up, frozenset({signal_id}))})
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
        do update it), so classification stability is still measured from
        the earlier review opening.
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
             resolution_condition: Optional[str] = None) -> ExitRecord:
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
                            resolution_condition)
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
                  resolution_condition=resolution_condition)
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
                  signal_ids: list[str], actor: str) -> StructuralReview:
        """
        Open a structural review for one of the ten escalation conditions.

        Enter:   condition    which escalation condition fired
                 scope        what it is about (see StructuralReview.scope)
                 detail       human-readable explanation
                 signal_ids   signals to hold in `escalated` (may be empty)
                 actor        the agent whose operation triggered it
        Exit:    the StructuralReview (new, or the existing open one)

        Spec: Layer 2, Escalation Conditions: these "automatically escalate
        to structural review". Rule 7 ("What to do"): "mandatory and
        automatic — not a judgment call subject to schedule pressure or
        institutional momentum." Layer 4 state machine: "under_review ->
        escalated".

        IMPLEMENTATION DECISION (one open review per condition and scope):
        if an unresolved review already exists for the same condition and
        scope, the new signals are added to it, a REVIEW_JOINED entry is
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

        # One open review per (condition, scope): a repeat adds to it.
        for existing in self.reviews:
            if (not existing.resolved and existing.condition == condition
                    and existing.scope == scope):
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
                                  self.clock, list(signal_ids))
        self.reviews.append(review)
        self._log("ESCALATION", actor, review=review.review_id, condition=condition,
                  scope=scope, detail=detail, signals=list(signal_ids))
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
        ... When a recurrence group crosses the escalation threshold,
        structural review is mandatory and automatic." Why: each recurrence
        "closed by authority" separately means "the pattern never
        accumulates into a recognized signal" (seven Challenger O-ring
        erosion missions). Recurrence Group (Key Definitions):
        "linked coordination signals sharing a common failure mode".
        Threshold: D1 (Settings.recurrence_threshold, default 3). The test
        is "members >= threshold", so the third member triggers it.

        IMPLEMENTATION DECISION (a resolved group stays reviewed): once a
        group's review has been resolved (Rule 8 update documented), the
        group is in reviewed_groups and later members do not open a new
        review.
        """
        # PLAYERS IN THIS SCENE
        #   group         the signal's recurrence group (or None)
        #   members       ids of every registered signal in that group
        #   open_review   the group's unresolved review, or None

        group = sig.recurrence_group
        if group is None or group in self.reviewed_groups:
            return
        members = [s.signal_id for s in self.signals.values() if s.recurrence_group == group]
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
    # ACT VI, SCENE 5 — THE MODEL IS UPDATED
    # Rule 8: resolve a review with a documented coordination model update.
    # =======================================================================

    def resolve_review(self, review_id: str, by: str, model_update: str) -> None:
        """
        Rule 8: the structural review must produce a documented update to the
        coordination model, not a re-approval. Escalated signals named by the
        review recover to under_review.

        Enter:   review_id      an open review ("R<n>")
                 by             the resolving agent
                 model_update   the documented coordination model update
                                (must not be blank)
        Exit:    None; the review is resolved, a group review marks its
                 group as reviewed, and named escalated signals that no
                 other open review holds return to under_review

        Spec: Rule 8, Systems Should Update Through Stress: "Rule 8 requires that the review
        produce a documented update to the coordination model — not a
        re-approval of existing practice." Why: otherwise the organization
        "learns the wrong lesson" (normalization of deviance). Layer 4
        recovery transition: "escalated -> under_review (Rule 8 model
        update documented)".

        The runtime can only check that an update was written down, not
        that it is a real change rather than a re-approval in other words.
        """
        # PLAYERS IN THIS SCENE
        #   review       the review being resolved
        #   sid          each signal id it names
        #   sig          that signal, or None if unknown
        #   still_held   True if another unresolved review also names it

        self._require_actor(by)
        if not model_update.strip():
            raise TransitionRefused("Rule 8: a structural review must document a "
                                    "coordination model update")
        self._tick()
        # --- Find the review -----------------------------------------------
        review = next((r for r in self.reviews if r.review_id == review_id), None)
        if review is None:
            raise TransitionRefused(f"unknown review {review_id!r}")
        if review.resolved:
            raise TransitionRefused(f"review {review_id} is already resolved")
        # --- Resolve it ----------------------------------------------------
        review.resolved_by = by
        review.model_update = model_update
        # A resolved group review marks the group as reviewed: this is what
        # the irreversible gate's "recurrence groups reviewed" relies on.
        # review.scope[len("group:"):] slices off the "group:" prefix.
        if review.scope.startswith("group:"):
            self.reviewed_groups.add(review.scope[len("group:"):])
        self._log("STRUCTURAL_REVIEW_RESOLVED", by, review=review_id,
                  condition=review.condition, model_update=model_update)
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
    # Record whether one of an agent's signals proved correct.
    # =======================================================================

    def record_signal_outcome(self, agent: str, correct: bool, by: str,
                              signal_id: Optional[str] = None) -> None:
        """
        Record whether one of an agent's signals later proved correct.

        Enter:   agent       the agent whose signal it was
                 correct     True if the signal proved correct
                 by          the recording agent
                 signal_id   the signal, if known (logged only)
        Exit:    None; the outcome is appended to self.accuracy[agent]

        Spec: Layer 0, AP.7 Source Standing ("What to do"): "Track the correlation
        between a registering agent's contemporaneous characterization ...
        and that agent's actual signal accuracy, measured independently."
        This is the accuracy half of that comparison.
        """
        self._require_actor(by)
        self._tick()
        # setdefault(key, []) returns the existing list for the key, or
        # stores and returns a new empty list if there is none yet.
        self.accuracy.setdefault(agent, []).append(correct)
        self._log("SIGNAL_OUTCOME", by, agent=agent, correct=correct, signal=signal_id)

    # =======================================================================
    # ACT VII, SCENE 2 — THE TRACK RECORD
    # Is this agent's accuracy stable or improving?
    # =======================================================================

    def accuracy_stable_or_improving(self, agent: str) -> bool:
        """
        The draft's definition (the project label D7): with
        at least two outcomes, the later half's accuracy is at least the
        earlier half's, and overall accuracy is at least one half. A single
        outcome counts if it was correct.

        Enter:   agent   the agent
        Exit:    True if their recorded accuracy is stable or improving;
                 False with no record at all

        Spec: the phrase "stable or improving accuracy rate" appears in the
        credibility discounting escalation condition (Layer 2, Escalation
        Conditions) and in AP.7 ("What to do"). Since October 2026 the spec
        gives it an operational definition (Layer 4, Execution Gates,
        "Operational definitions"): "two conditions together: the agent's
        accuracy over the later half of their recorded outcomes is no lower
        than over the earlier half (with an odd count, the later half takes
        the extra outcome), and their overall accuracy is at least one
        half." Also: "A single recorded outcome is stable or improving if it
        was correct and not if it was wrong. An agent with no outcome record
        has no accuracy rate against which a discount could be earned". The
        overall-accuracy condition follows from AP.7: a characterization
        that tracks genuinely poor signal quality is not a void. The formula
        below implements that definition exactly; D7 began as this
        project's choice and the draft adopted it in October 2026.

        Worked example: [False, True, True, True] -> early half [F, T] = 0.5,
        late half [T, T] = 1.0, overall 0.75 -> True.
        With an odd count the later "half" gets the extra item.
        """
        # PLAYERS IN THIS SCENE
        #   record   the agent's outcomes, oldest first
        #   half     size of the earlier half
        #   early    accuracy over the earlier half
        #   late     accuracy over the later half

        record = self.accuracy.get(agent, [])
        if not record:
            return False
        if len(record) == 1:
            return record[0]
        # sum() of a list of booleans counts the Trues (True == 1, False == 0).
        # record[:half] is the first `half` items; record[half:] the rest.
        half = len(record) // 2
        early = sum(record[:half]) / half
        late = sum(record[half:]) / (len(record) - half)
        return late >= early and sum(record) / len(record) >= 0.5

    # =======================================================================
    # ACT VII, SCENE 3 — EARNED OR APPLIED?
    # Is a credibility discount supported by the agent's record?
    # =======================================================================

    def discount_supported_by_record(self, agent: str) -> bool:
        """
        AP.7: credibility judgments must be traceable to demonstrated accuracy.
        A discount is supported only by an accuracy record that is poor or
        declining. With no record at all, the discount characterizes the
        person rather than their track record, so it is not supported (D7).

        Enter:   agent   the discounted agent
        Exit:    True only if there is a record and it is not stable/improving

        Spec: AP.7 ("What to do"): "Where negative characterization tracks
        accurately with genuinely poor signal quality, no void exists."
        """
        return bool(self.accuracy.get(agent)) and not self.accuracy_stable_or_improving(agent)

    # =======================================================================
    # ACT VII, SCENE 4 — SHOOTING THE MESSENGER
    # Record a credibility discount; escalate it, and detect AP-G.
    # =======================================================================

    def record_credibility_discount(self, target: str, by: str, characterization: str,
                                    signal_id: Optional[str] = None) -> None:
        """
        A registering agent is characterized instead of their signal being
        evaluated. Escalates unless the discount is supported by the agent's
        record (a record that exists and is not stable/improving), so a
        discount against an agent with no record escalates too; repeated
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
        if self.discount_supported_by_record(target):
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
        External Evidence Source showing that the path has been tested:
        evidence of an eligible kind produced by neither the agent who
        registered or reclassified the decision, nor the agent accepting
        it, nor a process under evaluation in its loops. An untested
        reversal path counts as absent." Assessed when needed, so a later
        acceptance by the evidence's producer withdraws the support.
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
        """
        # PLAYERS IN THIS SCENE
        #   d                         the decision
        #   old_declared, old_applied its classes before the change
        #   new_applied               the class the gate applies after it
        #   lowered                   True if either class went down

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
        lowered = (CLASS_RANK[execution_class] < CLASS_RANK[old_declared]
                   or CLASS_RANK[new_applied] < CLASS_RANK[old_applied])
        if lowered and d.ever_blocked:
            self._escalate(E.EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK, f"decision:{decision_id}",
                           f"{decision_id} lowered from {old_declared.value}/"
                           f"{old_applied.value} to {execution_class.value}/"
                           f"{new_applied.value} after a blocked execution request",
                           [], by)

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
        Exit:    None; the signal is added (once) and the authority count
                 re-checked
        """
        # PLAYERS IN THIS SCENE
        #   d   the decision

        self._require_actor(by)
        # Called only for its check: refuses if the signal is unknown.
        self._signal(signal_id)
        d = self._decision(decision_id)
        self._tick()
        if signal_id not in d.signal_ids:
            d.signal_ids.append(signal_id)
        self._log("SIGNAL_LINKED", by, decision=decision_id, signal=signal_id)
        self._check_authority_count(d, by)

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
                        evidence_ids: Iterable[str] = ()) -> None:
        """
        Rule 4: a single named agent accepts authorization, risk and rationale.

        Enter:   decision_id   the decision
                 by            the accepting agent
                 rationale     required; the rationale they take on
                 evidence_ids  evidence cited in the acceptance (already
                               added); it can supply the decision's External
                               Evidence Source at the irreversible gate
        Exit:    None; the decision records `by`, the rationale and the
                 cited evidence; an unknown evidence id is refused and
                 nothing changes. With authority enforced, an agent
                 without AUTHORIZE over the decision's scope is refused
                 (ACCEPTANCE_REFUSED) and nothing changes

        Spec: Rule 4, Decisions Have Living Ownership: "Before any execution-class decision,
        a single agent must explicitly accept authorization, risk
        acceptance, and rationale documentation as their responsibility."
        Why: "Diffused ownership is functionally equivalent to no
        ownership" (Challenger was "owned by no one cleanly").

        The decision holds one accepting agent; a later acceptance replaces
        the earlier one (both are in the audit trail).
        """
        # PLAYERS IN THIS SCENE
        #   d              the decision
        #   evidence_ids   the cited ids, frozen into a tuple
        #   unknown        any of them not in the evidence record

        self._require_actor(by)
        if not rationale:
            raise TransitionRefused("Rule 4: acceptance requires rationale documentation")
        d = self._decision(decision_id)
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
        # `a, b, c = x, y, z` assigns all three fields in one line.
        d.accepted_by, d.acceptance_rationale, d.acceptance_evidence = (
            by, rationale, evidence_ids)
        # The grant that backs this acceptance; it must stay in force.
        backing = (self._backing(by, Power.AUTHORIZE, d.scope)
                   if self.authority_enforced and by not in self.settings.authority_roots
                   else None)
        d.acceptance_grant = backing.grant_id if backing else None
        self._log("DECISION_ACCEPTED", by, decision=decision_id, rationale=rationale,
                  evidence=list(evidence_ids), grant=d.acceptance_grant)

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
    # D8: is this signal's classification stable?
    # =======================================================================

    def _classification_stable(self, sig: Signal) -> bool:
        """
        D8: classified, and not reclassified since its review last opened.

        Enter:   sig   the signal
        Exit:    True if its classification counts as stabilized

        Spec: Rule 3, Interpretive Stability Precedes Execution: "Execution
        cannot proceed while interpretive uncertainty remains unresolved and
        unstabilized ... Interpretive stability is achieved by naming the
        uncertainty, not by eliminating it." The irreversible gate requires
        "classification stabilized" (Layer 4, Execution Gates), which the
        spec's operational definitions now define as "no signal has been
        reclassified to a different operational state since its review
        opened. Re-confirming the same state does not destabilize it". The
        exact measurement is the IMPLEMENTATION DECISION D8:
          - never classified -> not stable
          - classified but review never opened -> stable
          - otherwise take the last classification at or before the review
            opened (or, if none, the first one after); stable if every
            classification after the opening equals it.
        So reclassifying to a different state during review makes it
        unstable; re-confirming the same state does not.
        """
        # PLAYERS IN THIS SCENE
        #   before     states recorded at or before the review opened
        #   after      states recorded after the review opened
        #   baseline   the state later classifications are compared against
        #   t, st     (clock time, state) pairs from the history

        if not sig.classification_history:
            return False
        if sig.review_opened_at < 0:
            return True
        # `for t, st in history` unpacks each (time, state) pair.
        before = [st for t, st in sig.classification_history if t <= sig.review_opened_at]
        after = [st for t, st in sig.classification_history if t > sig.review_opened_at]
        # before[-1] is the last item of `before`.
        baseline = before[-1] if before else (after[0] if after else None)
        # all(...) is True only if every item is True (and True when empty).
        return baseline is not None and all(st == baseline for st in after)

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
          open_loops                1 - (signals open or in trajectory_lock)
                                    / signals. Trajectory lock counts as
                                    open: the spec calls it "a permanent
                                    marker that the loop remained open"
                                    (Layer 4, Commitment State Machine).
          classification_stability  share of signals that pass D8
          closure_quality           chain-sound evidence closures / (real
                                    closures + reopens); 1.0 if there are
                                    neither. An evidence closure that is not
                                    chain-sound counts as non-evidence
                                    (Layer 2, Closure Chain). Attempted
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
        #   sigs                the decision's registered signals
        #   open_or_locked      those open or in trajectory_lock
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

        sigs = self._decision_signals(self._decision(decision_id))
        if not sigs:
            # {k: 1.0 for k in ...} is a dict comprehension: every factor -> 1.0.
            return 1.0, {k: 1.0 for k in COHERENCE_WEIGHTS}
        # --- Gather what the factors are computed from ---------------------
        open_or_locked = [s for s in sigs if s.is_open or s.state == S.TRAJECTORY_LOCK]
        # Two `for` clauses: for each signal, for each of its closures. The
        # (signal, closure) pairs let each closure be judged against its own
        # signal; only chain-sound evidence closures count as evidence
        # (Layer 2, Closure Chain).
        pairs = [(s, c) for s in sigs for c in s.closures if not c.attempted_only]
        closures = [c for _, c in pairs]
        evidence_closures = [c for s, c in pairs if self._closure_sound(c, s, frozenset())]
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
        non_evidence = [c for s, c in pairs if not self._closure_sound(c, s, frozenset())]
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
                       Void Types, AP-A)
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
            if not (arch.stewards.get(mode) or sig.steward):
                voids.append(f"AP-A stewardship void: no steward for failure mode {mode!r}")
            # --- AP.1b: is a successor registered, and someone else? -------
            # A "successor" who is the steward is still "a single point of
            # failure" (AP.1b, Stewardship Succession, which since October
            # 2026 says so explicitly). Found by the Alloy model
            # (verification/alloy, NoSinglePointOfStewardship).
            steward = arch.stewards.get(mode) or sig.steward
            successor = arch.successors.get(mode) or sig.successor
            if not successor:
                voids.append(f"AP.1b: no registered successor for failure mode {mode!r}")
            elif successor == steward:
                voids.append(f"AP.1b: the successor for failure mode {mode!r} is the "
                             "steward (single point of failure)")
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

    # =======================================================================
    # ACT VIII, SCENE 7b — WHAT THE IRREVERSIBLE GATE ASKS OF LOOPS AND EVIDENCE
    # Is each constraint/anomaly loop resolved, and is there an EES anywhere?
    # =======================================================================

    def _gate_resolved(self, sig: Signal) -> bool:
        """
        Does a constraint or anomaly loop meet the irreversible gate?

        Enter:   sig   a constraint or anomaly signal
        Exit:    True if it is closed by a chain-sound evidence closure, or
                 exited by a type whose Loop State After is closed

        Spec: Layer 4, Execution Gates, "Constraint and anomaly loops
        evidence-closed": "closed by a chain-sound evidence closure, or has
        exited by a type whose Loop State After is closed (terminal,
        superseded)." Reversibility Logic: "A constraint or anomaly loop
        closed by authority or role switch is not resolved for this
        purpose, however final its closure looks."
        """
        if sig.state == S.EXITED and sig.exit is not None:
            return sig.exit.exit_type in RESOLVING_EXITS
        return self._signal_sound(sig.signal_id, frozenset())

    def _decision_ees(self, d: Decision, sigs: list[Signal]) -> bool:
        """
        Is there at least one External Evidence Source in the decision's
        support?

        Enter:   d      the decision
                 sigs   its registered signals
        Exit:    True if some evidence of an eligible kind, produced by
                 neither a process under evaluation in the decision's loops
                 nor the accepting agent, is among (a) the qualifying
                 evidence of its loops' chain-sound evidence closures, or
                 (b) the evidence cited in its Rule 4 acceptance

        Spec: Layer 4, Execution Gates, "At least one External Evidence
        Source": "A decision reasoned through entirely inside one process,
        however many loops it closed or reviews it passed, does not meet
        this requirement."

        IMPLEMENTATION DECISION: the spec states no novelty or chain test
        for evidence cited in the acceptance, so none is applied to it.
        """
        # PLAYERS IN THIS SCENE
        #   excluded   producers that cannot count: the processes under
        #              evaluation and the accepting agent
        #   support    candidate Evidence items, from (a) and (b)
        #   latest     each evidence-closed loop's latest real closure

        excluded = {s.evaluated_process for s in sigs} | {d.accepted_by}
        support = [self.evidence[e] for e in d.acceptance_evidence]
        for s in sigs:
            if self._signal_sound(s.signal_id, frozenset()):
                latest = next(c for c in reversed(s.closures) if not c.attempted_only)
                support += self._qualifying(latest, s)
        return any(ev.kind in EES_ELIGIBLE_KINDS and ev.produced_by not in excluded
                   for ev in support)

    # =======================================================================
    # ACT VIII, SCENE 8 — THE INTERLOCK
    # May this decision execute? Check the gates, and handle overrides.
    # =======================================================================

    def request_execution(self, decision_id: str, by: str,
                          override_rationale: Optional[str] = None) -> GateResult:
        """
        Execution gate (Layer 4). Requirements by class:
        The class used is the APPLIED one (_applied_class): the declared
        class only if a tested reversal path supports it, else irreversible.
          irreversible  constraint and anomaly loops evidence-closed (weakest
                        link, chain-sound); minimum evidence closure ratio for
                        the other loop types; at least one External Evidence
                        Source; classification stabilized; recurrence groups
                        reviewed; coherence at or above threshold; plus the
                        implementation checks listed below (no unresolved
                        structural reviews, no open off-envelope/containment
                        signals)
          elevated      classification acknowledged; open loops documented
          routine       signal registration complete
        Order of checks: an already-executed decision is refused; then a
        missing Rule 4 acceptance returns at once (EXECUTION_REFUSED); then
        an unresolved EXECUTION_CLASS_DOWNGRADE_AFTER_BLOCK review on the
        decision returns at once (EXECUTION_BLOCKED). Neither of those two
        can be overridden, and each marks the decision `ever_blocked`. Only
        then are the gates above evaluated. A Layer 0 void makes the gate
        structurally void. Other failures may be overridden: the override
        is permanently logged with identity, rationale and time; for
        irreversible execution, constraint and anomaly loops under review
        are latched into trajectory_lock with a lock-in closure record
        ("open-loop irreversible execution"). Failures with no override
        mark the decision `ever_blocked`, so a later lowering of its class
        escalates (reclassify_decision, ACT VIII, Scene 1b).

        Enter:   decision_id          the decision asking to execute
                 by                   the requesting agent
                 override_rationale   if given, overrides any gate failure
                                      except Rule 4 and an unresolved
                                      downgrade-after-block review
        Exit:    a GateResult. On permission (clean or overridden) the
                 decision is marked executed. Raises TransitionRefused if the
                 decision is unknown or has already executed (the latter
                 after the clock has ticked).

        Spec sources:
          Execution Gates table (Layer 4, Execution Gates), summarized
            above. Its "Operational definitions" (October 2026) give the
            meanings used here: "Classification acknowledged" = every
            signal carries an operational state; "Open loops documented" =
            no signal remains merely `registered`; "Recurrence groups
            reviewed" = no recurrence group among the decision's signals
            has a structural review still awaiting its Rule 8 model update
            ("A group that never crossed its threshold has nothing to
            review"); the ratio applies to "uncertainty, dissent,
            classification, and framing signals", and "With no such
            closures, there is nothing to measure and the requirement is
            met." Lock-in closures are only ever created on constraint and
            anomaly signals (see the override below), so none reach the
            ratio; the draft's ratio definition no longer mentions them.
          Overrides (same section): "Gates can be overridden. Every override
            is permanently logged with the agent's identity, rationale, and
            timestamp. The system does not prevent decisions. It makes the
            epistemic quality of decisions visible, auditable, and
            permanent."
          Execution Class Assignment (same section): "Until that review is
            resolved, the decision cannot execute at any class, and this
            cannot be overridden".
          Coherence (Layer 4, Coherence Score): "A score below the
            domain-configured threshold blocks irreversible execution
            pending acknowledgment." Here the acknowledgment is an override.
          Reversibility Logic: "Irreversible decisions require
            evidence-based closure for all constraint and anomaly loops, or
            an explicit open-loop authorization with permanent audit
            logging." Closure Chain: a closure that is not chain-sound
            "counts as a non-evidence closure ... at the execution gates, in
            the evidence closure ratio, and in the coherence score."
          Open-Loop Irreversible Execution (Key Definitions):
            "Permitted with explicit authorization — permanently logged."
          Lock-in closure (Layer 4, Commitment State Machine; Key
            Definitions, Lock-in Closure): recorded as under_review ->
            trajectory_lock; "a trajectory lock indicator when it occurs in
            the presence of open constraint loops".
          Escalation conditions (Layer 2, Escalation Conditions): lock-in
            closure with open constraint loops; suppressed signal before
            irreversible execution.

        IMPLEMENTATION DECISIONS made here (not in the spec):
          - The class requirements are cumulative: routine's check applies to
            every class, elevated's checks also apply to irreversible.
          - The evidence closure ratio (D4) treats "the other loops" as the
            decision's non-constraint, non-anomaly signals (D9's
            high-consequence test), and its default minimum is 0.5.
          - Unresolved structural reviews on the decision's signals, or on
            the decision itself, block irreversible execution.
          - Open off-envelope or containment signals block irreversible
            execution. This reads Key Definitions (Operational State:
            Off-Envelope and Containment): off-envelope needs
            "Evidence-based classification ... before irreversible
            execution"; containment needs "extraordinary justification and
            independent steward review".
          - Overrides are allowed for every gate failure except the two
            never-overridable ones above, including Layer 0 voids (the
            result still reports architecture_void=True and the override
            log records it).
          - Lock-in latching applies only to constraint and anomaly signals
            that are under_review: that is the only state the state machine
            lets move to trajectory_lock. Constraint and anomaly loops that
            fail the gate in any other way (open elsewhere, or closed
            without chain-sound evidence) are reported as "still open" in
            the escalation and the log.
          - A suppressed signal at an irreversible request opens the
            SUPPRESSED_BEFORE_EXECUTION review first, before the other
            irreversible checks run, so that review's "unresolved
            structural review" failure blocks this same request.
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
        #   undocumented       signals still only `registered`
        #   suppressed         signals currently suppressed
        #   unresolved         constraint/anomaly signals failing the gate
        #   unstable           signals whose classification is not stable (D8)
        #   groups             the signals' recurrence groups
        #   unreviewed         groups with an unresolved recurrence review
        #   pairs              (signal, closure) for the other loop types
        #   ratio              share of those that are chain-sound evidence
        #   pending            ids of unresolved reviews touching this decision
        #   off                open signals classified off-envelope/containment
        #   result             the GateResult being returned
        #   locked             constraint/anomaly signals latched into
        #                      trajectory_lock
        #   s, rec             each signal, and its lock-in closure record
        #   still_open         constraint/anomaly signals still failing the
        #                      gate after latching

        self._require_actor(by)
        d = self._decision(decision_id)
        self._tick()
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
        # is ignored: an override cannot supply a power nobody granted.
        if not self.holds(by, Power.EXECUTE, d.scope):
            d.ever_blocked = True
            reason = (f"{by} does not hold execute over {d.scope!r} "
                      "(authority is granted, never inferred)")
            self._log("EXECUTION_REFUSED", by, decision=decision_id, reason=reason,
                      declared_class=d.execution_class, execution_class=applied)
            return GateResult(decision_id, applied, False, False, False, [reason], score,
                              declared_class=d.execution_class)
        # --- Rule 4: someone must have accepted it (never overridable) -----
        # Checked first, and returned at once: no other gate is evaluated
        # and override_rationale is ignored.
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
        # --- Relabeled after a refusal: blocked at every class -------------
        # Never overridable: "Until that review is resolved, the decision
        # cannot execute at any class, and this cannot be overridden" (Layer
        # 4, Execution Class Assignment).
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

        # --- Layer 0: architecture voids (every class) ---------------------
        voids = self.architecture_check(decision_id)
        failures += voids

        # --- Routine requirement (every class): registration complete ------
        missing = [sid for sid in d.signal_ids if sid not in self.signals]
        if missing or any(s.state == S.UNREGISTERED for s in sigs):
            failures.append(f"signal registration incomplete: {missing}")
        # --- Elevated requirements (elevated and irreversible) -------------
        if applied in (ExecutionClass.ELEVATED, ExecutionClass.IRREVERSIBLE):
            unclassified = [s.signal_id for s in sigs if s.operational_state is None]
            if unclassified:
                failures.append(f"classification not acknowledged: {unclassified}")
            undocumented = [s.signal_id for s in sigs if s.state == S.REGISTERED]
            if undocumented:
                failures.append(f"open loops not documented: {undocumented}")
        suppressed = [s.signal_id for s in sigs if s.state == S.SUPPRESSED]
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
            # Constraint and anomaly loops evidence-closed: weakest link,
            # so one failing loop fails the gate (Reversibility Logic).
            unresolved = [s.signal_id for s in sigs
                          if s.high_consequence and not self._gate_resolved(s)]
            if unresolved:
                failures.append(f"constraint/anomaly loops not evidence-closed: {unresolved}")
            # Classification stabilized (Rule 3; D8).
            unstable = [s.signal_id for s in sigs if not self._classification_stable(s)]
            if unstable:
                failures.append(f"classification not stabilized: {unstable}")
            # Recurrence groups reviewed (Rules 7-8).
            groups = {s.recurrence_group for s in sigs if s.recurrence_group}
            unreviewed = sorted(g for g in groups
                                if any(r.scope == f"group:{g}" and not r.resolved
                                       for r in self.reviews))
            if unreviewed:
                failures.append(f"recurrence groups not reviewed: {unreviewed}")
            # Minimum evidence closure ratio (D4), for the other loop types
            # only. sum() over booleans counts the chain-sound evidence
            # closures.
            pairs = [(s, c) for s in sigs if not s.high_consequence
                     for c in s.closures if not c.attempted_only]
            if pairs:
                ratio = (sum(self._closure_sound(c, s, frozenset()) for s, c in pairs)
                         / len(pairs))
                if ratio < self.settings.min_evidence_closure_ratio:
                    failures.append(f"evidence closure ratio {ratio:.2f} below "
                                    f"{self.settings.min_evidence_closure_ratio:.2f}")
            # At least one External Evidence Source in the decision's support.
            if not self._decision_ees(d, sigs):
                failures.append("no External Evidence Source in the decision's support")
            # Unresolved structural reviews (implementation decision).
            # `set(a) & set(b)` is set intersection: the signal ids both
            # lists share; an empty set is falsy. The outer {...} is a set
            # comprehension of review ids, then sorted into a list.
            pending = sorted({r.review_id for r in self.reviews if not r.resolved and (
                set(r.signal_ids) & set(d.signal_ids) or r.scope == f"decision:{decision_id}")})
            if pending:
                failures.append(f"unresolved structural reviews: {pending}")
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
                            bool(voids), failures, score, declared_class=d.execution_class)
        if not failures:
            d.executed = True
            self._log("EXECUTION_PERMITTED", by, decision=decision_id,
                      declared_class=d.execution_class, execution_class=applied,
                      coherence=score, factors=factors)
            return result

        # --- Failures and no override: blocked -----------------------------
        if not override_rationale:
            d.ever_blocked = True
            self._log("EXECUTION_BLOCKED", by, decision=decision_id,
                      declared_class=d.execution_class, execution_class=applied,
                      failures=failures,
                      architecture_void=bool(voids), coherence=score, factors=factors)
            return result

        # Override: permitted, but permanent, attributed and consequential.
        self._log("GATE_OVERRIDE", by, decision=decision_id,
                  declared_class=d.execution_class, execution_class=applied,
                  failures=failures,
                  architecture_void=bool(voids), rationale=override_rationale,
                  coherence=score, factors=factors)
        locked = []
        # --- Irreversible override: open-loop irreversible execution -------
        if applied == ExecutionClass.IRREVERSIBLE:
            # Latch each constraint/anomaly signal under review into
            # trajectory_lock, with a lock-in closure record (the spec's
            # fourth closure type, which has no closed state of its own;
            # Layer 4, Commitment State Machine).
            for s in sigs:
                if s.high_consequence and s.state == S.UNDER_REVIEW:
                    self._closure_seq += 1
                    rec = ClosureRecord(f"C{self._closure_seq}", s.signal_id,
                                        ClosureType.LOCK_IN, by, None, (),
                                        override_rationale, self.clock)
                    self._move(s, S.TRAJECTORY_LOCK, by, closure_type=ClosureType.LOCK_IN,
                               record=rec.record_id, decision=decision_id)
                    s.closures.append(rec)
                    locked.append(s.signal_id)
            # Constraint/anomaly loops still failing the gate: open in other
            # states (escalated, suppressed, open exits, ...) or closed
            # without chain-sound evidence. Latched ones are excluded.
            still_open = [s.signal_id for s in sigs if s.high_consequence
                          and s.state != S.TRAJECTORY_LOCK and not self._gate_resolved(s)]
            # Escalation: lock-in closure in the presence of open constraint
            # loops (the latched ones were open until this moment).
            if locked or still_open:
                self._escalate(E.LOCK_IN_WITH_OPEN_CONSTRAINTS, f"decision:{decision_id}",
                               f"lock-in closure with open constraint loops: locked {locked}, "
                               f"still open {still_open}", [], by)
            self._log("OPEN_LOOP_IRREVERSIBLE_EXECUTION", by, decision=decision_id,
                      locked=locked, still_open=still_open, rationale=override_rationale)
        # --- Execute under override ----------------------------------------
        d.executed = True
        result.permitted, result.overridden, result.locked_signals = True, True, locked
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

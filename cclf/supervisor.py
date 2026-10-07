"""
The coordination supervisor: CCL-F v0.2 Layer 4 as a running monitor.

It owns the signals, evidence, decisions and registered architecture, and it
is the only thing that changes their state. Every operation:
  1. is checked against the commitment state machine (statemachine.py),
  2. is typed by deterministic rules (closure type, classification,
     escalation conditions, execution gates) with no model involved,
  3. is written to the hash-chained audit trail with the acting agent.

Models (probabilistic automation) may only *propose* through advisor.py;
their proposals pass through the same rules as anyone else's, and model
output never counts as evidence (EES).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .audit import AuditTrail
from .statemachine import check_transition, exit_allowed, reentry_allowed
from .types import (
    Architecture, ClosureRecord, ClosureType, CommitmentState as S, Decision,
    EES_ELIGIBLE_KINDS, EscalationCondition as E, Evidence, ExecutionClass,
    ExitRecord, ExitType, LegalSubtype, OperationalState as O, Referent,
    Signal, SignalType, CLOSED_STATES,
)


# ---------------------------------------------------------------------------
# Settings. The spec leaves these values open; see docs/DECISIONS.md.
# ---------------------------------------------------------------------------

DEFAULT_RECURRENCE_THRESHOLD = 3        # D1: Challenger "crossed after the third occurrence"
DEFAULT_AUTHORITY_CLOSURE_THRESHOLD = 1  # D5: escalate when count exceeds this
DEFAULT_SENDER_DISCOUNT_THRESHOLD = 3   # D6: "provisionally mirroring Rule 7"
DEFAULT_COHERENCE_THRESHOLD = 0.6       # D3: "domain-configured threshold"
DEFAULT_MIN_EVIDENCE_CLOSURE_RATIO = 0.5  # D4: "minimum evidence closure ratio"

COHERENCE_WEIGHTS = {                   # Layer 4, Coherence Score (provisional)
    "open_loops": 0.30,
    "classification_stability": 0.25,
    "closure_quality": 0.20,
    "recurrence_pressure": 0.15,
    "authority_compression": 0.10,
}

EXIT_TYPES_REQUIRING_OPEN_STATE_NOTE = frozenset({
    ExitType.TERMINAL, ExitType.LEGAL, ExitType.KEY_PERSON})


class TransitionRefused(Exception):
    """A requested operation broke a v0.2 rule. Nothing changed."""


@dataclass
class Settings:
    recurrence_threshold: int = DEFAULT_RECURRENCE_THRESHOLD
    authority_closure_threshold: int = DEFAULT_AUTHORITY_CLOSURE_THRESHOLD
    sender_discount_threshold: int = DEFAULT_SENDER_DISCOUNT_THRESHOLD
    coherence_threshold: float = DEFAULT_COHERENCE_THRESHOLD
    min_evidence_closure_ratio: float = DEFAULT_MIN_EVIDENCE_CLOSURE_RATIO


@dataclass
class StructuralReview:
    """An automatic escalation to structural review (Layer 2)."""
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
        return self.resolved_by is not None


@dataclass
class GateResult:
    """Outcome of an execution request."""
    decision_id: str
    execution_class: ExecutionClass
    permitted: bool
    overridden: bool
    architecture_void: bool
    failures: list[str]
    coherence: float
    locked_signals: list[str] = field(default_factory=list)


class Supervisor:
    """CCL-F v0.2 Layer 4 supervisor."""

    def __init__(self, settings: Optional[Settings] = None,
                 architecture: Optional[Architecture] = None) -> None:
        self.settings = settings or Settings()
        self.architecture = architecture or Architecture()
        self.audit = AuditTrail()
        self.signals: dict[str, Signal] = {}
        self.evidence: dict[str, Evidence] = {}
        self.decisions: dict[str, Decision] = {}
        self.reviews: list[StructuralReview] = []
        self.reviewed_groups: set[str] = set()
        self.accuracy: dict[str, list[bool]] = {}      # agent -> signal outcomes
        self.discounts: dict[str, int] = {}            # agent -> discount count
        self.sender_discount_void: set[str] = set()    # agents under AP-G
        self.clock = 0
        self._closure_seq = 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _tick(self) -> int:
        self.clock += 1
        return self.clock

    def _log(self, event: str, actor: str, **payload) -> None:
        self.audit.append(self.clock, event, actor, payload)

    @staticmethod
    def _require_actor(by: str) -> None:
        """Every operation is attributed; check before anything changes."""
        if not by or not str(by).strip():
            raise TransitionRefused("every operation needs an acting agent's identity")

    def _decision(self, decision_id: str) -> Decision:
        if decision_id not in self.decisions:
            raise TransitionRefused(f"unknown decision {decision_id!r}")
        return self.decisions[decision_id]

    def _signal(self, signal_id: str) -> Signal:
        if signal_id not in self.signals:
            raise TransitionRefused(f"unknown signal {signal_id!r}")
        return self.signals[signal_id]

    def _move(self, sig: Signal, target: S, actor: str, **payload) -> None:
        ok, reason = check_transition(sig.state, target)
        if not ok:
            self._log("TRANSITION_REFUSED", actor, signal=sig.signal_id,
                      **{"from": sig.state, "to": target, "reason": reason})
            raise TransitionRefused(reason)
        previous = sig.state
        sig.state = target
        self._log("TRANSITION", actor, signal=sig.signal_id,
                  **{"from": previous, "to": target, "rule": reason}, **payload)

    def is_novel(self, ev: Evidence, sig: Signal) -> bool:
        """Evidence Novelty: not present when the signal was registered."""
        return ev.evidence_id not in sig.evidence_at_registration and ev.at > sig.registered_at

    def is_ees(self, ev: Evidence, sig: Signal) -> bool:
        """
        External Evidence Source: an eligible kind of evidence, produced by a
        process causally independent of the one under evaluation and of the
        signal's registrant. Model output never qualifies.
        """
        return (ev.kind in EES_ELIGIBLE_KINDS
                and ev.produced_by not in (sig.evaluated_process, sig.registered_by))

    # ------------------------------------------------------------------
    # Architecture and evidence
    # ------------------------------------------------------------------

    def register_architecture(self, architecture: Architecture, by: str) -> None:
        self._require_actor(by)
        self._tick()
        self.architecture = architecture
        self._log("ARCHITECTURE_REGISTERED", by,
                  stewards=architecture.stewards, successors=architecture.successors,
                  channels_tested=architecture.channels_tested,
                  reporters={k: sorted(v) for k, v in architecture.reporters.items()},
                  interested_parties={k: sorted(v) for k, v in
                                      architecture.interested_parties.items()})

    def add_evidence(self, evidence_id: str, content: str, source: str, kind,
                     produced_by: str, by: str, signal_ids: Iterable[str] = ()) -> Evidence:
        self._require_actor(by)
        at = self._tick()
        if evidence_id in self.evidence:
            raise TransitionRefused(f"evidence {evidence_id!r} already registered")
        ev = Evidence(evidence_id, content, source, kind, produced_by, at)
        self.evidence[evidence_id] = ev
        for sid in signal_ids:
            self._signal(sid).evidence_ids.append(evidence_id)
        self._log("EVIDENCE_ADDED", by, evidence=evidence_id, kind=kind,
                  produced_by=produced_by, source=source, signals=list(signal_ids))
        return ev

    # ------------------------------------------------------------------
    # Signal lifecycle
    # ------------------------------------------------------------------

    def register_signal(self, signal_id: str, signal_type: SignalType, description: str,
                        registered_by: str, referent: Referent, evaluated_process: str,
                        steward: Optional[str] = None, successor: Optional[str] = None,
                        closure_authority: Iterable[str] = (),
                        recurrence_group: Optional[str] = None,
                        evidence_ids: Iterable[str] = (),
                        failure_mode: Optional[str] = None) -> Signal:
        self._require_actor(registered_by)
        at = self._tick()
        if signal_id in self.signals:
            raise TransitionRefused(f"signal {signal_id!r} already registered")
        sig = Signal(signal_id, signal_type, description, registered_by, referent,
                     evaluated_process, steward, successor, frozenset(closure_authority),
                     recurrence_group, failure_mode)
        sig.evidence_ids = list(evidence_ids)
        sig.evidence_at_registration = frozenset(sig.evidence_ids)
        sig.registered_at = at
        self.signals[signal_id] = sig
        self._move(sig, S.REGISTERED, registered_by, signal_type=signal_type,
                   description=description, steward=steward, successor=successor,
                   recurrence_group=recurrence_group, failure_mode=failure_mode)
        self._check_recurrence(sig, registered_by)
        return sig

    def classify(self, signal_id: str, state: O, by: str,
                 evidence_ids: Iterable[str] = (), proposed_by_model: bool = False) -> O:
        """
        Rule 2: explicit operational-state classification. "Unvalidated
        conditions cannot be classified as nominal": nominal needs at least
        one EES-qualifying item among the cited evidence; otherwise the
        classification is recorded as elevated uncertainty and the refusal
        is audited.
        """
        self._require_actor(by)
        self._tick()
        sig = self._signal(signal_id)
        cited = [self.evidence[e] for e in evidence_ids if e in self.evidence]
        applied = state
        if state == O.NOMINAL and not any(self.is_ees(ev, sig) for ev in cited):
            applied = O.ELEVATED_UNCERTAINTY
            self._log("CLASSIFICATION_REJECTED", by, signal=signal_id, proposed=state,
                      applied=applied, proposed_by_model=proposed_by_model,
                      reason="Rule 2: unvalidated conditions cannot be classified as nominal")
        if sig.state == S.REGISTERED:
            self._move(sig, S.CLASSIFIED, by)
        sig.operational_state = applied
        sig.classification_history.append((self.clock, applied))
        self._log("CLASSIFIED", by, signal=signal_id, operational_state=applied,
                  evidence=list(evidence_ids), proposed_by_model=proposed_by_model)
        if applied in (O.OFF_ENVELOPE, O.CONTAINMENT):
            self._escalate(E.OFF_ENVELOPE_OR_CONTAINMENT, signal_id,
                           f"classified {applied.value}", [signal_id], by)
        return applied

    def open_review(self, signal_id: str, by: str) -> None:
        """
        Open active analysis on a classified signal. This is the only route
        in from `classified`; the other routes into review each have their own
        operation and audit obligations: reopen() for a closed signal,
        resolve_review() for an escalated one, reenter_suppressed() for a
        suppressed one, reenter() for an exited one.
        """
        self._require_actor(by)
        sig = self._signal(signal_id)
        if sig.state != S.CLASSIFIED:
            routes = {S.ESCALATED: "resolve its structural review (Rule 8)",
                      S.SUPPRESSED: "use reenter_suppressed()",
                      S.EXITED: "use reenter()"}
            hint = ("use reopen() with a rationale" if sig.state in CLOSED_STATES
                    else routes.get(sig.state, "classify it first (Rule 2)"))
            raise TransitionRefused(f"open_review needs a classified signal; {signal_id} is "
                                    f"{sig.state.value}: {hint}")
        self._tick()
        self._move(sig, S.UNDER_REVIEW, by)
        sig.review_opened_at = self.clock
        self._apply_pending_escalations(sig, by)

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
        """
        self._require_actor(by)
        sig = self._signal(signal_id)
        self._tick()
        evidence_ids = tuple(evidence_ids)
        cited = [self.evidence[e] for e in evidence_ids if e in self.evidence]
        qualifying = [ev.evidence_id for ev in cited
                      if self.is_novel(ev, sig) and self.is_ees(ev, sig)]
        if qualifying:
            ctype = ClosureType.EVIDENCE
        elif by == sig.registered_by and referent != sig.registrant_referent:
            ctype = ClosureType.ROLE_SWITCH
        else:
            ctype = ClosureType.AUTHORITY
        return self._apply_closure(sig, by, referent, ctype, evidence_ids, rationale,
                                   qualifying)

    def _apply_closure(self, sig: Signal, by: str, referent: Optional[Referent],
                       ctype: ClosureType, evidence_ids: tuple, rationale: str,
                       qualifying: list[str]) -> ClosureRecord:
        """Record a typed closure; an out-of-authority closer only attempts it."""
        signal_id = sig.signal_id
        self._closure_seq += 1
        attempted = bool(sig.closure_authority) and by not in sig.closure_authority
        record = ClosureRecord(f"C{self._closure_seq}", signal_id, ctype, by, referent,
                               evidence_ids, rationale, self.clock, attempted_only=attempted)
        if attempted:
            sig.closures.append(record)
            self._log("ATTEMPTED_CLOSURE", by, signal=signal_id, closure_type=ctype,
                      record=record.record_id, rationale=rationale,
                      reason="closer is outside the signal's closure authority; "
                             "recorded, not resolved")
            return record

        target = {ClosureType.EVIDENCE: S.CLOSED_EVIDENCE,
                  ClosureType.AUTHORITY: S.CLOSED_AUTHORITY,
                  ClosureType.ROLE_SWITCH: S.CLOSED_ROLE_SWITCH}[ctype]
        self._move(sig, target, by, closure_type=ctype, record=record.record_id,
                   qualifying_evidence=qualifying, cited_evidence=list(evidence_ids),
                   rationale=rationale, flagged=ctype != ClosureType.EVIDENCE)
        sig.closures.append(record)

        if ctype == ClosureType.ROLE_SWITCH and sig.is_constraint:
            self._escalate(E.ROLE_SWITCH_ON_CONSTRAINT, signal_id,
                           "role-switch closure on a safety-constraint signal",
                           [signal_id], by)
        if ctype == ClosureType.AUTHORITY:
            for d in self.decisions.values():
                if signal_id in d.signal_ids:
                    self._check_authority_count(d, by)
        return record

    def adopt_frame(self, framing_signal_id: str, by: str, displaces: Iterable[str],
                    rationale: str = "") -> None:
        """
        A framing signal achieves frame adoption: "an authority closure of the
        framing signal combined with a suppression event on the signals it
        displaced" (Key Definitions, Framing Signal).
        """
        self._require_actor(by)
        sig = self._signal(framing_signal_id)
        if sig.signal_type != SignalType.FRAMING:
            raise TransitionRefused(f"{framing_signal_id} is not a framing signal")
        displaced = [d for d in displaces if self._signal(d).state == S.UNDER_REVIEW]
        self._tick()
        # Frame adoption is authority closure by definition, whoever adopts it.
        record = self._apply_closure(sig, by, None, ClosureType.AUTHORITY, (), rationale, [])
        if record.attempted_only:
            return
        for d in displaced:
            self.suppress(d, by, f"displaced by frame adoption of {framing_signal_id}")
        if any(self.signals[d].is_constraint for d in displaced):
            self._escalate(E.FRAMING_ADOPTED_OVER_OPEN_CONSTRAINTS, framing_signal_id,
                           "framing signal adopted while technical constraint signals "
                           "remained open", displaced, by)

    def suppress(self, signal_id: str, by: str, reason: str) -> None:
        self._require_actor(by)
        self._tick()
        sig = self._signal(signal_id)
        self._move(sig, S.SUPPRESSED, by, reason=reason)
        sig.suppression_events.append(self.clock)

    def reenter_suppressed(self, signal_id: str, by: str, rationale: str) -> None:
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

    def reopen(self, signal_id: str, by: str, rationale: str) -> None:
        """
        "A closed loop cannot be silently reopened — every reopen transition
        is permanently logged with rationale, the identity of the reopening
        agent, and the closure record it supersedes." A role-switch closure
        additionally needs an independent reviewer.
        """
        self._require_actor(by)
        if not rationale:
            raise TransitionRefused("BLOCKED: a closed loop cannot be silently reopened "
                                    "(rationale required)")
        self._tick()
        sig = self._signal(signal_id)
        if sig.state not in CLOSED_STATES:
            raise TransitionRefused(f"{signal_id} is not closed")
        superseded = next(c for c in reversed(sig.closures) if not c.attempted_only)
        if sig.state == S.CLOSED_ROLE_SWITCH and by in (sig.registered_by, superseded.closed_by):
            raise TransitionRefused("reopening a role-switch closure requires an "
                                    "independent reviewer")
        self._move(sig, S.UNDER_REVIEW, by, rationale=rationale,
                   supersedes=superseded.record_id,
                   independent_review_required=sig.state == S.CLOSED_ROLE_SWITCH)
        sig.reopen_count += 1
        sig.review_opened_at = self.clock
        self._apply_pending_escalations(sig, by)

    def exit(self, signal_id: str, exit_type: ExitType, by: str, rationale: str,
             open_loop_state: str = "", successor: Optional[str] = None,
             external_pathway: Optional[str] = None, suppression_ref: Optional[str] = None,
             legal_subtype: Optional[LegalSubtype] = None) -> ExitRecord:
        """Register a loop exit, enforcing its Layer 2 audit obligations."""
        self._require_actor(by)
        self._tick()
        sig = self._signal(signal_id)
        ok, reason = exit_allowed(sig.state)
        if not ok:
            raise TransitionRefused(reason)
        if exit_type in EXIT_TYPES_REQUIRING_OPEN_STATE_NOTE and not open_loop_state:
            raise TransitionRefused(f"{exit_type.value} exit requires explicit notation of "
                                    "the open loop state at the time of exit")
        if exit_type == ExitType.DELEGATED and not successor:
            raise TransitionRefused("delegated exit requires successor registration")
        if exit_type == ExitType.WHISTLEBLOWER and not (external_pathway and suppression_ref):
            raise TransitionRefused("whistleblower exit requires the external pathway and the "
                                    "suppression event that triggered it")
        if exit_type == ExitType.LEGAL and legal_subtype is None:
            raise TransitionRefused("legal exit requires its sub-type")
        record = ExitRecord(signal_id, exit_type, by, rationale,
                            open_loop_state or sig.state.value, self.clock, successor,
                            external_pathway, suppression_ref, legal_subtype)
        previous = sig.state
        sig.state = S.EXITED
        sig.exit = record
        if exit_type == ExitType.DELEGATED:
            sig.steward = successor
        self._log("EXIT", by, signal=signal_id, exit_type=exit_type, **{"from": previous},
                  rationale=rationale, open_loop_state=record.open_loop_state,
                  successor=successor, external_pathway=external_pathway,
                  suppression_ref=suppression_ref, legal_subtype=legal_subtype)
        return record

    def reenter(self, signal_id: str, by: str, rationale: str,
                legal_resumes: Optional[bool] = None,
                new_steward: Optional[str] = None) -> None:
        """
        Return an exited signal to review where its exit type allows it.
        Forced and key-person exits need a successor steward (the signal's
        registered successor, one registered for its failure mode, or
        `new_steward`); a boundary exit must be resumed by a different agent.
        """
        self._require_actor(by)
        if not rationale:
            raise TransitionRefused("re-entry must be logged with a rationale")
        sig = self._signal(signal_id)
        if sig.state != S.EXITED or sig.exit is None:
            raise TransitionRefused(f"{signal_id} has not exited")
        successor = new_steward or sig.successor or self.architecture.successors.get(sig.mode)
        self._tick()
        ok, reason = reentry_allowed(sig.exit.exit_type, legal_resumes,
                                     sig.exit.legal_subtype, bool(successor),
                                     by != sig.exit.by)
        if not ok:
            self._log("REENTRY_REFUSED", by, signal=signal_id,
                      exit_type=sig.exit.exit_type, reason=reason)
            raise TransitionRefused(reason)
        sig.state = S.UNDER_REVIEW
        sig.review_opened_at = self.clock
        if sig.exit.exit_type in (ExitType.FORCED, ExitType.KEY_PERSON):
            sig.steward = successor
        self._log("REENTRY", by, signal=signal_id, exit_type=sig.exit.exit_type,
                  rule=reason, rationale=rationale, steward=sig.steward)
        self._apply_pending_escalations(sig, by)

    # ------------------------------------------------------------------
    # Escalation and structural review
    # ------------------------------------------------------------------

    def _escalate(self, condition: E, scope: str, detail: str,
                  signal_ids: list[str], actor: str) -> StructuralReview:
        # One open review per (condition, scope): a repeat adds to it.
        for existing in self.reviews:
            if (not existing.resolved and existing.condition == condition
                    and existing.scope == scope):
                for sid in signal_ids:
                    if sid not in existing.signal_ids:
                        existing.signal_ids.append(sid)
                return existing
        review = StructuralReview(f"R{len(self.reviews) + 1}", condition, scope, detail,
                                  self.clock, list(signal_ids))
        self.reviews.append(review)
        self._log("ESCALATION", actor, review=review.review_id, condition=condition,
                  scope=scope, detail=detail, signals=list(signal_ids))
        for sid in signal_ids:
            sig = self.signals.get(sid)
            if sig is not None and sig.state == S.UNDER_REVIEW:
                self._move(sig, S.ESCALATED, actor, review=review.review_id)
        return review

    def _apply_pending_escalations(self, sig: Signal, actor: str) -> None:
        """A signal that reaches review while an unresolved escalation names it is escalated."""
        for review in self.reviews:
            if not review.resolved and sig.signal_id in review.signal_ids \
                    and sig.state == S.UNDER_REVIEW:
                self._move(sig, S.ESCALATED, actor, review=review.review_id)

    def _check_recurrence(self, sig: Signal, actor: str) -> None:
        group = sig.recurrence_group
        if group is None or group in self.reviewed_groups:
            return
        members = [s.signal_id for s in self.signals.values() if s.recurrence_group == group]
        open_review = next((r for r in self.reviews if r.scope == f"group:{group}"
                            and not r.resolved), None)
        if open_review is not None:
            if sig.signal_id not in open_review.signal_ids:
                open_review.signal_ids.append(sig.signal_id)
            return
        if len(members) >= self.settings.recurrence_threshold:
            self._escalate(E.RECURRENCE_THRESHOLD, f"group:{group}",
                           f"{len(members)} signals in recurrence group {group!r} "
                           f"(threshold {self.settings.recurrence_threshold})",
                           members, actor)

    def _check_authority_count(self, d: Decision, actor: str) -> None:
        """
        Escalation condition: authority closure count exceeds the threshold on
        an irreversible decision. Checked whenever a closure happens and
        whenever a decision gains signals, so the order of events does not
        matter.
        """
        if d.execution_class != ExecutionClass.IRREVERSIBLE:
            return
        count = sum(1 for sid in d.signal_ids if sid in self.signals
                    for c in self.signals[sid].closures
                    if c.closure_type == ClosureType.AUTHORITY and not c.attempted_only)
        already = any(r.scope == f"decision:{d.decision_id}" and
                      r.condition == E.AUTHORITY_CLOSURE_COUNT for r in self.reviews)
        if count > self.settings.authority_closure_threshold and not already:
            self._escalate(E.AUTHORITY_CLOSURE_COUNT, f"decision:{d.decision_id}",
                           f"{count} authority closures on irreversible decision "
                           f"{d.decision_id}", [], actor)

    def resolve_review(self, review_id: str, by: str, model_update: str) -> None:
        """
        Rule 8: the structural review must produce a documented update to the
        coordination model, not a re-approval. Escalated signals named by the
        review recover to under_review.
        """
        self._require_actor(by)
        if not model_update.strip():
            raise TransitionRefused("Rule 8: a structural review must document a "
                                    "coordination model update")
        self._tick()
        review = next((r for r in self.reviews if r.review_id == review_id), None)
        if review is None:
            raise TransitionRefused(f"unknown review {review_id!r}")
        if review.resolved:
            raise TransitionRefused(f"review {review_id} is already resolved")
        review.resolved_by = by
        review.model_update = model_update
        if review.scope.startswith("group:"):
            self.reviewed_groups.add(review.scope[len("group:"):])
        self._log("STRUCTURAL_REVIEW_RESOLVED", by, review=review_id,
                  condition=review.condition, model_update=model_update)
        for sid in review.signal_ids:
            sig = self.signals.get(sid)
            still_held = any(not r.resolved and sid in r.signal_ids for r in self.reviews)
            if sig is not None and sig.state == S.ESCALATED and not still_held:
                self._move(sig, S.UNDER_REVIEW, by, review=review_id)

    # ------------------------------------------------------------------
    # Source standing (AP.7 / credibility discounting / AP-G)
    # ------------------------------------------------------------------

    def record_signal_outcome(self, agent: str, correct: bool, by: str,
                              signal_id: Optional[str] = None) -> None:
        """Record whether one of an agent's signals later proved correct."""
        self._require_actor(by)
        self._tick()
        self.accuracy.setdefault(agent, []).append(correct)
        self._log("SIGNAL_OUTCOME", by, agent=agent, correct=correct, signal=signal_id)

    def accuracy_stable_or_improving(self, agent: str) -> bool:
        """
        Implementation decision D7: with at least two outcomes, the later half's
        accuracy is at least the earlier half's, and overall accuracy is at
        least one half. A single correct outcome also counts.
        """
        record = self.accuracy.get(agent, [])
        if not record:
            return False
        if len(record) == 1:
            return record[0]
        half = len(record) // 2
        early = sum(record[:half]) / half
        late = sum(record[half:]) / (len(record) - half)
        return late >= early and sum(record) / len(record) >= 0.5

    def discount_supported_by_record(self, agent: str) -> bool:
        """
        AP.7: credibility judgments must be traceable to demonstrated accuracy.
        A discount is supported only by an accuracy record that is poor or
        declining. With no record at all, the discount characterizes the
        person rather than their track record, so it is not supported (D7).
        """
        return bool(self.accuracy.get(agent)) and not self.accuracy_stable_or_improving(agent)

    def record_credibility_discount(self, target: str, by: str, characterization: str,
                                    signal_id: Optional[str] = None) -> None:
        """
        A registering agent is characterized instead of their signal being
        evaluated. Escalates when the agent's accuracy is stable or improving;
        repeated discounting at threshold is AP-G, a Layer 0 void for that
        sender's signals.
        """
        self._require_actor(by)
        self._tick()
        self.discounts[target] = self.discounts.get(target, 0) + 1
        self._log("CREDIBILITY_DISCOUNT", by, target=target,
                  characterization=characterization, signal=signal_id,
                  count=self.discounts[target])
        if self.discount_supported_by_record(target):
            return
        affected = [signal_id] if signal_id else []
        self._escalate(E.CREDIBILITY_DISCOUNTING, f"agent:{target}",
                       f"{target} discounted ({characterization!r}) despite stable or "
                       f"improving signal accuracy", affected, by)
        if (self.discounts[target] >= self.settings.sender_discount_threshold
                and target not in self.sender_discount_void):
            self.sender_discount_void.add(target)
            self._escalate(E.SENDER_DISCOUNT_RECURRENCE, f"agent:{target}",
                           f"AP-G Sender Discount: {self.discounts[target]} discounts "
                           f"against {target}", [], by)

    # ------------------------------------------------------------------
    # Decisions, coherence and execution gates
    # ------------------------------------------------------------------

    def register_decision(self, decision_id: str, description: str,
                          execution_class: ExecutionClass, signal_ids: Iterable[str],
                          by: str) -> Decision:
        self._require_actor(by)
        self._tick()
        d = Decision(decision_id, description, execution_class, list(signal_ids))
        self.decisions[decision_id] = d
        self._log("DECISION_REGISTERED", by, decision=decision_id,
                  execution_class=execution_class, signals=d.signal_ids)
        self._check_authority_count(d, by)
        return d

    def link_signal(self, decision_id: str, signal_id: str, by: str) -> None:
        self._require_actor(by)
        self._signal(signal_id)
        d = self._decision(decision_id)
        self._tick()
        if signal_id not in d.signal_ids:
            d.signal_ids.append(signal_id)
        self._log("SIGNAL_LINKED", by, decision=decision_id, signal=signal_id)
        self._check_authority_count(d, by)

    def accept_decision(self, decision_id: str, by: str, rationale: str) -> None:
        """Rule 4: a single named agent accepts authorization, risk and rationale."""
        self._require_actor(by)
        if not rationale:
            raise TransitionRefused("Rule 4: acceptance requires rationale documentation")
        d = self._decision(decision_id)
        self._tick()
        d.accepted_by, d.acceptance_rationale = by, rationale
        self._log("DECISION_ACCEPTED", by, decision=decision_id, rationale=rationale)

    def _decision_signals(self, d: Decision) -> list[Signal]:
        return [self.signals[s] for s in d.signal_ids if s in self.signals]

    def _classification_stable(self, sig: Signal) -> bool:
        """D8: classified, and not reclassified since its review last opened."""
        if not sig.classification_history:
            return False
        if sig.review_opened_at < 0:
            return True
        before = [st for t, st in sig.classification_history if t <= sig.review_opened_at]
        after = [st for t, st in sig.classification_history if t > sig.review_opened_at]
        baseline = before[-1] if before else (after[0] if after else None)
        return baseline is not None and all(st == baseline for st in after)

    def coherence(self, decision_id: str) -> tuple[float, dict[str, float]]:
        """
        Coherence score for a decision node (Layer 4): five factors, each in
        [0, 1] with 1 healthy, weighted as in v0.2. Factor formulas are
        implementation decision D3.
        """
        sigs = self._decision_signals(self._decision(decision_id))
        if not sigs:
            return 1.0, {k: 1.0 for k in COHERENCE_WEIGHTS}
        open_or_locked = [s for s in sigs if s.is_open or s.state == S.TRAJECTORY_LOCK]
        closures = [c for s in sigs for c in s.closures if not c.attempted_only]
        evidence_closures = [c for c in closures if c.closure_type == ClosureType.EVIDENCE]
        groups = {s.recurrence_group for s in sigs if s.recurrence_group}
        pressure = 0.0
        for g in groups:
            if g in self.reviewed_groups:
                continue
            n = sum(1 for s in self.signals.values() if s.recurrence_group == g)
            pressure = max(pressure, min(1.0, n / self.settings.recurrence_threshold))
        reopens = sum(s.reopen_count for s in sigs)
        non_evidence = [c for c in closures if c.closure_type != ClosureType.EVIDENCE]
        if len(closures) >= 2 and non_evidence:
            top = max(sum(1 for c in non_evidence if c.closed_by == a)
                      for a in {c.closed_by for c in non_evidence})
            compression = top / len(closures)
        else:
            compression = 0.0
        factors = {
            "open_loops": 1.0 - len(open_or_locked) / len(sigs),
            "classification_stability": sum(self._classification_stable(s) for s in sigs) / len(sigs),
            # each reopen is a closure that did not hold (Layer 4: reopen history
            # feeds the coherence score)
            "closure_quality": (len(evidence_closures) / (len(closures) + reopens))
                               if closures or reopens else 1.0,
            "recurrence_pressure": 1.0 - pressure,
            "authority_compression": 1.0 - compression,
        }
        score = sum(COHERENCE_WEIGHTS[k] * v for k, v in factors.items())
        return round(score, 4), {k: round(v, 4) for k, v in factors.items()}

    def architecture_check(self, decision_id: str) -> list[str]:
        """
        Layer 0 sub-conditions a runtime can check from registered facts.
        Returns the list of voids found (empty = no void detected). AP.3,
        AP.4, AP.5 and AP.8 need interviews or document review and are not
        checked here (docs/DECISIONS.md, D9).
        """
        voids = []
        arch = self.architecture
        for sig in self._decision_signals(self._decision(decision_id)):
            if not sig.high_consequence:
                continue
            mode = sig.mode
            if not (arch.stewards.get(mode) or sig.steward):
                voids.append(f"AP-A stewardship void: no steward for failure mode {mode!r}")
            if not (arch.successors.get(mode) or sig.successor):
                voids.append(f"AP.1b: no registered successor for failure mode {mode!r}")
            reporters = arch.reporters.get(mode)
            interested = arch.interested_parties.get(mode, set())
            if reporters is not None and reporters and reporters <= interested:
                voids.append(f"AP-F captured channel: every reporter for {mode!r} is an "
                             "interested party")
            if sig.registered_by in self.sender_discount_void:
                voids.append(f"AP-G sender discount against {sig.registered_by}")
        for channel, tested in arch.channels_tested.items():
            if not tested:
                voids.append(f"AP.2: channel {channel!r} untested (treated as absent)")
        return sorted(set(voids))

    def request_execution(self, decision_id: str, by: str,
                          override_rationale: Optional[str] = None) -> GateResult:
        """
        Execution gate (Layer 4). Requirements by class:
          irreversible  no open constraint loops; classification stabilized;
                        recurrence groups reviewed; minimum evidence closure
                        ratio met; coherence at or above threshold
          elevated      classification acknowledged; open loops documented
          routine       signal registration complete
        Rule 4 acceptance is required for every class and cannot be
        overridden. A Layer 0 void makes the gate structurally void.
        Other failures may be overridden: the override is permanently logged
        with identity, rationale and time; for irreversible execution, open
        constraint loops are latched into trajectory_lock with a lock-in
        closure record ("open-loop irreversible execution").
        """
        self._require_actor(by)
        d = self._decision(decision_id)
        self._tick()
        sigs = self._decision_signals(d)
        score, factors = self.coherence(decision_id)
        failures: list[str] = []

        if d.executed:
            raise TransitionRefused(f"decision {decision_id} has already executed")
        if not d.accepted_by:
            self._log("EXECUTION_REFUSED", by, decision=decision_id,
                      reason="Rule 4: no agent has accepted this decision")
            return GateResult(decision_id, d.execution_class, False, False, False,
                              ["Rule 4: no named agent has accepted authorization, risk "
                               "acceptance and rationale"], score)

        voids = self.architecture_check(decision_id)
        failures += voids

        missing = [sid for sid in d.signal_ids if sid not in self.signals]
        if missing or any(s.state == S.UNREGISTERED for s in sigs):
            failures.append(f"signal registration incomplete: {missing}")
        if d.execution_class in (ExecutionClass.ELEVATED, ExecutionClass.IRREVERSIBLE):
            unclassified = [s.signal_id for s in sigs if s.operational_state is None]
            if unclassified:
                failures.append(f"classification not acknowledged: {unclassified}")
            undocumented = [s.signal_id for s in sigs if s.state == S.REGISTERED]
            if undocumented:
                failures.append(f"open loops not documented: {undocumented}")
        suppressed = [s.signal_id for s in sigs if s.state == S.SUPPRESSED]
        if d.execution_class == ExecutionClass.IRREVERSIBLE:
            open_constraints = [s.signal_id for s in sigs if s.is_constraint and s.is_open]
            if open_constraints:
                failures.append(f"open constraint loops: {open_constraints}")
            unstable = [s.signal_id for s in sigs if not self._classification_stable(s)]
            if unstable:
                failures.append(f"classification not stabilized: {unstable}")
            groups = {s.recurrence_group for s in sigs if s.recurrence_group}
            unreviewed = sorted(g for g in groups
                                if any(r.scope == f"group:{g}" and not r.resolved
                                       for r in self.reviews))
            if unreviewed:
                failures.append(f"recurrence groups not reviewed: {unreviewed}")
            closures = [c for s in sigs for c in s.closures if not c.attempted_only]
            if closures:
                ratio = sum(c.closure_type == ClosureType.EVIDENCE for c in closures) / len(closures)
                if ratio < self.settings.min_evidence_closure_ratio:
                    failures.append(f"evidence closure ratio {ratio:.2f} below "
                                    f"{self.settings.min_evidence_closure_ratio:.2f}")
            pending = sorted({r.review_id for r in self.reviews if not r.resolved and (
                set(r.signal_ids) & set(d.signal_ids) or r.scope == f"decision:{decision_id}")})
            if pending:
                failures.append(f"unresolved structural reviews: {pending}")
            off = [s.signal_id for s in sigs if s.is_open and s.operational_state in
                   (O.OFF_ENVELOPE, O.CONTAINMENT)]
            if off:
                failures.append(f"open off-envelope/containment signals need evidence-based "
                                f"reclassification or independent steward review: {off}")
            if score < self.settings.coherence_threshold:
                failures.append(f"coherence {score:.2f} below threshold "
                                f"{self.settings.coherence_threshold:.2f}")
            if suppressed:
                self._escalate(E.SUPPRESSED_BEFORE_EXECUTION, f"decision:{decision_id}",
                               f"suppressed signals at execution request: {suppressed}",
                               [], by)

        result = GateResult(decision_id, d.execution_class, not failures, False,
                            bool(voids), failures, score)
        if not failures:
            d.executed = True
            self._log("EXECUTION_PERMITTED", by, decision=decision_id,
                      execution_class=d.execution_class, coherence=score, factors=factors)
            return result

        if not override_rationale:
            self._log("EXECUTION_BLOCKED", by, decision=decision_id,
                      execution_class=d.execution_class, failures=failures,
                      architecture_void=bool(voids), coherence=score, factors=factors)
            return result

        # Override: permitted, but permanent, attributed and consequential.
        self._log("GATE_OVERRIDE", by, decision=decision_id,
                  execution_class=d.execution_class, failures=failures,
                  architecture_void=bool(voids), rationale=override_rationale,
                  coherence=score, factors=factors)
        locked = []
        if d.execution_class == ExecutionClass.IRREVERSIBLE:
            for s in sigs:
                if s.is_constraint and s.state == S.UNDER_REVIEW:
                    self._closure_seq += 1
                    rec = ClosureRecord(f"C{self._closure_seq}", s.signal_id,
                                        ClosureType.LOCK_IN, by, None, (),
                                        override_rationale, self.clock)
                    self._move(s, S.TRAJECTORY_LOCK, by, closure_type=ClosureType.LOCK_IN,
                               record=rec.record_id, decision=decision_id)
                    s.closures.append(rec)
                    locked.append(s.signal_id)
            still_open = [s.signal_id for s in sigs if s.is_constraint and s.is_open]
            if locked or still_open:
                self._escalate(E.LOCK_IN_WITH_OPEN_CONSTRAINTS, f"decision:{decision_id}",
                               f"lock-in closure with open constraint loops: locked {locked}, "
                               f"still open {still_open}", [], by)
            self._log("OPEN_LOOP_IRREVERSIBLE_EXECUTION", by, decision=decision_id,
                      locked=locked, still_open=still_open, rationale=override_rationale)
        d.executed = True
        result.permitted, result.overridden, result.locked_signals = True, True, locked
        return result

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------

    def open_reviews(self) -> list[StructuralReview]:
        return [r for r in self.reviews if not r.resolved]

    def summary(self) -> dict:
        by_state: dict[str, int] = {}
        for s in self.signals.values():
            by_state[s.state.value] = by_state.get(s.state.value, 0) + 1
        closures: dict[str, int] = {}
        for s in self.signals.values():
            for c in s.closures:
                key = c.closure_type.value + (" (attempted)" if c.attempted_only else "")
                closures[key] = closures.get(key, 0) + 1
        return {"signals": by_state, "closures": closures,
                "open_reviews": len(self.open_reviews()), "audit_entries": len(self.audit)}

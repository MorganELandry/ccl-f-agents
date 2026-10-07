"""
The commitment state machine (CCL-F v0.2, Layer 4).

TRANSITIONS is a direct transcription of the v0.2 transition listing. The
check is pure Python with no model involved: "its blocked transitions are
the supervisor's forbidden-event set, enforced structurally rather than by
convention."

Exits are handled separately (exit_allowed / reentry_allowed) because their
legality depends on the exit type, not only on the state.
"""

from __future__ import annotations

from typing import Optional

from .types import CommitmentState as S, ExitType as X, LegalSubtype as L, CLOSED_STATES


# (from, to) -> the condition the spec attaches to that transition
TRANSITIONS: dict[tuple[S, S], str] = {
    (S.UNREGISTERED, S.REGISTERED):        "signal enters the system",
    (S.REGISTERED, S.CLASSIFIED):          "Rule 2: required before review opens",
    (S.CLASSIFIED, S.UNDER_REVIEW):        "active analysis opened",
    (S.UNDER_REVIEW, S.CLOSED_EVIDENCE):   "new data resolves the constraint",
    (S.UNDER_REVIEW, S.CLOSED_AUTHORITY):  "senior override, no new evidence",
    (S.UNDER_REVIEW, S.CLOSED_ROLE_SWITCH): "same agent, different role",
    (S.UNDER_REVIEW, S.SUPPRESSED):        "signal lost operational visibility",
    (S.UNDER_REVIEW, S.ESCALATED):         "recurrence threshold crossed",
    (S.UNDER_REVIEW, S.TRAJECTORY_LOCK):   "revision capacity exhausted",
    # recovery
    (S.ESCALATED, S.UNDER_REVIEW):         "Rule 8 model update documented",
    (S.SUPPRESSED, S.UNDER_REVIEW):        "re-entry logged; suppression permanent",
    # reopen
    (S.CLOSED_EVIDENCE, S.UNDER_REVIEW):   "evidence invalidated or recurrence link",
    (S.CLOSED_AUTHORITY, S.UNDER_REVIEW):  "new evidence or recurrence linkage",
    (S.CLOSED_ROLE_SWITCH, S.UNDER_REVIEW): "mandatory independent review; L2 flag",
}

REOPEN_FROM = CLOSED_STATES

# Open states from which any exit may be taken ("any open state -> exited").
OPEN_STATES = frozenset({S.REGISTERED, S.CLASSIFIED, S.UNDER_REVIEW,
                         S.SUPPRESSED, S.ESCALATED})

# Re-entry from an exit into this automaton, by exit type (v0.2 listing).
REENTRY_STATED = frozenset({X.RECOVERABLE, X.DELEGATED})
REENTRY_INFERRED = frozenset({X.FORCED, X.EXHAUSTION, X.BOUNDARY, X.KEY_PERSON})
# Inferred re-entries that need a successor steward first (AP.1b).
REENTRY_NEEDS_SUCCESSOR = frozenset({X.FORCED, X.KEY_PERSON})
# Legal sub-types that "may resume to under_review when lifted".
LEGAL_RESUMABLE = frozenset({L.REGULATORY_INTERVENTION, L.INVESTIGATIVE_HOLD})
NO_REENTRY = frozenset({X.TERMINAL, X.SUPERSEDED, X.TIMEOUT})
# v0.2 Exit Checklist leaves these open; implementation decision D2: no
# automatic re-entry, re-register as a new linked signal instead.
OPEN_ENDED = frozenset({X.CONTAINMENT, X.DEFERRED, X.AMBIGUITY})
EXTERNAL = frozenset({X.WHISTLEBLOWER})
LEGAL = frozenset({X.LEGAL})


def check_transition(current: S, target: S) -> tuple[bool, str]:
    """
    Is current -> target in the v0.2 table? Returns (allowed, reason).

    The four structurally blocked transitions get their own named reasons,
    since they are the ones the spec singles out.
    """
    if (current, target) in TRANSITIONS:
        return True, TRANSITIONS[(current, target)]

    if target in CLOSED_STATES:
        if current in (S.UNREGISTERED, S.REGISTERED):
            return False, "BLOCKED: a signal cannot be closed before it is classified"
        if current == S.CLASSIFIED:
            return False, "BLOCKED: a classified signal cannot be closed before review opens"
        if current == S.SUPPRESSED:
            return False, ("BLOCKED: a suppressed signal cannot be silently closed; "
                           "it must re-enter review first")
        if current == S.ESCALATED:
            return False, ("BLOCKED: an escalated signal cannot be closed; structural "
                           "review must first document a model update (Rules 7-8)")
    if current in CLOSED_STATES and target != S.UNDER_REVIEW:
        return False, "BLOCKED: a closed loop can only be reopened into review"
    if current == S.TRAJECTORY_LOCK:
        return False, "BLOCKED: trajectory_lock is terminal"
    if current == S.EXITED:
        return False, "BLOCKED: exits leave only by the re-entry rule for their type"
    return False, f"BLOCKED: {current.value} -> {target.value} is not a v0.2 transition"


def exit_allowed(current: S) -> tuple[bool, str]:
    if current in OPEN_STATES:
        return True, "any open state -> exited(type)"
    return False, f"BLOCKED: only open signals can exit; signal is {current.value}"


def reentry_allowed(exit_type: X, legal_resumes: Optional[bool] = None,
                    legal_subtype: Optional[L] = None, has_successor: bool = False,
                    resumer_differs: bool = True) -> tuple[bool, str]:
    """
    May an exited signal of this type return to under_review?

      has_successor    a successor steward is registered (forced / key person)
      resumer_differs  the resuming agent is not the one who hit the boundary
    """
    if exit_type in REENTRY_STATED:
        return True, "re-entry stated in v0.2"
    if exit_type in REENTRY_NEEDS_SUCCESSOR and not has_successor:
        return False, ("BLOCKED: re-entry after this exit needs a registered successor "
                       "steward (AP.1b)")
    if exit_type == X.BOUNDARY and not resumer_differs:
        return False, ("BLOCKED: a boundary exit resumes only under a different agent with "
                       "covering authority")
    if exit_type in REENTRY_INFERRED:
        return True, "re-entry inferred in v0.2 (AP.1b / Autonomy-Bounded Closure)"
    if exit_type in LEGAL:
        if legal_subtype not in LEGAL_RESUMABLE:
            return False, ("BLOCKED: only a regulatory intervention or investigative hold "
                           "may resume when lifted; judicial orders and statutory triggers "
                           "depend on the order")
        if legal_resumes:
            return True, "legal exit lifted (regulatory intervention / investigative hold)"
        return False, "BLOCKED: legal exit resumes only when the external authority lifts it"
    if exit_type in EXTERNAL:
        return False, "BLOCKED: whistleblower exits re-enter through external jurisdiction"
    if exit_type in OPEN_ENDED:
        return False, ("BLOCKED: no re-entry transition is specified for this exit "
                       "(implementation decision D2: re-register as a new linked signal)")
    return False, "BLOCKED: terminal exit; no re-entry"

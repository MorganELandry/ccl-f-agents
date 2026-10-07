"""
THE RULEBOOK
A Play in Three Scenes
======================

PROLOGUE
--------
The commitment state machine (CCL-F v0.2, Layer 4).

TRANSITIONS is a direct transcription of the v0.2 transition listing. The
check is pure Python with no model involved: "its blocked transitions are
the supervisor's forbidden-event set, enforced structurally rather than by
convention."

Exits are handled separately (exit_allowed / reentry_allowed) because their
legality depends on the exit type, not only on the state.

Where this fits: these functions only *answer* "is this move legal, and
why?". They change nothing. The Supervisor (supervisor.py) asks them before
every state change, logs the answer to the audit trail, and refuses the
move (TransitionRefused) when the answer is no.

THE PLAYBILL (what happens in this file)
    Scene 1  check_transition()  is current -> target in the v0.2 table?
    Scene 2  exit_allowed()      may a signal in this state exit at all?
    Scene 3  reentry_allowed()   may an exited signal return to under_review?

READER'S NOTE — `import ... as` aliases
    `from .types import CommitmentState as S` makes S a short local name for
    CommitmentState, so the table below reads `S.UNDER_REVIEW` instead of
    `CommitmentState.UNDER_REVIEW`. Likewise X is ExitType and L is
    LegalSubtype. The leading dot in `.types` means "the types module in
    this same package (cclf)".

READER'S NOTE — the (allowed, reason) tuple
    Every function here returns a pair like (True, "active analysis opened")
    or (False, "BLOCKED: ..."). Callers unpack it as `ok, reason = ...`.
    The reason is written into the audit trail either way, so a refused move
    is as visible as an allowed one.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# Optional        Optional[X] means "an X, or None".
# S, X, L         short aliases for CommitmentState, ExitType, LegalSubtype.
# CLOSED_STATES   the three closed commitment states (from types.py).
# ===========================================================================

from __future__ import annotations

from typing import Optional

from .types import CommitmentState as S, ExitType as X, LegalSubtype as L, CLOSED_STATES


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# All of these are built only from the imported enums, so they all live up
# here. Each frozenset is a fixed, unchangeable group used for fast `in`
# tests (see the READER'S NOTE on frozenset in types.py).
# ===========================================================================

# TRANSITIONS — every allowed (from, to) state pair, mapped to the condition
#   text the spec writes beside it in the Commitment State Machine listing
#   (Layer 4). check_transition() looks pairs up here, and the text becomes
#   the "reason" logged with the transition. Anything not in this dict is
#   blocked. The type hint reads: a dict whose keys are (state, state)
#   tuples and whose values are str.
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
    # (the spec's RECOVERY TRANSITIONS: back into review)
    (S.ESCALATED, S.UNDER_REVIEW):         "Rule 8 model update documented",
    (S.SUPPRESSED, S.UNDER_REVIEW):        "re-entry logged; suppression permanent",
    # reopen
    # (the spec's REOPEN TRANSITIONS: "Closed states are stable but not
    # terminal", so false closure can be corrected)
    (S.CLOSED_EVIDENCE, S.UNDER_REVIEW):   "evidence invalidated or recurrence link",
    (S.CLOSED_AUTHORITY, S.UNDER_REVIEW):  "new evidence or recurrence linkage",
    (S.CLOSED_ROLE_SWITCH, S.UNDER_REVIEW): "mandatory independent review; L2 flag",
}

# REOPEN_FROM — the states a reopen may start from: exactly the closed
#   states. Another name for CLOSED_STATES that says what it is for here.
#   Not currently read elsewhere in the package.
REOPEN_FROM = CLOSED_STATES

# OPEN_STATES — states from which a signal may exit. Closed states, trajectory
#   lock, unregistered and already-exited signals are excluded.
# Open states from which any exit may be taken ("any open state -> exited").
OPEN_STATES = frozenset({S.REGISTERED, S.CLASSIFIED, S.UNDER_REVIEW,
                         S.SUPPRESSED, S.ESCALATED})

# --- Re-entry groups: one per kind of line in the spec's EXIT TRANSITIONS ---
# REENTRY_STATED — exits the spec directly says re-enter under_review
#   ("Re-entry into this same automaton, direct restatement").
# REENTRY_INFERRED — exits whose re-entry the spec marks as *inferred* from
#   AP.1b (Stewardship Succession) or Autonomy-Bounded Closure.
# Re-entry from an exit into this automaton, by exit type (v0.2 listing).
REENTRY_STATED = frozenset({X.RECOVERABLE, X.DELEGATED})
REENTRY_INFERRED = frozenset({X.FORCED, X.EXHAUSTION, X.BOUNDARY, X.KEY_PERSON})
# REENTRY_NEEDS_SUCCESSOR — of the inferred ones, those whose spec line says
#   "successor steward registered".
# Inferred re-entries that need a successor steward first (AP.1b).
REENTRY_NEEDS_SUCCESSOR = frozenset({X.FORCED, X.KEY_PERSON})
# LEGAL_RESUMABLE — legal sub-types that can come back into review.
# Legal sub-types that "may resume to under_review when lifted".
LEGAL_RESUMABLE = frozenset({L.REGULATORY_INTERVENTION, L.INVESTIGATIVE_HOLD})
# NO_REENTRY — exits marked "[no transition]" (terminal, superseded,
#   timeout). Not read by reentry_allowed(): these simply fall through to its
#   final "terminal exit" refusal. Kept as documentation of the spec group.
NO_REENTRY = frozenset({X.TERMINAL, X.SUPERSEDED, X.TIMEOUT})
# OPEN_ENDED — exits marked "[no transition specified]"; the spec calls this
#   "a genuine specification gap".
# v0.2 Exit Checklist leaves these open; implementation decision D2: no
# automatic re-entry, re-register as a new linked signal instead.
OPEN_ENDED = frozenset({X.CONTAINMENT, X.DEFERRED, X.AMBIGUITY})
# EXTERNAL — exits that go to "[external process]", not back into this
#   automaton.
EXTERNAL = frozenset({X.WHISTLEBLOWER})
# LEGAL — exits whose re-entry "[depends on sub-type]" (see LEGAL_RESUMABLE).
LEGAL = frozenset({X.LEGAL})


# ===========================================================================
# SCENE 1 — THE GATEKEEPER
# check_transition(): is this state change allowed, and why (or why not)?
# ===========================================================================

def check_transition(current: S, target: S) -> tuple[bool, str]:
    """
    Is current -> target in the v0.2 table? Returns (allowed, reason).

    The four structurally blocked transitions get their own named reasons,
    since they are the ones the spec singles out.

    Enter:   current   the signal's CommitmentState now
             target    the CommitmentState it would move to
    Exit:    (True, the spec's condition text) if the pair is in TRANSITIONS
             (False, "BLOCKED: ...") otherwise, naming the specific rule

    The spec's four blocked transitions (Layer 4) and where they appear:
      "cannot be closed before it is classified"       -> first BLOCKED
      "cannot be closed before review opens"           -> second
      "A suppressed signal cannot be silently closed"  -> third
      "A closed loop cannot be silently reopened"      -> enforced by the
          Supervisor (reopen needs a rationale); here, a closed loop may only
          go back to under_review
    Escalated, trajectory_lock and exited get their own messages too.
    Exits are not checked here: see exit_allowed().
    """
    # --- Allowed: the pair is in the spec's table ---------------------------
    if (current, target) in TRANSITIONS:
        return True, TRANSITIONS[(current, target)]

    # --- Blocked: an attempt to close from the wrong state ------------------
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
    # --- Blocked: a closed loop going anywhere but back into review ---------
    if current in CLOSED_STATES and target != S.UNDER_REVIEW:
        return False, "BLOCKED: a closed loop can only be reopened into review"
    # --- Blocked: terminal and exited states --------------------------------
    if current == S.TRAJECTORY_LOCK:
        return False, "BLOCKED: trajectory_lock is terminal"
    if current == S.EXITED:
        return False, "BLOCKED: exits leave only by the re-entry rule for their type"
    # --- Blocked: anything else simply is not in the table ------------------
    # `.value` gives the plain string, e.g. "registered".
    return False, f"BLOCKED: {current.value} -> {target.value} is not a v0.2 transition"


# ===========================================================================
# SCENE 2 — THE WAY OUT
# exit_allowed(): may a signal in this state exit?
# ===========================================================================

def exit_allowed(current: S) -> tuple[bool, str]:
    """
    May a signal in this state take any exit?

    Enter:   current   the signal's CommitmentState
    Exit:    (True, ...) if current is in OPEN_STATES ("any open state ->
             exited(type)"), else (False, "BLOCKED: ...")

    The exit type does not matter here; the spec allows every type from
    every open state. What each type obliges is checked by the Supervisor.
    """
    if current in OPEN_STATES:
        return True, "any open state -> exited(type)"
    return False, f"BLOCKED: only open signals can exit; signal is {current.value}"


# ===========================================================================
# SCENE 3 — THE WAY BACK IN
# reentry_allowed(): may an exited signal return to under_review?
# ===========================================================================

def reentry_allowed(exit_type: X, legal_resumes: Optional[bool] = None,
                    legal_subtype: Optional[L] = None, has_successor: bool = False,
                    resumer_differs: bool = True) -> tuple[bool, str]:
    """
    May an exited signal of this type return to under_review?

      has_successor    a successor steward is registered (forced / key person)
      resumer_differs  the resuming agent is not the one who hit the boundary

    Enter:   exit_type        the ExitType the signal left by
             legal_resumes    for legal exits: has the external authority
                              lifted it? (None if not applicable)
             legal_subtype    for legal exits: which LegalSubtype
             has_successor    see above
             resumer_differs  see above
    Exit:    (allowed, reason)

    The checks run in order and the first match wins, following the spec's
    EXIT TRANSITIONS groups:
      1. stated re-entry (recoverable, delegated)         -> allowed
      2. forced / key person without a successor          -> blocked (AP.1b)
      3. boundary resumed by the same agent               -> blocked
      4. other inferred re-entries                        -> allowed
      5. legal: only resumable sub-types, only when lifted
      6. whistleblower                                    -> external process
      7. containment / deferred / ambiguity               -> blocked (D2)
      8. anything left (terminal, superseded, timeout)    -> blocked
    Steps 2 and 3 come before step 4 so their extra conditions are enforced
    before the general "inferred re-entry" permission.
    """
    # --- 1. Re-entry the spec states directly -------------------------------
    if exit_type in REENTRY_STATED:
        return True, "re-entry stated in v0.2"
    # --- 2. Forced / key person need a successor steward first (AP.1b) ------
    if exit_type in REENTRY_NEEDS_SUCCESSOR and not has_successor:
        return False, ("BLOCKED: re-entry after this exit needs a registered successor "
                       "steward (AP.1b)")
    # --- 3. Boundary exits need a different agent (Autonomy-Bounded Closure)
    if exit_type == X.BOUNDARY and not resumer_differs:
        return False, ("BLOCKED: a boundary exit resumes only under a different agent with "
                       "covering authority")
    # --- 4. Inferred re-entries whose conditions are now met ----------------
    if exit_type in REENTRY_INFERRED:
        return True, "re-entry inferred in v0.2 (AP.1b / Autonomy-Bounded Closure)"
    # --- 5. Legal exits: depends on the sub-type, and on the authority ------
    if exit_type in LEGAL:
        if legal_subtype not in LEGAL_RESUMABLE:
            return False, ("BLOCKED: only a regulatory intervention or investigative hold "
                           "may resume when lifted; judicial orders and statutory triggers "
                           "depend on the order")
        if legal_resumes:
            return True, "legal exit lifted (regulatory intervention / investigative hold)"
        return False, "BLOCKED: legal exit resumes only when the external authority lifts it"
    # --- 6. Whistleblower: re-enters elsewhere, not here --------------------
    if exit_type in EXTERNAL:
        return False, "BLOCKED: whistleblower exits re-enter through external jurisdiction"
    # --- 7. Open-ended exits: spec gap, implementation decision D2 ----------
    if exit_type in OPEN_ENDED:
        return False, ("BLOCKED: no re-entry transition is specified for this exit "
                       "(implementation decision D2: re-register as a new linked signal)")
    # --- 8. Terminal, superseded, timeout -----------------------------------
    return False, "BLOCKED: terminal exit; no re-entry"

# EXEUNT — end of file.

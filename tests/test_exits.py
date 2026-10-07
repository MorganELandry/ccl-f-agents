"""
FOURTEEN WAYS TO LEAVE THE STAGE
A Play in Twelve Scenes
================================

PROLOGUE
--------
Tests for Supervisor.exit() and Supervisor.reenter(), derived from the CCL-F
v0.2 Loop Exit Taxonomy (spec lines 522-553) and the exit transitions of
the Layer 4 state machine (lines 894-933, 944).

The taxonomy has fourteen exit types. Each one says what obligations
survive the exit and whether the loop may be re-entered:

  Obligations (line 553):
    terminal, legal, key person   explicit notation of the open loop state
    delegated                     successor registered before the exit is valid
    whistleblower                 external pathway AND the triggering
                                  suppression event permanently recorded
    every type                    an audit trail entry (an unregistered exit
                                  "is structurally equivalent to a suppressed
                                  signal")
  Re-entry into this automaton's under_review (lines 897-932):
    stated      recoverable, delegated
    inferred    forced, exhaustion, boundary, key person
    none        terminal, superseded, timeout
    unspecified containment, deferred, ambiguity (a spec gap; the code's
                choice D2 is "no re-entry, register a new linked signal")
    external    whistleblower (re-entered through external jurisdiction)
    legal       depends on sub-type: regulatory intervention / investigative
                hold may resume when lifted

THE PLAYBILL
    Scene 1   test_every_exit_type_is_recorded            (parametrized, 14 runs)
    Scene 2   test_open_loop_state_notation_required       (parametrized, 3 runs)
    Scene 3   test_delegated_exit_requires_successor
    Scene 4   test_whistleblower_exit_requires_pathway_and_suppression
    Scene 5   test_legal_exit_requires_sub_type
    Scene 6   test_only_open_signals_can_exit
    Scene 7   test_reentry_by_exit_type                    (parametrized, 13 runs)
    Scene 8   test_open_ended_exits_have_no_reentry        (impl. decision D2)
    Scene 9   test_legal_exit_resumes_only_when_lifted     (parametrized, 2 runs)
    Scene 10  test_statutory_trigger_does_not_resume       (was a spec mismatch; now fixed)
    Scene 11  test_successor_reentry_needs_a_successor     (was a spec mismatch; now fixed)
    Scene 12  test_refused_reentry_is_logged_and_changes_nothing

READER'S NOTE — building keyword arguments with a dict
    `sv.exit(..., **extras)` unpacks a dict into keyword arguments, so
    {"successor": "x"} becomes successor="x". OBLIGATIONS below holds, for
    each exit type, the extra arguments that satisfy its obligations.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       fixtures, parametrize, raises, xfail.
# cclf         CommitmentState, ExitType, LegalSubtype, SignalType,
#              Supervisor, TransitionRefused.
# stagehands   CUST, to_review, entries.
# ===========================================================================

import pytest

from cclf import (
    CommitmentState, ExitType, LegalSubtype, SignalType, Supervisor, TransitionRefused,
)
from stagehands import CUST, entries, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# S, X — short aliases for CommitmentState and ExitType.
S = CommitmentState
X = ExitType

# OBLIGATIONS — for each exit type, the extra exit() arguments that meet the
#   obligations of line 553 (and a sub-type for legal exits, line 547).
#   Types with no special obligation get an empty dict.
OBLIGATIONS = {
    X.TERMINAL: {"open_loop_state": "constraint unresolved at exit"},
    X.LEGAL: {"open_loop_state": "under review when the order arrived",
              "legal_subtype": LegalSubtype.REGULATORY_INTERVENTION},
    X.KEY_PERSON: {"open_loop_state": "open, steward departed"},
    X.DELEGATED: {"successor": "new-steward"},
    X.WHISTLEBLOWER: {"external_pathway": "Rogers Commission testimony",
                      "suppression_ref": "audit seq 12"},
}

# REENTRY_EXPECTED — from the spec listing, whether each type (except legal,
#   which depends on its sub-type) may return to under_review.
REENTRY_EXPECTED = {
    X.RECOVERABLE: True, X.DELEGATED: True,
    X.FORCED: True, X.EXHAUSTION: True, X.BOUNDARY: True, X.KEY_PERSON: True,
    X.TERMINAL: False, X.SUPERSEDED: False, X.TIMEOUT: False,
    X.CONTAINMENT: False, X.DEFERRED: False, X.AMBIGUITY: False,
    X.WHISTLEBLOWER: False,
}


# ===========================================================================
# THE FIXTURE AND A HELPER
# ===========================================================================

@pytest.fixture
def sv():
    """
    A Supervisor with one constraint signal "c" under review.

    Enter:   (nothing)
    Exit:    the Supervisor
    """
    # PLAYERS IN THIS SCENE
    #   s   the new Supervisor

    s = Supervisor()
    to_review(s, "c", by="steward")
    return s


def do_exit(sv, exit_type, by="steward"):
    """
    Exit signal "c" with exactly the obligations its type requires.

    Enter:   sv          a Supervisor holding signal "c"
             exit_type   which of the fourteen types
             by          the exiting agent
    Exit:    the ExitRecord
    """
    return sv.exit("c", exit_type, by, f"{exit_type.value} exit",
                   **OBLIGATIONS.get(exit_type, {}))


# ===========================================================================
# SCENE 1 — EVERY EXIT LEAVES A MARK
# Proves: all fourteen types exist, each one moves the signal to exited,
# keeps a typed ExitRecord, and is logged (line 553: "Every exit type
# generates audit trail obligations"). (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("exit_type", list(X), ids=lambda x: x.value)
def test_every_exit_type_is_recorded(sv, exit_type):
    """
    An exit of each type is recorded on the signal and in the audit trail.

    Enter:   sv          fixture
             exit_type   each ExitType
    Exit:    passes if there are fourteen types, the signal is exited with
             a matching ExitRecord, and one EXIT entry names the type and actor
    """
    # PLAYERS IN THIS SCENE
    #   record   the ExitRecord
    #   logged   the EXIT audit entries

    assert len(X) == 14
    record = do_exit(sv, exit_type)
    assert sv.signals["c"].state == S.EXITED
    assert sv.signals["c"].exit == record and record.exit_type == exit_type
    logged = entries(sv, "EXIT")
    assert len(logged) == 1
    assert logged[0].payload["exit_type"] == exit_type.value
    assert logged[0].actor == "steward"


# ===========================================================================
# SCENE 2 — SAY WHAT WAS LEFT OPEN
# Proves: line 553, terminal, legal and key person exits "require explicit
# notation of the open loop state at the time of exit". (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("exit_type", [X.TERMINAL, X.LEGAL, X.KEY_PERSON],
                         ids=lambda x: x.value)
def test_open_loop_state_notation_required(sv, exit_type):
    """
    Without an open-loop-state note the exit is refused; with one, it is stored.

    Enter:   sv          fixture
             exit_type   TERMINAL, LEGAL or KEY_PERSON
    Exit:    passes if the bare exit raises and leaves the signal under
             review, and the full exit stores the note verbatim
    """
    # PLAYERS IN THIS SCENE
    #   extras   the obligations minus the open-loop-state note

    extras = {k: v for k, v in OBLIGATIONS[exit_type].items() if k != "open_loop_state"}
    with pytest.raises(TransitionRefused):
        sv.exit("c", exit_type, "steward", "leaving", **extras)
    assert sv.signals["c"].state == S.UNDER_REVIEW
    record = do_exit(sv, exit_type)
    assert record.open_loop_state == OBLIGATIONS[exit_type]["open_loop_state"]


# ===========================================================================
# SCENE 3 — NO HANDOVER WITHOUT AN HEIR
# Proves: line 553, "Delegated exits require successor registration before
# the exit is valid"; line 532, "Open — new steward registered".
# ===========================================================================

def test_delegated_exit_requires_successor(sv):
    """
    A delegated exit without a successor is refused; with one, the steward changes.

    Enter:   sv   fixture
    Exit:    passes if the bare exit raises and the full exit makes the
             successor the signal's steward
    """
    with pytest.raises(TransitionRefused):
        sv.exit("c", X.DELEGATED, "steward", "handing over")
    do_exit(sv, X.DELEGATED)
    assert sv.signals["c"].steward == "new-steward"


# ===========================================================================
# SCENE 4 — THE WHISTLE AND WHY IT BLEW
# Proves: line 553, whistleblower exits require "the external escalation
# pathway and the suppression event that triggered it" permanently recorded.
# ===========================================================================

def test_whistleblower_exit_requires_pathway_and_suppression(sv):
    """
    Either missing piece refuses the exit; both are logged when present.

    Enter:   sv   fixture
    Exit:    passes if pathway-only and suppression-only exits raise, and
             the full exit's EXIT entry carries both
    """
    # PLAYERS IN THIS SCENE
    #   full   the complete whistleblower obligations
    #   key    one obligation to leave out

    full = OBLIGATIONS[X.WHISTLEBLOWER]
    for key in full:
        with pytest.raises(TransitionRefused):
            sv.exit("c", X.WHISTLEBLOWER, "boisjoly", "go external",
                    **{k: v for k, v in full.items() if k != key})
    do_exit(sv, X.WHISTLEBLOWER, by="boisjoly")
    payload = entries(sv, "EXIT")[0].payload
    assert payload["external_pathway"] == full["external_pathway"]
    assert payload["suppression_ref"] == full["suppression_ref"]


# ===========================================================================
# SCENE 5 — WHICH KIND OF LAW?
# Proves: line 547, legal exit "has four sub-types"; the runtime needs to
# know which one (re-entry depends on it, line 926).
# ===========================================================================

def test_legal_exit_requires_sub_type(sv):
    """
    A legal exit without a sub-type is refused.

    Enter:   sv   fixture
    Exit:    passes if the exit raises TransitionRefused
    """
    with pytest.raises(TransitionRefused):
        sv.exit("c", X.LEGAL, "regulator", "order", open_loop_state="open")


# ===========================================================================
# SCENE 6 — YOU CANNOT LEAVE WHAT IS ALREADY SETTLED
# Proves: line 895, exits leave from "any open state": not from a closed
# state, and not twice.
# ===========================================================================

def test_only_open_signals_can_exit(sv):
    """
    Exiting a closed signal, or an already-exited one, is refused.

    Enter:   sv   fixture
    Exit:    passes if both exits raise
    """
    to_review(sv, "closed-one", signal_type=SignalType.UNCERTAINTY)
    sv.attempt_closure("closed-one", "vp", CUST)
    with pytest.raises(TransitionRefused):
        sv.exit("closed-one", X.SUPERSEDED, "vp", "moot")
    do_exit(sv, X.SUPERSEDED)
    with pytest.raises(TransitionRefused):
        do_exit(sv, X.SUPERSEDED)


# ===========================================================================
# SCENE 7 — WHO MAY COME BACK
# Proves: the re-entry column of the state machine listing for every type
# except legal (Scene 9). (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("exit_type", list(REENTRY_EXPECTED), ids=lambda x: x.value)
def test_reentry_by_exit_type(sv, exit_type):
    """
    reenter() succeeds exactly for the types the spec gives a re-entry path.

    Enter:   sv          fixture
             exit_type   every type except LEGAL
    Exit:    passes if allowed types return to under_review (and log
             REENTRY) and the rest raise and stay exited
    """
    do_exit(sv, exit_type)
    if REENTRY_EXPECTED[exit_type]:
        sv.reenter("c", "new-steward", "conditions met")
        assert sv.signals["c"].state == S.UNDER_REVIEW
        assert entries(sv, "REENTRY")[0].payload["exit_type"] == exit_type.value
    else:
        with pytest.raises(TransitionRefused):
            sv.reenter("c", "anyone", "trying to come back")
        assert sv.signals["c"].state == S.EXITED


# ===========================================================================
# SCENE 8 — THE SPEC'S OWN GAP
# Proves (implementation decision D2): containment, deferred and ambiguity
# exits have no re-entry, and the refusal says why.
# ===========================================================================

def test_open_ended_exits_have_no_reentry(sv):
    """
    Implementation-decision test (D2). The spec lists these three as
    "[no transition specified]" and calls it "a genuine specification gap"
    (lines 906-911). The code refuses re-entry and points to re-registering
    as a new linked signal; the refusal reason must name D2.

    Enter:   sv   fixture
    Exit:    passes if the refusal message mentions D2
    """
    do_exit(sv, X.DEFERRED)
    with pytest.raises(TransitionRefused, match="D2"):
        sv.reenter("c", "steward", "conditions now exist")


# ===========================================================================
# SCENE 9 — WHEN THE REGULATOR LIFTS THE HOLD
# Proves: line 926, "regulatory intervention/investigative hold may resume
# to under_review when lifted", and not before. (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("subtype", [LegalSubtype.REGULATORY_INTERVENTION,
                                     LegalSubtype.INVESTIGATIVE_HOLD], ids=lambda s: s.value)
def test_legal_exit_resumes_only_when_lifted(sv, subtype):
    """
    A legal exit stays put until the authority lifts it, then may resume.

    Enter:   sv        fixture
             subtype   REGULATORY_INTERVENTION or INVESTIGATIVE_HOLD
    Exit:    passes if reenter without legal_resumes raises and with
             legal_resumes=True returns to under_review
    """
    sv.exit("c", X.LEGAL, "regulator", "halt ordered", open_loop_state="open",
            legal_subtype=subtype)
    with pytest.raises(TransitionRefused):
        sv.reenter("c", "steward", "we would like to continue")
    sv.reenter("c", "steward", "hold lifted", legal_resumes=True)
    assert sv.signals["c"].state == S.UNDER_REVIEW


# ===========================================================================
# SCENE 10 — THE LAW THAT ENDS THE LOOP
# Proves: a statutory trigger "automatically terminates
# or transfers the loop" (line 547); it is not a hold that lifts.
# ===========================================================================

def test_statutory_trigger_does_not_resume(sv):
    """
    A statutory-trigger legal exit cannot resume into this automaton.

    Enter:   sv   fixture
    Exit:    passes if reenter(..., legal_resumes=True) raises
    """
    sv.exit("c", X.LEGAL, "legislature", "statute", open_loop_state="open",
            legal_subtype=LegalSubtype.STATUTORY_TRIGGER)
    with pytest.raises(TransitionRefused):
        sv.reenter("c", "steward", "resume", legal_resumes=True)


# ===========================================================================
# SCENE 11 — NO RETURN WITHOUT A SUCCESSOR
# Proves: forced and key-person re-entry is conditioned
# on "successor steward registered" (lines 916, 920).
# ===========================================================================

@pytest.mark.parametrize("exit_type", [X.FORCED, X.KEY_PERSON], ids=lambda x: x.value)
def test_successor_reentry_needs_a_successor(exit_type):
    """
    A forced or key-person exit with no successor registered cannot re-enter.

    Enter:   exit_type   FORCED or KEY_PERSON
    Exit:    passes if reenter raises TransitionRefused
    """
    # PLAYERS IN THIS SCENE
    #   sv   a Supervisor whose signal has a steward but no successor

    sv = Supervisor()
    to_review(sv, "c", by="steward", successor=None)
    sv.exit("c", exit_type, "org", "steward gone", **OBLIGATIONS.get(exit_type, {}))
    with pytest.raises(TransitionRefused):
        sv.reenter("c", "someone", "resume")


# ===========================================================================
# SCENE 12 — A DOOR THAT STAYS SHUT, ON THE RECORD
# Proves: a refused re-entry is itself logged (the audit trail records
# refusals as well as transitions) and changes nothing.
# ===========================================================================

def test_refused_reentry_is_logged_and_changes_nothing(sv):
    """
    A refused re-entry logs REENTRY_REFUSED and leaves the exit record in place.

    Enter:   sv   fixture
    Exit:    passes if the entry exists with the actor and the signal stays exited
    """
    do_exit(sv, X.TERMINAL)
    with pytest.raises(TransitionRefused):
        sv.reenter("c", "manager", "on second thoughts")
    assert [e.actor for e in entries(sv, "REENTRY_REFUSED")] == ["manager"]
    assert sv.signals["c"].state == S.EXITED and sv.signals["c"].exit is not None

# EXEUNT — end of file.

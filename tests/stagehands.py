"""
THE STAGEHANDS
A Play in Six Scenes
====================

PROLOGUE
--------
Shared helpers for the CCL-F v0.2 runtime tests. This file holds no tests
(its name does not start with "test_", so pytest never collects it); it
holds the small, repetitive set-up moves that nearly every test file needs:
put a signal into review, add a piece of evidence that passes the External
Evidence Source test, register and accept a decision, and pull audit
entries out by event name.

Every helper builds its world through the Supervisor's public methods, the
same way a real caller would. Nothing here reaches into private state.

Why a shared module? pytest.ini puts tests/ on the import path
(`pythonpath = . tests`), so any test file can write
`from stagehands import ...`. Keeping the set-up here means each test only
shows the part of the story it is about.

THE PLAYBILL
    (DRAMATIS PERSONAE also holds ATTESTER, RULE3, UPDATE and
    UPDATE_AT_LEVEL: the independent risk-evidence attester, and the
    complete Rule 3 registration and Rule 8 updates the October 2026 gate
    and review rules require, ready to pass as keyword arguments.)
    Scene 1   to_review()         register, classify and open review on a signal
    Scene 2   add_ees()           add evidence that qualifies as EES
    Scene 3   add_non_ees()       add evidence of a kind that never qualifies
    Scene 4   decision()          register (and by default accept) a decision
    Scene 4b  attest()            independent attestation of the risk evidence
    Scene 5   entries()           the audit entries carrying one event name
    Scene 6   transitions()       (from, to) pairs of every logged TRANSITION

READER'S NOTE — why signals get a steward and successor by default
    The execution gate runs the Layer 0 (Architecture Precondition) checks
    on every constraint and anomaly signal: no steward is an AP-A void, no
    successor is an AP.1b void. Tests about other gate rules would trip over
    those voids, so to_review() supplies both unless a test says otherwise.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# cclf      the runtime under test. From it we use:
#   Supervisor        the Layer 4 supervisor that owns all state
#   SignalType        the six signal types (Rule 1)
#   OperationalState  the five operational states (Rule 2)
#   Referent          technical vs customer (R5.3)
#   EvidenceKind      what kind of process produced a piece of evidence
#   ExecutionClass    irreversible / elevated / routine
#   Power             the granted powers (attest() grants OVERRIDE)
# ===========================================================================

from cclf import (
    EvidenceKind, ExecutionClass, OperationalState, Power, Referent, SignalType, Supervisor,
)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# TECH, CUST — short names for the two R5.3 referents, used everywhere.
TECH = Referent.TECHNICAL
CUST = Referent.CUSTOMER

# PROCESS — the "evaluated process" every helper-made signal is about.
#   The EES test refuses evidence produced by this process.
PROCESS = "program-under-evaluation"

# INDEPENDENT_LAB — a producer with no causal tie to PROCESS or to any
#   registrant used in the tests, so its evidence can qualify as EES.
INDEPENDENT_LAB = "independent-lab"

# ATTESTER — an independent agent (never an acceptor or requester in the
#   tests) who attests that an acceptance's evidence bears on its risk claim.
ATTESTER = "risk-attester"

# RULE3 — a complete Rule 3 registration ("what is known, what is assumed,
#   and what remains genuinely uncertain"), as accept_decision keywords.
RULE3 = dict(known="the measured margins", assumed="the load model holds",
             uncertain="behaviour beyond the tested range")

# UPDATE — a complete Rule 8 update for resolve_review: an update text and
#   the registered elements it changes. Recurrence reviews also need a
#   level (UPDATE_AT_LEVEL).
UPDATE = dict(model_update="tighten the gate parameter",
              elements_changed=["gate parameter: inspection interval"])
UPDATE_AT_LEVEL = dict(UPDATE, level="the design process that generates the instances")


# ===========================================================================
# SCENE 1 — INTO THE REVIEW ROOM
# to_review(): take a fresh signal all the way to under_review.
# ===========================================================================

def to_review(sv: Supervisor, signal_id: str, signal_type=SignalType.CONSTRAINT,
              by: str = "engineer", referent=TECH,
              state=OperationalState.ELEVATED_UNCERTAINTY, **kwargs):
    """
    Register, classify and open review on one signal.

    Enter:   sv            the Supervisor to act on
             signal_id     the new signal's ID
             signal_type   defaults to CONSTRAINT
             by            the registrant (also classifies and opens review)
             referent      the registrant's referent (defaults to technical)
             state         the operational state to classify it as
             **kwargs      passed on to register_signal (steward, successor,
                           closure_authority, recurrence_group, ...)
    Exit:    the Signal object (it may be under_review or, if a pending
             escalation names it, already escalated)
    """
    # PLAYERS IN THIS SCENE
    #   sig   the newly registered Signal (returned)

    # --- Supply a steward and successor unless the caller chose otherwise --
    kwargs.setdefault("steward", "steward")
    kwargs.setdefault("successor", "successor")
    # --- The three lifecycle moves -----------------------------------------
    sig = sv.register_signal(signal_id, signal_type, f"signal {signal_id}", by, referent,
                             PROCESS, **kwargs)
    sv.classify(signal_id, state, by)
    sv.open_review(signal_id, by)
    return sig


# ===========================================================================
# SCENE 2 — A WITNESS FROM OUTSIDE
# add_ees(): evidence that passes the External Evidence Source test.
# ===========================================================================

def add_ees(sv: Supervisor, evidence_id: str, signal_ids=(),
            kind=EvidenceKind.DIRECT_MEASUREMENT, produced_by: str = INDEPENDENT_LAB):
    """
    Add one item of EES-eligible evidence from an independent producer.

    Enter:   sv, evidence_id   where and under what ID
             signal_ids        signals to attach it to (optional)
             kind              an EES-eligible kind (default direct measurement)
             produced_by       the producing process (default INDEPENDENT_LAB)
    Exit:    the Evidence object; its `at` is the supervisor's clock now,
             so it is "novel" for any signal registered before this call
    """
    return sv.add_evidence(evidence_id, f"evidence {evidence_id}", "test", kind,
                           produced_by, "evidence-clerk", signal_ids)


# ===========================================================================
# SCENE 3 — A WITNESS WHO DOES NOT COUNT
# add_non_ees(): evidence of a kind the EES test always refuses.
# ===========================================================================

def add_non_ees(sv: Supervisor, evidence_id: str, kind, signal_ids=()):
    """
    Add one item of evidence whose kind can never be an External Evidence Source.

    Enter:   sv, evidence_id   where and under what ID
             kind              MODEL_OUTPUT, ASSERTION or INTERNAL_ANALYSIS
             signal_ids        signals to attach it to (optional)
    Exit:    the Evidence object, produced by INDEPENDENT_LAB so that only
             its kind (not its producer) can be the reason it fails EES
    """
    return sv.add_evidence(evidence_id, f"evidence {evidence_id}", "test", kind,
                           INDEPENDENT_LAB, "evidence-clerk", signal_ids)


# ===========================================================================
# SCENE 4 — THE DECISION ON THE TABLE
# decision(): register an execution-class decision, accepted by default.
# ===========================================================================

def decision(sv: Supervisor, decision_id: str, signal_ids,
             execution_class=ExecutionClass.IRREVERSIBLE, accept: bool = True,
             by: str = "director", reversible: bool = True, risk_checked: bool = True,
             root=None):
    """
    Register a decision and (unless accept=False) have one agent accept it.

    Enter:   sv, decision_id    where and under what ID
             signal_ids         the signals the decision depends on
             execution_class    defaults to IRREVERSIBLE
             accept             give Rule 4 acceptance with a rationale?
             by                 the registering and accepting agent
             reversible         for ROUTINE or ELEVATED: register a reversal
                                path with independent-lab evidence that it
                                was tested, so the declared class applies
                                (default). False registers the lower class
                                with no reversal path, so the gate treats it
                                as irreversible (Execution Class Assignment).
             risk_checked       with accept: name a principal risk claim,
                                cite independent-lab evidence for it
                                ("risk-check-<decision_id>"), record the
                                Rule 3 registration, and have ATTESTER
                                attest that the evidence bears on the claim,
                                so the irreversible gate's risk-claim and
                                Rule 3 tests pass (default). False accepts
                                with the rationale only, as tests of those
                                tests need.
             root               with authority enforced: the root that
                                grants ATTESTER the OVERRIDE power it needs
                                (see attest())
    Exit:    the Decision object
    """
    # PLAYERS IN THIS SCENE
    #   path, evidence   the reversal path and its evidence ids, if any
    #   d                the new Decision
    #   risk             keyword arguments for the risk claim and Rule 3

    path, evidence = None, ()
    if execution_class != ExecutionClass.IRREVERSIBLE and reversible:
        add_ees(sv, f"reversal-test-{decision_id}")
        path, evidence = f"documented rollback for {decision_id}", (f"reversal-test-{decision_id}",)
    d = sv.register_decision(decision_id, f"decision {decision_id}", execution_class,
                             signal_ids, by, reversal_path=path, reversal_evidence_ids=evidence)
    if accept:
        risk = {}
        if risk_checked:
            add_ees(sv, f"risk-check-{decision_id}")
            risk = dict(evidence_ids=[f"risk-check-{decision_id}"],
                        risk_claim=f"{decision_id} is safe to execute", **RULE3)
        sv.accept_decision(decision_id, by, "I accept authorization, risk and rationale",
                           **risk)
        if risk_checked:
            attest(sv, decision_id, root)
    return d


# ===========================================================================
# SCENE 4b — A SECOND PAIR OF EYES
# attest(): have ATTESTER attest a decision's risk evidence.
# ===========================================================================

def attest(sv: Supervisor, decision_id: str, root=None):
    """
    Have ATTESTER attest that the decision's acceptance evidence bears on
    its principal risk claim.

    Enter:   sv, decision_id   an accepted decision naming a risk claim
             root              with authority enforced: the root that grants
                               ATTESTER OVERRIDE over the decision's scope
                               first (the attester must hold it)
    Exit:    the RiskAttestation
    """
    if root is not None:
        sv.grant(ATTESTER, Power.OVERRIDE, sv.decisions[decision_id].scope, by=root)
    return sv.attest_risk_evidence(decision_id, ATTESTER, "the cited evidence measures the claim")


# ===========================================================================
# SCENE 5 — READING THE LOG
# entries(): every audit entry with a given event name.
# ===========================================================================

def entries(sv: Supervisor, event: str):
    """
    Return the audit entries whose event is `event`, in log order.

    Enter:   sv      the Supervisor whose audit trail to read
             event   an event name such as "ESCALATION" or "GATE_OVERRIDE"
    Exit:    a list of AuditEntry objects (possibly empty)
    """
    return [e for e in sv.audit.entries() if e.event == event]


# ===========================================================================
# SCENE 6 — THE PATH A SIGNAL TOOK
# transitions(): the (from, to) pairs of one signal's logged transitions.
# ===========================================================================

def transitions(sv: Supervisor, signal_id: str):
    """
    Return the (from, to) state pairs logged for one signal, in order.

    Enter:   sv, signal_id   which supervisor and signal
    Exit:    a list of (str, str) tuples, e.g. [("unregistered", "registered"), ...]
             (states appear as plain strings because the audit trail stores
             enums by value)
    """
    return [(e.payload["from"], e.payload["to"]) for e in entries(sv, "TRANSITION")
            if e.payload.get("signal") == signal_id]

# EXEUNT — end of file.

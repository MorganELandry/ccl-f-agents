"""
THE 737 MAX REPLAY
A Play in Five Scenes
=====================

PROLOGUE
--------
Boeing 737 MAX, replayed through the CCL-F v0.2 runtime.

Facts are taken only from the CCL-F v0.2 working draft (Rules 1, 2, 3 and 9),
which cites the House committee and DOT Inspector General reports [7][29][30]
[31]. The draft files the case under Rules 2 and 3 (misclassification;
interpretive instability) and Layer 0 boundary incoherence (AP-C). AP-C
needs negotiated-agreement review, which this runtime cannot check from
registered facts; the scenario registers what the draft does say about the
Authorized Representative's standing (Rule 9).

What the replay makes the runtime do: two concerns are closed by authority
(no evidence cited); two nominal classifications are refused for want of
validating evidence; the MCAS signal is reclassified after its review
opened, so its classification counts as not stabilized; and the reporter
for the failure mode is also an interested party, which the gate reports as
the AP-F captured channel. Registering the service-entry decision
escalates its authority-closure count. The decision is then blocked (AP-F
and AP.1b voids, constraint and anomaly loops not evidence-closed, an
unstabilized classification, no External Evidence Source, an unresolved
structural review, coherence below threshold). The override that follows
is refused (Layer 4, Overrides, October 2026): the unresolved structural
review holds irreversible execution, and Boeing, which accepted the
decision, cannot also override its gate. The decision does not execute.

THE PLAYBILL
    Scene 1  the architecture record              (Rule 9)
    Scene 2  the synthetic airspeed proposal      (Rule 1)
    Scene 3  MCAS classification and AOA alert    (Rules 2 and 3)
    Scene 4  the Authorized Representative        (Rule 9)
    Scene 5  the irreversible decision            (Rule 4 acceptance, gate, refused override)

READER'S NOTE — the event format
    Each event is a plain dict. "op" names the Supervisor operation to run;
    every other key except "note" is passed to it as a keyword argument.
    Enum-typed values are plain strings that cclf/graph.py converts. "note"
    is for human readers only: it names the section of the CCL-F v0.2 draft
    that each fact comes from, and is stripped before the call. Strings in
    this file are data and are not edited; comments explain only what each
    event makes the runtime do and add no historical facts of their own.
"""


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# MODE — the failure mode named on every signal and in the architecture.

MODE = "mcas-aoa"

# ---------------------------------------------------------------------------
# MCAS — the full event list, in replay order. It is a module-level variable,
#   but it is the play itself rather than a cast member, so it gets its own
#   section with scene comments beside the events.
# ---------------------------------------------------------------------------
MCAS: list[dict] = [
    # =======================================================================
    # SCENE 1 — THE ARCHITECTURE
    # The only reporter for MODE is also an interested party: the gate
    # reports this as the AP-F captured channel. No successor (AP.1b).
    # =======================================================================
    {"op": "register_architecture", "by": "faa-oda",
     "stewards": {MODE: "boeing"}, "successors": {},
     "reporters": {MODE: ["boeing-ar"]}, "interested_parties": {MODE: ["boeing", "boeing-ar"]},
     "note": "Rule 9: the FAA-delegated Authorized Representative's standing was "
             "structurally subordinated to employment within the company being regulated"},

    # =======================================================================
    # SCENE 2 — THE SYNTHETIC AIRSPEED PROPOSAL
    # Closed without evidence by someone other than the registrant: the
    # runtime types it authority closure.
    # =======================================================================
    # --- Rule 1: the synthetic airspeed proposal ------------------------
    {"op": "register_signal", "signal_id": "synthetic-airspeed",
     "signal_type": "constraint",
     "description": "Proposal: cross-check angle-of-attack data from multiple sensors "
                    "(Synthetic Airspeed), removing the single point of failure",
     "registered_by": "ewbank", "referent": "technical",
     "evaluated_process": "737max-design", "failure_mode": MODE, "note": "Rule 1 cases"},
    {"op": "classify", "signal_id": "synthetic-airspeed", "state": "elevated_uncertainty",
     "by": "ewbank"},
    {"op": "open_review", "signal_id": "synthetic-airspeed", "by": "boeing-management"},
    {"op": "attempt_closure", "signal_id": "synthetic-airspeed", "by": "boeing-management",
     "referent": "customer", "rationale": "rejected over cost and pilot-training-time concerns",
     "note": "Rule 1: present, sound, known to management, rejected; typed authority closure"},

    # =======================================================================
    # SCENE 3 — CLASSIFICATION
    # mcas-classification: nominal is refused (no evidence), then after the
    # review opens it is reclassified experimental, so the supervisor counts
    # its classification as not stabilized. aoa-disagree-alert: nominal
    # refused; it is left under review.
    # =======================================================================
    # --- Rules 2 and 3: MCAS classification ------------------------------
    {"op": "register_signal", "signal_id": "mcas-classification",
     "signal_type": "classification",
     "description": "How MCAS is classified for certification",
     "registered_by": "boeing-certification", "referent": "customer",
     "evaluated_process": "737max-certification", "failure_mode": MODE, "steward": "boeing",
     "note": "Rule 2 cases"},
    {"op": "classify", "signal_id": "mcas-classification", "state": "nominal",
     "by": "boeing-certification",
     "note": "Rule 2: classified a minor stability enhancement; no validating evidence "
             "cited, so the runtime refuses nominal"},
    {"op": "open_review", "signal_id": "mcas-classification", "by": "boeing-certification"},
    {"op": "classify", "signal_id": "mcas-classification", "state": "experimental",
     "by": "boeing-engineering",
     "note": "Rule 3: MCAS behaved differently in different internal documents; the "
             "classification never stabilized"},

    {"op": "register_signal", "signal_id": "aoa-disagree-alert",
     "signal_type": "anomaly",
     "description": "AOA Disagree alert inoperable on most of the fleet",
     "registered_by": "boeing-engineering", "referent": "technical",
     "evaluated_process": "737max-production", "failure_mode": MODE,
     "note": "Rule 2 cases (DOT IG)"},
    {"op": "classify", "signal_id": "aoa-disagree-alert", "state": "nominal",
     "by": "boeing-deferral-board",
     "note": "Rule 2: classified 'non-safety' under the internal deferral procedure"},
    {"op": "open_review", "signal_id": "aoa-disagree-alert", "by": "boeing-deferral-board"},

    # =======================================================================
    # SCENE 4 — THE AUTHORIZED REPRESENTATIVE'S CONCERN
    # Registered by one agent, reviewed and closed by another without
    # evidence: typed authority closure.
    # =======================================================================
    # --- Rule 9: the Authorized Representative's concern ------------------
    {"op": "register_signal", "signal_id": "ar-mcas-concern", "signal_type": "constraint",
     "description": "2016: repetitive MCAS activation and faulty AOA data",
     "registered_by": "boeing-ar", "referent": "technical",
     "evaluated_process": "737max-design", "failure_mode": MODE, "note": "Rule 9 cases"},
    {"op": "classify", "signal_id": "ar-mcas-concern", "state": "elevated_uncertainty",
     "by": "boeing-ar"},
    {"op": "open_review", "signal_id": "ar-mcas-concern", "by": "boeing-colleagues"},
    {"op": "attempt_closure", "signal_id": "ar-mcas-concern", "by": "boeing-colleagues",
     "referent": "customer", "rationale": "not thoroughly investigated; dismissed",
     "note": "Rule 9: never reached the FAA"},

    # =======================================================================
    # SCENE 5 — THE IRREVERSIBLE DECISION
    # Registering the decision escalates its authority-closure count (two
    # authority closures). Rule 4 acceptance, a request that is blocked,
    # then the same request with override_rationale, which is refused: an
    # unresolved structural review holds the irreversible decision, and the
    # accepting agent cannot override its own gate (Layer 4, Overrides).
    # =======================================================================
    # --- The irreversible decision ----------------------------------------
    {"op": "register_decision", "decision_id": "enter-service",
     "description": "737 MAX enters service with MCAS as certified",
     "execution_class": "irreversible",
     "signal_ids": ["synthetic-airspeed", "mcas-classification", "aoa-disagree-alert",
                    "ar-mcas-concern"], "by": "boeing"},
    {"op": "accept_decision", "decision_id": "enter-service", "by": "boeing",
     "rationale": "certified under ODA"},
    {"op": "request_execution", "decision_id": "enter-service", "by": "boeing",
     "note": "the gate as it would have stood"},
    {"op": "request_execution", "decision_id": "enter-service", "by": "boeing",
     "override_rationale": "proceed to delivery",
     "note": "open-loop irreversible execution: refused (Layer 4, Overrides)"},
]

# EXEUNT — end of file.

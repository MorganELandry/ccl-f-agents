"""
Boeing 737 MAX, replayed through the CCL-F v0.2 runtime.

Facts are taken only from the CCL-F v0.2 working draft (Rules 1, 2, 3 and 9),
which cites the House committee and DOT Inspector General reports [7][29][30]
[31]. The draft files the case under Rules 2 and 3 (misclassification;
interpretive instability) and Layer 0 boundary incoherence (AP-C). AP-C
needs negotiated-agreement review, which this runtime cannot check from
registered facts; the scenario registers what the draft does say about the
Authorized Representative's standing (Rule 9).
"""

MODE = "mcas-aoa"

MCAS: list[dict] = [
    {"op": "register_architecture", "by": "faa-oda",
     "stewards": {MODE: "boeing"}, "successors": {},
     "reporters": {MODE: ["boeing-ar"]}, "interested_parties": {MODE: ["boeing", "boeing-ar"]},
     "note": "Rule 9: the FAA-delegated Authorized Representative's standing was "
             "structurally subordinated to employment within the company being regulated"},

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

    # --- Rules 2 and 3: MCAS classification ------------------------------
    {"op": "register_signal", "signal_id": "mcas-classification",
     "signal_type": "classification",
     "description": "How MCAS is classified for certification",
     "registered_by": "boeing-certification", "referent": "customer",
     "evaluated_process": "737max-certification", "failure_mode": MODE, "steward": "boeing", "note": "Rule 2 cases"},
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
     "evaluated_process": "737max-production", "failure_mode": MODE, "note": "Rule 2 cases (DOT IG)"},
    {"op": "classify", "signal_id": "aoa-disagree-alert", "state": "nominal",
     "by": "boeing-deferral-board",
     "note": "Rule 2: classified 'non-safety' under the internal deferral procedure"},
    {"op": "open_review", "signal_id": "aoa-disagree-alert", "by": "boeing-deferral-board"},

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
     "note": "open-loop irreversible execution, permanently logged"},
]

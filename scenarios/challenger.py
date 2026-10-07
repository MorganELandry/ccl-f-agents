"""
Challenger (1986), replayed through the CCL-F v0.2 runtime.

Every fact below is taken from the CCL-F v0.2 working draft, which cites the
Rogers Commission report and Vaughan [5][6]; the `note` on each event names
the section. Nothing is added beyond the draft's own account. The draft's
0.2 Exit Checklist flags its named-actor Challenger sourcing for a cold read
against the primary Rogers Commission volumes; until that read is done,
treat actor attributions here as the draft's, not independently verified.

What the replay shows: the runtime refuses the later launch-constraint
waivers once the recurrence threshold is crossed (Rule 7), rejects a
nominal classification of an off-envelope condition (Rule 2), types the
Lund reversal as role-switch closure, records the framing signal's
suppression of the open uncertainty, and blocks the irreversible launch
decision. The launch then proceeds only through a logged override, which
latches the open constraint loops into trajectory lock with a lock-in
closure record.
"""

GROUP = "srb-joint-erosion"
MODE = "srb-joint-seal"

CHALLENGER: list[dict] = [
    {"op": "register_architecture", "by": "nasa-srb-project",
     "stewards": {}, "successors": {},
     "note": "Failure Taxonomy: stewardship void under off-envelope conditions; "
             "Rule 9: off-envelope authorization never distributed to engineering"},

    # --- Rule 7: the erosion recurrence group and the waiver chain ---------
    {"op": "add_evidence", "evidence_id": "e-51b-secondary-erosion",
     "content": "STS 51-B booster disassembled June 25, 1985: first-ever secondary "
                "O-ring erosion.",
     "source": "post-flight disassembly", "kind": "direct_measurement",
     "produced_by": "booster-disassembly", "by": "thiokol-engineering",
     "note": "Rule 7 cases"},
    {"op": "register_signal", "signal_id": "launch-constraint-51F",
     "signal_type": "constraint",
     "description": "Marshall launch constraint on 51-F and all subsequent launches "
                    "after secondary O-ring erosion",
     "registered_by": "marshall", "referent": "technical",
     "evaluated_process": "srb-program", "recurrence_group": GROUP, "failure_mode": MODE,
     "evidence_ids": ["e-51b-secondary-erosion"], "note": "Rule 7 cases"},
    {"op": "classify", "signal_id": "launch-constraint-51F", "state": "nominal",
     "by": "mulloy", "note": "illustrates Rule 2: nominal without validating evidence "
                             "is refused (recorded as elevated uncertainty)"},
    {"op": "open_review", "signal_id": "launch-constraint-51F", "by": "mulloy"},
    {"op": "attempt_closure", "signal_id": "launch-constraint-51F", "by": "mulloy",
     "referent": "customer", "rationale": "Flight Readiness Review waiver (51-F)",
     "note": "Rule 7: waived at each FRR without the condition being resolved"},
] + [
    step
    for n in range(2, 7)
    for step in (
        {"op": "register_signal", "signal_id": f"constraint-frr-{n}",
         "signal_type": "constraint",
         "description": f"launch constraint in effect at FRR {n} of 6 "
                        f"({'51-L, Challenger itself' if n == 6 else 'unresolved'})",
         "registered_by": "marshall", "referent": "technical",
         "evaluated_process": "srb-program", "recurrence_group": GROUP, "failure_mode": MODE,
         "note": "Rule 7: the same constraint, recurring at each FRR"},
        {"op": "classify", "signal_id": f"constraint-frr-{n}", "state": "nominal",
         "by": "mulloy"},
        {"op": "open_review", "signal_id": f"constraint-frr-{n}", "by": "mulloy"},
        {"op": "attempt_closure", "signal_id": f"constraint-frr-{n}", "by": "mulloy",
         "referent": "customer", "rationale": f"FRR waiver {n} of 6",
         "note": "refused from the third occurrence on: the group is escalated and "
                 "an escalated signal cannot be closed until structural review "
                 "documents a model update (Rules 7-8)"},
    )
] + [
    # --- The night of January 27, 1986 -----------------------------------
    {"op": "add_evidence", "evidence_id": "e-temperature-vs-test-data",
     "content": "Forecast O-ring temperature below anything in the validated test data.",
     "source": "Thiokol engineering data", "kind": "primary_document",
     "produced_by": "thiokol-engineering-test-data", "by": "boisjoly",
     "note": "Rule 2 cases"},
    {"op": "register_signal", "signal_id": "cold-oring-no-launch",
     "signal_type": "constraint",
     "description": "Engineering no-launch recommendation: O-ring performance "
                    "unvalidated at forecast temperature",
     "registered_by": "lund", "referent": "technical",
     "evaluated_process": "srb-program", "steward": "lund", "failure_mode": MODE,
     "evidence_ids": ["e-temperature-vs-test-data"],
     "note": "Closure Quality: Lund signed the original no-launch recommendation"},
    {"op": "classify", "signal_id": "cold-oring-no-launch", "state": "off_envelope",
     "by": "boisjoly", "evidence_ids": ["e-temperature-vs-test-data"],
     "note": "Key Definitions: off-envelope = outside validated test data"},
    {"op": "open_review", "signal_id": "cold-oring-no-launch", "by": "thiokol-engineering"},

    {"op": "register_signal", "signal_id": "seal-uncertainty",
     "signal_type": "uncertainty",
     "description": "No one had validated O-ring performance at the forecast temperature",
     "registered_by": "thiokol-engineering", "referent": "technical",
     "evaluated_process": "srb-program", "failure_mode": MODE, "note": "Rule 3 cases"},
    {"op": "classify", "signal_id": "seal-uncertainty", "state": "elevated_uncertainty",
     "by": "thiokol-engineering"},
    {"op": "open_review", "signal_id": "seal-uncertainty", "by": "thiokol-engineering"},

    {"op": "register_signal", "signal_id": "burden-of-proof-frame",
     "signal_type": "framing",
     "description": "'Prove it's unsafe' replaces 'prove it's safe'",
     "registered_by": "nasa-srb-project", "referent": "customer",
     "evaluated_process": "launch-decision", "note": "Rule 1: framing signals"},
    {"op": "classify", "signal_id": "burden-of-proof-frame", "state": "elevated_uncertainty",
     "by": "nasa-srb-project"},
    {"op": "open_review", "signal_id": "burden-of-proof-frame", "by": "nasa-srb-project"},
    {"op": "adopt_frame", "framing_signal_id": "burden-of-proof-frame",
     "by": "nasa-srb-project", "displaces": ["seal-uncertainty"],
     "rationale": "burden of proof inverted",
     "note": "Key Definitions, Framing Signal: authority closure of the frame plus a "
             "suppression event on the signal it displaced"},

    {"op": "attempt_closure", "signal_id": "cold-oring-no-launch", "by": "lund",
     "referent": "customer",
     "rationale": "reconsidered 'from a management perspective' at Mason's instruction",
     "note": "Closure Quality: canonical role-switch closure. The runtime refuses it: "
             "the off-envelope classification had already escalated this signal to "
             "structural review. (tests/ show the same reversal typed as role-switch "
             "closure when no escalation is pending.)"},

    {"op": "register_decision", "decision_id": "launch-51L",
     "description": "Launch STS-51-L (Challenger)", "execution_class": "irreversible",
     "signal_ids": ["launch-constraint-51F"] + [f"constraint-frr-{n}" for n in range(2, 7)]
                   + ["cold-oring-no-launch", "seal-uncertainty", "burden-of-proof-frame"],
     "by": "nasa"},
    {"op": "accept_decision", "decision_id": "launch-51L", "by": "kilminster",
     "rationale": "reversed recommendation written out and delivered to NASA",
     "note": "Revision Rigidity and Trajectory Lock: Kilminster's authorization act"},
    {"op": "request_execution", "decision_id": "launch-51L", "by": "kilminster",
     "note": "the gate as it would have stood"},
    {"op": "request_execution", "decision_id": "launch-51L", "by": "kilminster",
     "override_rationale": "management decision to recommend launch",
     "note": "Lock-in Closure: accumulated rigidity converted into a binding record"},
]

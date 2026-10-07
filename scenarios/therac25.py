"""
Therac-25 (1985-1987), replayed through the CCL-F v0.2 runtime.

Facts are taken only from the CCL-F v0.2 working draft (AP.6, Rule 3, Rule 7,
Failure Taxonomy), which cites Leveson & Turner (1993) and FDA/GAO sources
[11][24][25]. The draft classifies the case as Rule 7 + Rule 1 (recurrence
never linked; authority closure without evidence) and AP.6 (captured
reporting channel). It does not say AECL concealed an internal analysis;
neither does this scenario. Incidents are numbered rather than placed,
because the draft names the hospitals involved (Kennestone, Yakima, East
Texas Cancer Center) without mapping every incident to a site.
"""

GROUP = "therac25-overdose"
MODE = GROUP

_AECL_ASSERTION = ("Damage 'could not have been produced by any malfunction of the "
                   "Therac-25 or by any operator error.'")

THERAC25: list[dict] = [
    {"op": "register_architecture", "by": "fda-mdr-regime",
     "stewards": {MODE: "aecl"}, "successors": {},
     "reporters": {MODE: ["aecl"]}, "interested_parties": {MODE: ["aecl"]},
     "note": "AP.6: under 21 CFR 803 (1984-1990) only the manufacturer was obligated to "
             "report; treating hospitals and physicists had no federal channel"},
]

for n in range(1, 7):
    THERAC25 += [
        {"op": "register_signal", "signal_id": f"overdose-{n}", "signal_type": "anomaly",
         "description": f"Massive radiation overdose, incident {n} of 6, reported to AECL "
                       "by the treating hospital",
         "registered_by": "treating-hospital", "referent": "technical",
         "evaluated_process": "therac25-software", "recurrence_group": GROUP,
         "failure_mode": MODE,
         "note": "Rule 7: six overdoses before the incidents were connected"},
        {"op": "add_evidence", "evidence_id": f"e-aecl-letter-{n}", "content": _AECL_ASSERTION,
         "source": "AECL letter to the hospital", "kind": "assertion",
         "produced_by": "aecl", "by": "aecl", "signal_ids": [f"overdose-{n}"],
         "note": "AP.6: written to Kennestone, Yakima and East Texas Cancer Center"},
        {"op": "classify", "signal_id": f"overdose-{n}", "state": "nominal", "by": "aecl",
         "evidence_ids": [f"e-aecl-letter-{n}"],
         "note": "Rule 3: an assertion is not validating evidence, so the runtime "
                 "refuses nominal and records elevated uncertainty"},
        {"op": "open_review", "signal_id": f"overdose-{n}", "by": "aecl"},
        {"op": "attempt_closure", "signal_id": f"overdose-{n}", "by": "aecl",
         "referent": "technical", "evidence_ids": [f"e-aecl-letter-{n}"],
         "rationale": "no malfunction found",
         "note": "Rule 3: assertion substituted for stabilization; typed authority "
                 "closure. From the third incident the recurrence group is escalated "
                 "and the closure is refused (Rule 7)."},
    ]

THERAC25 += [
    {"op": "add_evidence", "evidence_id": "e-tyler-reproduction",
     "content": "Hospital physicist at Tyler independently reproduced the software error.",
     "source": "East Texas Cancer Center physicist", "kind": "direct_measurement",
     "produced_by": "etcc-physicist", "by": "etcc-physicist",
     "signal_ids": [f"overdose-{n}" for n in range(1, 7)],
     "note": "Rule 3 cases: the reproduction that ended the assertions"},
    {"op": "reopen", "signal_id": "overdose-1", "by": "etcc-physicist",
     "rationale": "independent reproduction of the software error",
     "note": "Layer 4: a reopen is logged with rationale, reopening agent and the "
             "closure record it supersedes"},
    {"op": "reopen", "signal_id": "overdose-2", "by": "etcc-physicist",
     "rationale": "independent reproduction of the software error"},
    {"op": "add_evidence", "evidence_id": "e-texas-health-notice",
     "content": "First notification to reach the FDA about the fatal Tyler incidents "
                "came from the Texas Health Department.",
     "source": "Texas Health Department", "kind": "independent_party",
     "produced_by": "texas-health-department", "by": "texas-health-department",
     "note": "AP.6: an accidental third-party route, not a designed one"},
    {"op": "register_decision", "decision_id": "continue-treatment",
     "description": "Continue clinical treatment on the Therac-25",
     "execution_class": "irreversible",
     "signal_ids": [f"overdose-{n}" for n in range(1, 7)], "by": "aecl"},
    {"op": "accept_decision", "decision_id": "continue-treatment", "by": "aecl",
     "rationale": "no malfunction found",
     "note": "Rule 4 acceptance by the manufacturer"},
    {"op": "request_execution", "decision_id": "continue-treatment", "by": "aecl",
     "note": "blocked: captured channel (AP-F), open loops, unreviewed recurrence"},
]

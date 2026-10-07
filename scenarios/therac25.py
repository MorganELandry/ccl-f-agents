"""
THE THERAC-25 REPLAY
A Play in Three Scenes
======================

PROLOGUE
--------
Therac-25 (1985-1987), replayed through the CCL-F v0.2 runtime.

Facts are taken only from the CCL-F v0.2 working draft (AP.6, Rule 3, Rule 7,
Failure Taxonomy), which cites Leveson & Turner (1993) and FDA/GAO sources
[11][24][25]. The draft classifies the case as Rule 7 + Rule 1 (recurrence
never linked; authority closure without evidence) and AP.6 (captured
reporting channel). It does not say AECL concealed an internal analysis;
neither does this scenario. Incidents are numbered rather than placed,
because the draft names the hospitals involved (Kennestone, Yakima, East
Texas Cancer Center) without mapping every incident to a site.

What the replay makes the runtime do: each manufacturer letter is recorded
as an "assertion", which is not EES-eligible evidence, so every nominal
classification is refused (recorded as elevated uncertainty) and the first
two closures are typed authority closure. The third overdose crosses the
recurrence threshold, so later closures are refused. The independent
reproduction is recorded as direct measurement, and the first two closed
signals are reopened (and, because the recurrence escalation names them,
go straight to escalated). The decision to continue treatment is then
blocked: every reporter is an interested party (AP-F captured channel),
the recurrence group is unreviewed, and coherence is below threshold.

THE PLAYBILL
    Scene 1  the architecture record           (AP.6: who could report)
    Scene 2  six overdoses                     (built by the `for` loop below)
    Scene 3  reproduction, reopen, decision    (Rule 3, Layer 4 reopen, gate)

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

# GROUP — the recurrence group shared by all six overdose signals.

GROUP = "therac25-overdose"

# MODE — the failure mode name; the same string as GROUP. The architecture
#   uses it to name the steward, the reporters and the interested parties.
MODE = GROUP

# _AECL_ASSERTION — the content of every manufacturer letter in Scene 2,
#   quoted as the draft gives it. Two adjacent string literals inside
#   parentheses are joined into one string by Python.
_AECL_ASSERTION = ("Damage 'could not have been produced by any malfunction of the "
                   "Therac-25 or by any operator error.'")

# ---------------------------------------------------------------------------
# THERAC25 — the full event list, in replay order.
#   Its first part is declared here with the other module-level variables,
#   but the `for` loop and the `+=` below keep adding to it, so those
#   statements stay where they are: they must run after this one, in order.
#   (A loop cannot be moved into a declaration block without changing code.)
# ---------------------------------------------------------------------------

# ===========================================================================
# SCENE 1 — THE ARCHITECTURE
# The manufacturer is steward, the only reporter, and an interested party.
# Every reporter being an interested party is what the gate later reports
# as the AP-F captured channel. No successor is registered (AP.1b).
# ===========================================================================
THERAC25: list[dict] = [
    {"op": "register_architecture", "by": "fda-mdr-regime",
     "stewards": {MODE: "aecl"}, "successors": {},
     "reporters": {MODE: ["aecl"]}, "interested_parties": {MODE: ["aecl"]},
     "note": "AP.6: under 21 CFR 803 (1984-1990) only the manufacturer was obligated to "
             "report; treating hospitals and physicists had no federal channel"},
]

# ===========================================================================
# SCENE 2 — SIX OVERDOSES
# For each incident n = 1..6, five events: register the overdose, record the
# letter as an "assertion" linked to it, classify nominal citing the letter
# (refused: an assertion is not EES-eligible), open review, attempt closure.
# `+=` on a list appends all items of the right-hand list (it extends it).
# The third signal in GROUP crosses the recurrence threshold; from then on
# each review opens straight into escalated and its closure is refused.
# ===========================================================================
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

# ===========================================================================
# SCENE 3 — THE REPRODUCTION, THE REOPENS, AND THE DECISION
# The reproduction is recorded as direct measurement by a party other than
# the manufacturer. Reopening needs a rationale and is logged against the
# closure it supersedes; the reopened signals are escalated at once because
# the open recurrence review names them. Only the two signals that were
# actually closed (1 and 2) can be reopened; 3-6 were never closed.
# The final request has no override_rationale, so it simply ends blocked.
# ===========================================================================
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

# EXEUNT — end of file.

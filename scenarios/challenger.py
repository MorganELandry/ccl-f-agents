"""
THE CHALLENGER REPLAY
A Play in Four Scenes
=====================

PROLOGUE
--------
Challenger (1986), replayed through the CCL-F v0.2 runtime.

Every fact below is taken from the CCL-F v0.2 working draft, which cites the
Rogers Commission report and Vaughan [5][6]; the `note` on each event names
the section. Nothing is added beyond the draft's own account. The draft's
0.2 Exit Checklist flags its named-actor Challenger sourcing for a cold read
against the primary Rogers Commission volumes; until that read is done,
treat actor attributions here as the draft's, not independently verified.

What the replay shows: the runtime refuses the later launch-constraint
waivers once the recurrence threshold is crossed (Rule 7), rejects every
nominal classification made without validating evidence (Rule 2), refuses the
Lund reversal because the off-envelope classification has already escalated
that signal (the same reversal is typed as role-switch closure in
tests/test_closure.py when no escalation is pending), records the framing
signal's suppression of the open uncertainty, escalates the decision's three
authority closures when the decision is registered and the suppressed signal
when execution is requested, and blocks the irreversible launch decision.
The launch then proceeds only through a logged override. The override
records open-loop irreversible execution and escalates lock-in with open
constraint loops. None is latched into trajectory lock (v0.2 defines
that transition only from under_review): the open constraints are by then
escalated, and the rest were closed by authority, which the irreversible
gate does not accept as resolution, so all of them are listed still open.

THE PLAYBILL
    Scene 1  the architecture record             (Layer 0)
    Scene 2  the erosion recurrence group        (Rule 7: first constraint, then FRRs 2-6)
    Scene 3  the night before launch             (Rule 2, Rule 3, Rule 1 framing,
                                                  Closure Quality)
    Scene 4  the irreversible decision           (Rule 4 acceptance, gate, override)

READER'S NOTE — the event format
    Each event is a plain dict. "op" names the Supervisor operation to run
    (register_signal, classify, open_review, attempt_closure, ...); every
    other key except "note" is passed to that method as a keyword argument,
    so the keys match the method's parameter names. Enum-typed values are
    written as plain strings ("constraint", "nominal", "irreversible") and
    cclf/graph.py converts them. "note" is for human readers only: it names
    the section of the CCL-F v0.2 draft that each fact comes from, and the
    demo prints it next to the op. It is stripped before the call.
    Agent names such as "mulloy" or "kilminster" are the "by" identities
    recorded in the audit trail; every operation needs one.

READER'S NOTE — what this file is, and is not
    The strings in this file are data: descriptions and notes reproduce the
    draft's account and are not to be edited as part of commenting. The
    comments added around them explain only what each event makes the
    runtime do; they add no historical facts of their own.
"""


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# GROUP — the recurrence group shared by every launch-constraint signal in
#   Scene 2. The supervisor counts signals per group; at the third member
#   (DEFAULT_RECURRENCE_THRESHOLD in supervisor.py) the group escalates.

GROUP = "srb-joint-erosion"

# MODE — the failure mode named on the signals. The architecture registered
#   in Scene 1 has no steward or successor for it, which the gate reports
#   as Layer 0 voids (AP-A, AP.1b).
MODE = "srb-joint-seal"

# ---------------------------------------------------------------------------
# CHALLENGER — the full event list, in replay order.
#   This module-level variable is not in the cast list above: it is the play
#   itself, built by joining three lists with `+`, the middle one produced by
#   a list comprehension over FRRs 2-6. It is kept here as its own section so
#   its scene comments sit next to the events they describe.
# ---------------------------------------------------------------------------

CHALLENGER: list[dict] = [
    # =======================================================================
    # SCENE 1 — THE ARCHITECTURE
    # Empty stewards and successors: nobody is registered as steward or
    # successor for MODE, so the execution gate later reports Layer 0 voids.
    # =======================================================================
    {"op": "register_architecture", "by": "nasa-srb-project",
     "stewards": {}, "successors": {},
     "note": "Failure Taxonomy: stewardship void under off-envelope conditions; "
             "Rule 9: off-envelope authorization never distributed to engineering"},

    # =======================================================================
    # SCENE 2 — THE RECURRENCE GROUP
    # The first constraint in GROUP: evidence recorded at registration, a
    # nominal classification the runtime refuses (no novel, independent
    # evidence is cited), a review, and a closure the runtime types as
    # authority closure (no evidence cited, closer not the registrant).
    # =======================================================================
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
    # --- The same four steps for each of FRRs 2-6 ---------------------------
    # A nested list comprehension: for each n in 2..6, take each of the four
    # dicts in the inner tuple, giving one flat list of 20 events. f-strings
    # put n into the ids. The third signal in GROUP (n == 3) crosses the
    # recurrence threshold: from then on each new signal is escalated as soon
    # as its review opens, and its attempt_closure is refused.
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
    # =======================================================================
    # SCENE 3 — THE NIGHT BEFORE LAUNCH
    # Three new signals: the no-launch constraint (classified off_envelope,
    # which escalates it at once), the seal uncertainty, and the framing
    # signal whose adoption suppresses the uncertainty. (Only an
    # uncertainty signal is displaced, so the "frame adopted over open
    # constraints" escalation does not fire.) Lund's closure of the
    # constraint is then refused because it is already escalated.
    # =======================================================================
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

    # =======================================================================
    # SCENE 4 — THE IRREVERSIBLE DECISION
    # The launch decision names every signal above. Registering it escalates
    # the authority-closure count (three authority closures: 51-F, FRR 2 and
    # the frame). Rule 4 acceptance, then an execution request (blocked; it
    # also escalates the suppressed seal-uncertainty signal), then the same
    # request with an override_rationale (permitted, permanently logged; it
    # escalates lock-in with open constraint loops and locks nothing, since
    # no constraint is still under_review).
    # =======================================================================
    # The signal list is built with + and a list comprehension (FRRs 2-6).
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
     "note": "the override over open constraint loops (spec: Lock-in Closure)"},
]

# EXEUNT — end of file.

"""
THE FLIGHT 1549 REPLAY
A Play in Four Scenes
======================

PROLOGUE
--------
US Airways Flight 1549 (2009), replayed through the CCL-F v0.2 runtime as
an Emergency Justification given on scene, by the agent who accepted the
decision.

Facts are taken only from the CCL-F v0.2 working draft (Layer 4, Execution
Gates, Overrides, "Emergency Justification"), which cites [56]: "after bird
ingestion caused an almost total loss of thrust in both engines at low
altitude, the engine-restart procedure called for an airspeed the aircraft
could not reach ('airspeed optimum relight. three hundred knots. we don't
have that'), the crew considered and rejected a return to LaGuardia and a
diversion to Teterboro as unreachable, and the captain ditched in the
Hudson River — a landing no certification or checklist covered — about
three and a half minutes after the bird strike"; "Flight 1549 had minutes
and no time to consult one, which is the case the on-scene proviso in
element 5 exists for." The agents are roles; the evidence ids name the
kinds of record the draft describes.

What the replay makes the runtime do: the ditching is classified
off-envelope, which opens a review that holds the irreversible decision.
The captain accepts the decision (Rule 4), registers the condition
Experimental with the instrument readings as best evidence, and gives the
justification on scene: element 5's proviso lets the acceptor act alone,
with the cockpit voice recorder as the contemporaneous record. The
decision executes, the review is suspended, the loop is latched with the
captain as steward, and the post-event review opens. An independent board
then resolves the post-event review with a finding on every element,
including the time estimate.

THE PLAYBILL
    Scene 1  the architecture record             (Layer 0, AP.1)
    Scene 2  the ditching condition              (off-envelope, Rule 2)
    Scene 3  acceptance, registered experimental (Rule 4; element 4)
    Scene 4  the justification on scene; the post-event review

READER'S NOTE — the event format
    As in scenarios/challenger.py; cclf/graph.py turns the "emergency"
    object into an EmergencyJustification.
"""


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# MODE — the failure mode named on the signal and in the architecture.
MODE = "dual-engine-thrust-loss"

# ---------------------------------------------------------------------------
# USAIR1549 — the full event list, in replay order. It is the play itself
#   rather than a cast member, so it gets its own section with scene
#   comments beside the events.
# ---------------------------------------------------------------------------
USAIR1549: list[dict] = [
    # =======================================================================
    # SCENE 1 — THE ARCHITECTURE
    # The flight crew is registered steward, the first officer successor.
    # =======================================================================
    {"op": "register_architecture", "by": "airline",
     "stewards": {MODE: "captain"}, "successors": {MODE: "first-officer"},
     "note": "Layer 0, AP.1: stewardship registered before the flight"},

    # =======================================================================
    # SCENE 2 — THE DITCHING CONDITION
    # Off-envelope: no certification or checklist covered it.
    # =======================================================================
    {"op": "register_signal", "signal_id": "hudson-ditching", "signal_type": "constraint",
     "description": "Ditching in the Hudson River: a landing no certification or "
                    "checklist covered",
     "registered_by": "first-officer", "referent": "technical",
     "evaluated_process": "a320-certification-basis", "steward": "captain",
     "successor": "first-officer", "failure_mode": MODE,
     "note": "Layer 4, Overrides, Emergency Justification: US Airways 1549 [56]"},
    {"op": "classify", "signal_id": "hudson-ditching", "state": "off_envelope",
     "by": "first-officer", "note": "no certification or checklist covered it"},
    {"op": "open_review", "signal_id": "hudson-ditching", "by": "first-officer"},
    {"op": "register_decision", "decision_id": "ditch-in-hudson",
     "description": "Ditch in the Hudson River", "execution_class": "irreversible",
     "signal_ids": ["hudson-ditching"], "by": "captain"},

    # =======================================================================
    # SCENE 3 — ACCEPTANCE, REGISTERED EXPERIMENTAL
    # The captain accepts; the condition is registered experimental on the
    # instrument readings.
    # =======================================================================
    {"op": "accept_decision", "decision_id": "ditch-in-hudson", "by": "captain",
     "rationale": "both engines lost; no runway reachable",
     "note": "Rule 4: a single accepting agent"},
    {"op": "add_evidence", "evidence_id": "thrust-and-airspeed",
     "content": "Almost total loss of thrust in both engines at low altitude; airspeed "
                "below the relight requirement",
     "source": "cockpit instruments", "kind": "direct_measurement",
     "produced_by": "aircraft-instruments", "by": "first-officer",
     "note": "Emergency Justification, element 4: best evidence available [56]"},
    {"op": "add_evidence", "evidence_id": "cockpit-voice-recorder",
     "content": "airspeed optimum relight. three hundred knots. we don't have that",
     "source": "cockpit voice recorder", "kind": "primary_document",
     "produced_by": "cockpit-voice-recorder", "by": "first-officer",
     "note": "element 5: the contemporaneous record stands in for the separate "
             "authorization"},
    {"op": "classify", "signal_id": "hudson-ditching", "state": "experimental",
     "by": "first-officer", "evidence_ids": ["thrust-and-airspeed"],
     "note": "element 4: registered, not reclassified"},

    # =======================================================================
    # SCENE 4 — THE JUSTIFICATION ON SCENE; THE POST-EVENT REVIEW
    # The captain, who accepted the decision, gives it alone (on_scene).
    # The post-event review (opened by the justification) is then resolved
    # by an independent board; its id is looked up by the test, not here.
    # =======================================================================
    {"op": "request_execution", "decision_id": "ditch-in-hudson", "by": "captain",
     "emergency": {
         "consequence": "life_safety_catastrophic",
         "time_estimate": "about three and a half minutes from the bird strike: harm "
                          "before any second agent could be consulted",
         "options_considered": [
             "engine restart: needs three hundred knots, which the aircraft could not "
             "reach",
             "return to LaGuardia: unreachable",
             "diversion to Teterboro: unreachable"],
         "best_evidence": ["thrust-and-airspeed", "cockpit-voice-recorder"],
         "on_scene": True,
         "rationale": "no reachable runway; ditching is the only option left"},
     "note": "Emergency Justification, element 5: the agent on scene acts alone"},
]

# EXEUNT — end of file.

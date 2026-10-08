"""
THE APOLLO 13 REPLAY
A Play in Four Scenes
=====================

PROLOGUE
--------
Apollo 13 (1970), replayed through the CCL-F v0.2 runtime as an Emergency
Justification given by a separate authority.

Facts are taken only from the CCL-F v0.2 working draft (Layer 4, Execution
Gates, Overrides, "Emergency Justification"), which cites [54]: "after the
oxygen-tank failure, doing nothing meant the loss of the crew, the
condition was explicit, and survival required operating the lunar module
far outside its design mission, as a lifeboat for three, on procedures
generated and checked on the ground"; "Apollo 13 had hours and a separate
authority on the ground". The agents below are roles, not named people,
and the evidence ids name the kinds of record the draft describes; they
are illustrative, not historical claims beyond the draft's text.

What the replay makes the runtime do: the lifeboat condition is registered
and classified off-envelope, which opens a structural review that holds the
irreversible decision. The crew accepts the plan (Rule 4). The condition is
then registered Experimental (element 4), on the ground-checked procedures
as its best evidence. The ground authority, a different agent from the
acceptor, gives the Emergency Justification (element 5, not on scene). The
decision executes; the off-envelope review is suspended, not resolved; the
lifeboat loop is latched into executed_open with the ground authority as
its steward; a post-event review opens.

THE PLAYBILL
    Scene 1  the architecture record             (Layer 0, AP.1)
    Scene 2  the lifeboat condition              (off-envelope, Rule 2)
    Scene 3  the decision and its acceptance     (Rule 4)
    Scene 4  registered experimental; the justification from the ground

READER'S NOTE — the event format
    As in scenarios/challenger.py: each event is a plain dict; "op" names
    the Supervisor operation, every other key except "note" is passed as a
    keyword argument, and cclf/graph.py turns strings into enums and the
    "emergency" object into an EmergencyJustification.
"""


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# MODE — the failure mode named on the signal and in the architecture.
MODE = "crew-life-support"

# ---------------------------------------------------------------------------
# APOLLO13 — the full event list, in replay order. It is the play itself
#   rather than a cast member, so it gets its own section with scene
#   comments beside the events.
# ---------------------------------------------------------------------------
APOLLO13: list[dict] = [
    # =======================================================================
    # SCENE 1 — THE ARCHITECTURE
    # A steward and a successor for the failure mode, so no Layer 0 void
    # stands in the way (a void could not be suspended).
    # =======================================================================
    {"op": "register_architecture", "by": "mission-programme",
     "stewards": {MODE: "lm-systems-team"}, "successors": {MODE: "backup-lm-team"},
     "note": "Layer 0, AP.1: stewardship registered before the emergency"},

    # =======================================================================
    # SCENE 2 — THE LIFEBOAT CONDITION
    # Classified off-envelope: an off-envelope review opens and, once review
    # opens, holds the signal in `escalated`.
    # =======================================================================
    {"op": "register_signal", "signal_id": "lm-as-lifeboat", "signal_type": "constraint",
     "description": "Survival requires operating the lunar module far outside its design "
                    "mission, as a lifeboat for three",
     "registered_by": "lm-systems-team", "referent": "technical",
     "evaluated_process": "lunar-module-design", "steward": "lm-systems-team",
     "successor": "backup-lm-team", "failure_mode": MODE,
     "note": "Layer 4, Overrides, Emergency Justification: Apollo 13 [54]"},
    {"op": "classify", "signal_id": "lm-as-lifeboat", "state": "off_envelope",
     "by": "lm-systems-team", "note": "outside the design mission: off-envelope"},
    {"op": "open_review", "signal_id": "lm-as-lifeboat", "by": "lm-systems-team"},

    # =======================================================================
    # SCENE 3 — THE DECISION AND ITS ACCEPTANCE
    # Irreversible; the crew accepts it under Rule 4.
    # =======================================================================
    {"op": "register_decision", "decision_id": "lifeboat-return",
     "description": "Return the crew using the lunar module as a lifeboat",
     "execution_class": "irreversible", "signal_ids": ["lm-as-lifeboat"],
     "by": "mission-programme"},
    {"op": "accept_decision", "decision_id": "lifeboat-return", "by": "apollo-13-crew",
     "rationale": "doing nothing means the loss of the crew",
     "note": "Rule 4: a single accepting agent"},
    {"op": "request_execution", "decision_id": "lifeboat-return", "by": "mission-control",
     "note": "held: the off-envelope review is unresolved"},

    # =======================================================================
    # SCENE 4 — REGISTERED EXPERIMENTAL; THE JUSTIFICATION FROM THE GROUND
    # Element 4: the condition is classified experimental (deliberately
    # unvalidated, under active investigation), on the ground-checked
    # procedures as the best evidence. Element 5: given by mission-control,
    # not the acceptor, and not on scene.
    # =======================================================================
    {"op": "add_evidence", "evidence_id": "ground-checked-procedures",
     "content": "Lifeboat procedures generated and checked on the ground",
     "source": "ground procedure checks", "kind": "primary_document",
     "produced_by": "ground-procedure-team", "by": "mission-control",
     "note": "Emergency Justification, element 4: best engineering evidence [54]"},
    {"op": "classify", "signal_id": "lm-as-lifeboat", "state": "experimental",
     "by": "lm-systems-team", "evidence_ids": ["ground-checked-procedures"],
     "note": "element 4: registered, not reclassified nominal"},
    {"op": "request_execution", "decision_id": "lifeboat-return", "by": "mission-control",
     "emergency": {
         "consequence": "life_safety_catastrophic",
         "time_estimate": "the crew would be lost before any structural review could "
                          "complete",
         "options_considered": ["do nothing / wait for the review: loss of the crew"],
         "best_evidence": ["ground-checked-procedures"],
         "on_scene": False,
         "rationale": "survival requires the lifeboat; there is no in-envelope option"},
     "note": "Emergency Justification: separate authority on the ground (element 5)"},
]

# EXEUNT — end of file.

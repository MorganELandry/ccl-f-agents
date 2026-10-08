"""
THE EVENT PIPELINE
A Play in Five Scenes
=====================

PROLOGUE
--------
Event pipeline: a LangGraph state graph that feeds one event at a time to
the supervisor.

    interpret  -> apply -> assess -> END

  interpret  for a raw "report" event, ask the advisor (probabilistic
             automation) to propose a signal type and operational state;
             every other event passes through unchanged
  apply      call the matching Supervisor operation; a refused operation is
             recorded as the outcome, not raised, so a replay continues
  assess     snapshot coherence for any decision the event touched

The supervisor holds all state and every rule. The graph only orchestrates,
which keeps the safety logic out of the model's reach and out of the graph.

Where this fits: supervisor.py is the deterministic Layer 4 runtime of
CCL-F v0.2. advisor.py wraps a language model that may only PROPOSE a
classification; the supervisor then applies the same Rule 2 check to that
proposal as to anyone else's. This file is the glue: it takes a list of
plain-dict events (for example a scenario from scenarios/) and pushes each
one through the three nodes above. run_demo.py and the scenario tests call
replay(); observability.py can wrap each node in a tracing span.

THE PLAYBILL (what happens in this file)
    Scene 1  EventState        the shape of the state dict passed between nodes
    Scene 2  _coerce()         turn plain strings in an event into enum values
    Scene 3  _architecture()   build an Architecture object from event fields
    Scene 4  build_graph()     wire interpret -> apply -> assess and compile it
    Scene 5  replay()          run a whole list of events through the graph

READER'S NOTE — the event dict format
    Every event is a plain dict, the kind you could load from JSON:

        {"op": "classify", "signal_id": "s1", "state": "nominal",
         "by": "engineer", "note": "why this event is here"}

      "op"     names the operation. Two values are special: "report" (ask
               the advisor first, then register and classify) and
               "register_architecture" (build an Architecture object).
               Any other value is the name of a public Supervisor method.
      "note"   free text for humans (scenarios use it to cite the spec).
               It is removed before the call and never reaches the
               supervisor.
      others   every remaining key becomes a keyword argument of that
               method, so the keys must match the method's parameter
               names exactly (for example register_signal() takes
               "registered_by", while most methods take "by").

READER'S NOTE — enum coercion
    JSON has no enums, so an event says "state": "nominal" where the
    supervisor expects OperationalState.NOMINAL. _coerce() looks up each
    key in _ENUM_FIELDS and, if the value is a string, converts it by
    calling the enum class: OperationalState("nominal") returns
    OperationalState.NOMINAL. A string that is not a valid value raises
    ValueError. Values that are already enums, and keys not in the table,
    pass through untouched.

READER'S NOTE — LangGraph in five ideas
    LangGraph builds a small workflow ("graph") out of plain functions.
      State     a dict shared by all the nodes. Here its shape is declared
                by EventState, a TypedDict (see Scene 1).
      Nodes     functions that take the current state and return a dict of
                the keys they want to update. LangGraph merges that dict
                into the state (by default, each returned key simply
                replaces the old value).
      Edges     add_edge(a, b) means "after node a, run node b". START and
                END are LangGraph's built-in entry and exit markers.
      compile   builder.compile() checks the wiring and returns a runnable
                graph object.
      invoke    graph.invoke(initial_state) runs the nodes in edge order
                and returns the final state dict.
    Here the graph is a straight line, so it behaves like calling the three
    functions in turn; LangGraph gives a uniform place to hang tracing on
    each node (the `wrap` hook) and room to add branches later.

READER'S NOTE — why a refused operation is recorded, not raised
    When the supervisor refuses an operation (an escalated signal cannot be
    closed, a signal id is registered twice, an act has no named agent, ...)
    it raises TransitionRefused and the operation does not go ahead. A refused
    state-machine transition is also written to the audit trail as
    TRANSITION_REFUSED (a refused re-entry as REENTRY_REFUSED) before the
    exception is raised. (A nominal classification without
    evidence is different: it is not raised at all; classify() records
    CLASSIFICATION_REJECTED and applies elevated uncertainty instead.)
    The apply node catches the exception and returns it as
    the event's outcome with refused=True. That is deliberate: a replay of
    a historical case is MEANT to hit refusals (they are the point of the
    demo), and stopping at the first one would hide everything after it.
    Only TransitionRefused is caught; any other exception (a misspelled key
    giving a TypeError, a missing key giving a KeyError) still propagates,
    because that is a bug in the event list, not a rule doing its job.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# __future__.annotations   lets type hints mention names lazily (as text).
# typing                   Any, Callable, Optional for hints; TypedDict for
#                          declaring the shape of the graph's state dict.
# langgraph.graph          StateGraph (the graph builder) and the START / END
#                          markers that begin and end every run.
# .advisor                 Advisor: the model wrapper that proposes a signal
#                          type and operational state for "report" events.
# .supervisor              Supervisor (the rule engine) and TransitionRefused
#                          (the exception it raises when a rule says no).
# .types                   the enum classes that _coerce() converts strings
#                          into, plus Architecture for register_architecture
#                          and EmergencyJustification (with its
#                          EmergencyConsequence) for an "emergency" field.
# ===========================================================================

from __future__ import annotations

from typing import Any, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from .advisor import Advisor
from .supervisor import Supervisor, TransitionRefused
from .types import (
    AgentKind, Architecture, EmergencyConsequence, EmergencyJustification, EvidenceKind,
    ExecutionClass, ExitType, LegalSubtype, OperationalState, Referent, SignalType,
)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# _ENUM_FIELDS — maps an event key to the enum class its string value must
#   become. Field converters: event JSON uses plain strings; the supervisor
#   uses enums. Read by _coerce() (Scene 2). The leading underscore marks it
#   as private to this module.
_ENUM_FIELDS = {
    "signal_type": SignalType, "referent": Referent, "state": OperationalState,
    "kind": EvidenceKind, "execution_class": ExecutionClass, "exit_type": ExitType,
    "legal_subtype": LegalSubtype, "agent_kind": AgentKind,
}


# ===========================================================================
# SCENE 1 — THE SHAPE OF THE STATE
# EventState: which keys travel between the three nodes
# ===========================================================================

class EventState(TypedDict, total=False):
    """
    The state dict that LangGraph passes from node to node for ONE event.

    A TypedDict is an ordinary dict at runtime; the class only tells type
    checkers (and readers) which keys exist and what they hold.
    `total=False` means every key is optional, which matters because the
    graph starts with only "event" and each node adds its own keys.

      event       the raw event dict, exactly as given to replay()
      proposal    interpret's output: the advisor's proposal for a "report"
                  event (as plain strings and a flag), otherwise None
      outcome     apply's one-line, human-readable result, e.g.
                  "classify ok" or "attempt_closure refused: ..."
      refused     True when the supervisor refused the operation (or the
                  op name was unknown)
      result      whatever the Supervisor method returned (only set on
                  success by the generic branch of apply)
      coherence   assess's snapshot {"decision", "score", "factors"} for the
                  decision this event named, otherwise None
    """
    event: dict
    proposal: Optional[dict]
    outcome: str
    refused: bool
    result: Any
    coherence: Optional[dict]


# ===========================================================================
# SCENE 2 — THE TRANSLATOR
# _coerce(): turn JSON-style strings into the enums the supervisor expects
# ===========================================================================

def _coerce(args: dict) -> dict:
    """
    Return a copy of `args` with enum-typed fields converted to enums.

    Enter:   args   the event's keyword arguments (op and note already removed)
    Exit:    a new dict with the same keys; any key listed in _ENUM_FIELDS
             whose value is a str is replaced by the enum member, e.g.
             "nominal" -> OperationalState.NOMINAL; an "emergency" dict
             becomes an EmergencyJustification
             raises ValueError if such a string is not a valid enum value
    """
    # PLAYERS IN THIS SCENE
    #   out    the converted copy being built
    #   k, v   each key and value of args in turn
    out = {}
    for k, v in args.items():
        # Calling an enum class with a value looks the member up by value.
        # The isinstance check leaves already-converted enums (and any
        # non-string such as a list) alone.
        out[k] = _ENUM_FIELDS[k](v) if k in _ENUM_FIELDS and isinstance(v, str) else v
    # An "emergency" given as a JSON object becomes an EmergencyJustification;
    # its consequence must be one of the EmergencyConsequence values, so a
    # justification naming schedule or cost cannot even be built (ValueError).
    # `**dict` passes the object's keys as keyword arguments; lists become
    # the tuples the frozen record holds.
    if isinstance(out.get("emergency"), dict):
        ej = dict(out["emergency"])
        ej["consequence"] = EmergencyConsequence(ej["consequence"])
        ej["options_considered"] = tuple(ej.get("options_considered", ()))
        ej["best_evidence"] = tuple(ej.get("best_evidence", ()))
        out["emergency"] = EmergencyJustification(**ej)
    return out


# ===========================================================================
# SCENE 3 — THE SET DESIGNER
# _architecture(): build the Layer 0 Architecture record from an event
# ===========================================================================

def _architecture(args: dict) -> Architecture:
    """
    Build an Architecture from a "register_architecture" event's fields.

    Enter:   args   the event dict (op and note already removed); may hold
                    stewards, successors, channels_tested (dicts) and
                    reporters, interested_parties (dicts of lists)
    Exit:    an Architecture; missing fields default to empty dicts

    This op is special-cased because Supervisor.register_architecture()
    takes one Architecture object, not loose keyword arguments. Lists from
    JSON are turned into sets, which is what Architecture stores for
    reporters and interested parties; dict() makes a fresh copy so the
    event dict is never shared with the supervisor's state.
    """
    return Architecture(
        stewards=dict(args.get("stewards", {})),
        successors=dict(args.get("successors", {})),
        channels_tested=dict(args.get("channels_tested", {})),
        # A dict comprehension: same keys, each list of names made a set.
        reporters={k: set(v) for k, v in args.get("reporters", {}).items()},
        interested_parties={k: set(v) for k, v in args.get("interested_parties", {}).items()},
    )


# ===========================================================================
# SCENE 4 — RIGGING THE STAGE
# build_graph(): define the three nodes and wire them into a compiled graph
# ===========================================================================

def build_graph(supervisor: Supervisor, advisor: Optional[Advisor] = None,
                wrap: Optional[Callable[[str, Callable], Callable]] = None):
    """
    Compile the pipeline around one supervisor. `wrap(name, fn)` may wrap
    each node (observability.py uses it for tracing).

    Enter:   supervisor   the Supervisor every event is applied to
             advisor      the Advisor used by "report" events; a default
                          Advisor() is made if none is given
             wrap         optional function (node name, node function) ->
                          replacement function; None means no wrapping
    Exit:    a compiled LangGraph graph; call .invoke({"event": event}) on
             it to process one event and get the final EventState back

    The three node functions are defined INSIDE build_graph, so each one is
    a closure: it can use `supervisor` and `advisor` from the enclosing
    function without them being passed in the state. That keeps the state
    dict small and keeps the supervisor out of anything a node returns.
    """
    # PLAYERS IN THIS SCENE
    #   advisor     the advisor to use (the argument, or a fresh default)
    #   interpret   node 1: ask the advisor about "report" events
    #   apply       node 2: perform the event on the supervisor
    #   assess      node 3: snapshot coherence for the decision named
    #   nodes       name -> node function, for the add_node loop
    #   builder     the StateGraph being wired
    #   name, fn    each node's name and function in the loop
    # `x or y` returns x if x is truthy, otherwise y: a common default idiom.
    advisor = advisor or Advisor()

    # --- Node 1: interpret -------------------------------------------------
    def interpret(state: EventState) -> EventState:
        """
        Ask the advisor to propose a classification for a "report" event.

        Enter:   state   holds "event"
        Exit:    {"proposal": {...}} for a report, {"proposal": None} otherwise

        The proposal is stored as plain strings (.value) plus the advisor's
        rationale and whether a model actually produced it (from_model is
        False when the advisor fell back to its conservative default).
        """
        # PLAYERS IN THIS SCENE
        #   event   the raw event dict
        #   p       the advisor's Proposal object
        event = state["event"]
        if event.get("op") != "report":
            return {"proposal": None}
        p = advisor.propose(event["text"])
        return {"proposal": {"signal_type": p.signal_type.value,
                             "operational_state": p.operational_state.value,
                             "rationale": p.rationale, "from_model": p.from_model}}

    # --- Node 2: apply -----------------------------------------------------
    def apply(state: EventState) -> EventState:
        """
        Perform the event's operation on the supervisor.

        Enter:   state   holds "event" and, for a report, "proposal"
        Exit:    {"outcome", "refused"} and, for generic ops on success,
                 "result"; a TransitionRefused becomes refused=True with
                 the reason in "outcome" (see the READER'S NOTE above)
        """
        # PLAYERS IN THIS SCENE
        #   event     a COPY of the event, so pop() does not alter the caller's dict
        #   op        the operation name, popped out of event
        #   p         (report only) the advisor's proposal from interpret
        #   sid       (report only) the new signal's id
        #   applied   (report only) the operational state the supervisor actually
        #             applied, which may differ from the proposal (Rule 2)
        #   method    (generic ops) the bound Supervisor method named by op
        #   result    (generic ops) what that method returned
        event = dict(state["event"])
        # --- Strip the non-argument keys -----------------------------------
        # pop() removes a key and returns its value; pop(key, None) does not
        # fail if the key is absent. What is left are keyword arguments.
        op = event.pop("op")
        event.pop("note", None)
        try:
            # --- Special case 1: a raw report, classified via the advisor ---
            if op == "report":
                p = state["proposal"]
                sid = event["signal_id"]
                supervisor.register_signal(
                    sid, SignalType(p["signal_type"]), event["text"], event["by"],
                    Referent(event.get("referent", "technical")),
                    event.get("evaluated_process", event["by"]),
                    steward=event.get("steward"), successor=event.get("successor"),
                    closure_authority=event.get("closure_authority", ()),
                    recurrence_group=event.get("recurrence_group"),
                    failure_mode=event.get("failure_mode"))
                # The model only proposes. classify() applies Rule 2 to the
                # proposal like anyone's, and proposed_by_model=True marks
                # the audit entry so readers can see where it came from.
                applied = supervisor.classify(sid, OperationalState(p["operational_state"]),
                                              event["by"], event.get("evidence_ids", ()),
                                              proposed_by_model=p["from_model"])
                return {"outcome": f"registered {sid} as {p['signal_type']}, "
                                   f"classified {applied.value}", "refused": False}
            # --- Special case 2: the Layer 0 architecture record ------------
            if op == "register_architecture":
                supervisor.register_architecture(_architecture(event), event["by"])
                return {"outcome": "architecture registered", "refused": False}
            # --- Everything else: call the Supervisor method named by op ----
            # getattr(obj, name, None) fetches an attribute by its string
            # name, or None if there is none. Names starting with "_" are
            # the supervisor's internals and are not allowed from events.
            method = getattr(supervisor, op, None)
            if method is None or op.startswith("_"):
                return {"outcome": f"unknown operation {op!r}", "refused": True}
            # **dict unpacks the dict into keyword arguments:
            # method(**{"signal_id": "s1"}) is method(signal_id="s1").
            result = method(**_coerce(event))
            return {"outcome": f"{op} ok", "refused": False, "result": result}
        except TransitionRefused as exc:
            # Recorded, not raised: the refusal becomes this event's outcome
            # and the replay carries on with the next event.
            return {"outcome": f"{op} refused: {exc}", "refused": True}

    # --- Node 3: assess ----------------------------------------------------
    def assess(state: EventState) -> EventState:
        """
        Snapshot the coherence score of the decision this event named.

        Enter:   state   holds "event"
        Exit:    {"coherence": {"decision", "score", "factors"}} if the event
                 has a decision_id that the supervisor knows, else
                 {"coherence": None}

        Read-only: Supervisor.coherence() computes a score from current
        state and does not change it.
        """
        # PLAYERS IN THIS SCENE
        #   decision   the event's decision_id, or None
        #   score      the coherence score (a float)
        #   factors    the named components that make up the score
        decision = state["event"].get("decision_id")
        if decision and decision in supervisor.decisions:
            score, factors = supervisor.coherence(decision)
            return {"coherence": {"decision": decision, "score": score, "factors": factors}}
        return {"coherence": None}

    # --- Wire the graph ----------------------------------------------------
    nodes = {"interpret": interpret, "apply": apply, "assess": assess}
    builder = StateGraph(EventState)
    for name, fn in nodes.items():
        # If a wrapper was given (e.g. a tracing span), register the wrapped
        # function instead; it must still return what fn returns.
        builder.add_node(name, wrap(name, fn) if wrap else fn)
    builder.add_edge(START, "interpret")
    builder.add_edge("interpret", "apply")
    builder.add_edge("apply", "assess")
    builder.add_edge("assess", END)
    return builder.compile()


# ===========================================================================
# SCENE 5 — THE PERFORMANCE
# replay(): push a whole event history through the graph, in order
# ===========================================================================

def replay(events: list[dict], supervisor: Optional[Supervisor] = None,
           advisor: Optional[Advisor] = None, wrap=None,
           on_event: Optional[Callable[[dict, EventState], None]] = None) -> Supervisor:
    """
    Run every event through the pipeline in order; return the supervisor.

    Enter:   events       the event dicts (e.g. scenarios.SCENARIOS["challenger"])
             supervisor   the Supervisor to apply them to; a fresh one if None
             advisor      passed to build_graph() for "report" events
             wrap         passed to build_graph() to wrap each node
             on_event     optional callback, called after each event with
                          (event, final state); run_demo.py uses it to print
                          the new audit entries
    Exit:    the supervisor, now holding the full state and audit trail

    The graph is compiled once and reused for every event. Each invoke
    starts from a fresh state containing only {"event": event}; anything
    that must persist between events lives in the supervisor, not the graph.
    """
    # PLAYERS IN THIS SCENE
    #   supervisor   the supervisor used (argument or a fresh one)
    #   graph        the compiled pipeline
    #   event        each event in turn
    #   out          the final EventState for that event
    supervisor = supervisor or Supervisor()
    graph = build_graph(supervisor, advisor, wrap)
    for event in events:
        out = graph.invoke({"event": event})
        if on_event:
            on_event(event, out)
    return supervisor

# EXEUNT — end of file.

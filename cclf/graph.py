"""
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
"""

from __future__ import annotations

from typing import Any, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from .advisor import Advisor
from .supervisor import Supervisor, TransitionRefused
from .types import (
    Architecture, EvidenceKind, ExecutionClass, ExitType, LegalSubtype,
    OperationalState, Referent, SignalType,
)


class EventState(TypedDict, total=False):
    event: dict
    proposal: Optional[dict]
    outcome: str
    refused: bool
    result: Any
    coherence: Optional[dict]


# Field converters: event JSON uses plain strings; the supervisor uses enums.
_ENUM_FIELDS = {
    "signal_type": SignalType, "referent": Referent, "state": OperationalState,
    "kind": EvidenceKind, "execution_class": ExecutionClass, "exit_type": ExitType,
    "legal_subtype": LegalSubtype,
}


def _coerce(args: dict) -> dict:
    out = {}
    for k, v in args.items():
        out[k] = _ENUM_FIELDS[k](v) if k in _ENUM_FIELDS and isinstance(v, str) else v
    return out


def _architecture(args: dict) -> Architecture:
    return Architecture(
        stewards=dict(args.get("stewards", {})),
        successors=dict(args.get("successors", {})),
        channels_tested=dict(args.get("channels_tested", {})),
        reporters={k: set(v) for k, v in args.get("reporters", {}).items()},
        interested_parties={k: set(v) for k, v in args.get("interested_parties", {}).items()},
    )


def build_graph(supervisor: Supervisor, advisor: Optional[Advisor] = None,
                wrap: Optional[Callable[[str, Callable], Callable]] = None):
    """
    Compile the pipeline around one supervisor. `wrap(name, fn)` may wrap
    each node (observability.py uses it for tracing).
    """
    advisor = advisor or Advisor()

    def interpret(state: EventState) -> EventState:
        event = state["event"]
        if event.get("op") != "report":
            return {"proposal": None}
        p = advisor.propose(event["text"])
        return {"proposal": {"signal_type": p.signal_type.value,
                             "operational_state": p.operational_state.value,
                             "rationale": p.rationale, "from_model": p.from_model}}

    def apply(state: EventState) -> EventState:
        event = dict(state["event"])
        op = event.pop("op")
        event.pop("note", None)
        try:
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
                applied = supervisor.classify(sid, OperationalState(p["operational_state"]),
                                              event["by"], event.get("evidence_ids", ()),
                                              proposed_by_model=p["from_model"])
                return {"outcome": f"registered {sid} as {p['signal_type']}, "
                                   f"classified {applied.value}", "refused": False}
            if op == "register_architecture":
                supervisor.register_architecture(_architecture(event), event["by"])
                return {"outcome": "architecture registered", "refused": False}
            method = getattr(supervisor, op, None)
            if method is None or op.startswith("_"):
                return {"outcome": f"unknown operation {op!r}", "refused": True}
            result = method(**_coerce(event))
            return {"outcome": f"{op} ok", "refused": False, "result": result}
        except TransitionRefused as exc:
            return {"outcome": f"{op} refused: {exc}", "refused": True}

    def assess(state: EventState) -> EventState:
        decision = state["event"].get("decision_id")
        if decision and decision in supervisor.decisions:
            score, factors = supervisor.coherence(decision)
            return {"coherence": {"decision": decision, "score": score, "factors": factors}}
        return {"coherence": None}

    nodes = {"interpret": interpret, "apply": apply, "assess": assess}
    builder = StateGraph(EventState)
    for name, fn in nodes.items():
        builder.add_node(name, wrap(name, fn) if wrap else fn)
    builder.add_edge(START, "interpret")
    builder.add_edge("interpret", "apply")
    builder.add_edge("apply", "assess")
    builder.add_edge("assess", END)
    return builder.compile()


def replay(events: list[dict], supervisor: Optional[Supervisor] = None,
           advisor: Optional[Advisor] = None, wrap=None,
           on_event: Optional[Callable[[dict, EventState], None]] = None) -> Supervisor:
    """Run every event through the pipeline in order; return the supervisor."""
    supervisor = supervisor or Supervisor()
    graph = build_graph(supervisor, advisor, wrap)
    for event in events:
        out = graph.invoke({"event": event})
        if on_event:
            on_event(event, out)
    return supervisor

"""
CCL-F LangGraph Graph Assembly
==============================
Wires the eight CCL-F nodes into a LangGraph StateGraph.

Graph topology:
  START
    ↓
  evidence_intake           (score all un-scored evidence)
    ↓
  acs_inference             (estimate hidden ACS distribution)
    ↓
  aco_detection             (check for adversarial opacity)
    ↓
  transition_evaluation     (LLM proposes: advance / hold / escalate)
    ↓
  transition_guard          (structural block — LLM-free)
    ↓ (conditional)
  human_review ────── (if ACO or high-stakes transition)
    ↓
  apply_transition
    ↓ (conditional)
  terminate ──────── (if EXECUTION reached or should_terminate)
    ↓
  END  (one cycle per evidence batch; the caller streams the next batch)

Human-in-the-loop interrupt is configured via LangGraph checkpointer.
Set interrupt_before=["human_review"] to pause and wait for external approval.
"""

from __future__ import annotations
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .types import CCLFAgentState
from .nodes import (
    evidence_intake,
    acs_inference,
    aco_detection,
    transition_evaluation,
    transition_guard,
    human_review,
    apply_transition,
    terminate,
)


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def route_after_guard(state: CCLFAgentState) -> Literal["human_review", "apply_transition"]:
    """
    After the guard, route to human review if:
      - ACO has been detected, OR
      - A transition is proposed (always require human-in-the-loop)
    Otherwise go directly to apply_transition (which will no-op if nothing proposed).
    """
    if state.proposed_transition is not None or state.aco_detected:
        return "human_review"
    return "apply_transition"


def route_after_apply(state: CCLFAgentState) -> Literal["terminate", "evidence_intake", END]:
    """
    After applying (or not applying) a transition:
      - Terminate if flagged
      - Otherwise end this cycle. Evidence only arrives from the caller, so
        looping back would re-run the LLM nodes with nothing new to score
        and never return. The caller streams the graph again with the
        next evidence batch (state persists via the checkpointer).
    """
    if state.should_terminate:
        return "terminate"
    return END


# ---------------------------------------------------------------------------
# Checkpointer
# ---------------------------------------------------------------------------

# State types the checkpoint may rebuild. Newer LangGraph releases refuse to
# deserialize unregistered classes; older ones ignore this setting.
_CHECKPOINT_TYPES = [
    ("cclf.types", name)
    for name in ("CCLFAgentState", "CommitmentState", "Evidence",
                 "ACSEstimate", "AuditEntry")
]


def _make_checkpointer() -> MemorySaver:
    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES)
    except (ImportError, TypeError):
        return MemorySaver()
    return MemorySaver(serde=serde)


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(
    interrupt_before_human: bool = True,
    use_checkpointer: bool = True,
) -> StateGraph:
    """
    Build and return the compiled CCL-F commitment agent graph.

    Args:
        interrupt_before_human: If True, graph pauses at human_review
            and waits for external resume (production mode).
            If False, human_review runs inline via stdin (CLI demo mode).
        use_checkpointer: If True, attach MemorySaver for state persistence
            across interrupts. Required for interrupt_before to work.
    """
    builder = StateGraph(CCLFAgentState)

    # Add all nodes
    builder.add_node("evidence_intake",       evidence_intake)
    builder.add_node("acs_inference",         acs_inference)
    builder.add_node("aco_detection",         aco_detection)
    builder.add_node("transition_evaluation", transition_evaluation)
    builder.add_node("transition_guard",      transition_guard)
    builder.add_node("human_review",          human_review)
    builder.add_node("apply_transition",      apply_transition)
    builder.add_node("terminate",             terminate)

    # Linear edges
    builder.add_edge(START,                    "evidence_intake")
    builder.add_edge("evidence_intake",        "acs_inference")
    builder.add_edge("acs_inference",          "aco_detection")
    builder.add_edge("aco_detection",          "transition_evaluation")
    builder.add_edge("transition_evaluation",  "transition_guard")

    # Conditional: guard → human_review or apply_transition
    builder.add_conditional_edges(
        "transition_guard",
        route_after_guard,
        {
            "human_review":    "human_review",
            "apply_transition": "apply_transition",
        },
    )

    # human_review always feeds apply_transition
    builder.add_edge("human_review", "apply_transition")

    # Conditional: apply → terminate or end this cycle
    builder.add_conditional_edges(
        "apply_transition",
        route_after_apply,
        {
            "terminate":       "terminate",
            "evidence_intake": "evidence_intake",
            END:               END,
        },
    )

    # terminate → END
    builder.add_edge("terminate", END)

    # Compile
    interrupt_nodes = ["human_review"] if interrupt_before_human else []
    checkpointer    = _make_checkpointer() if use_checkpointer else None

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes,
    )

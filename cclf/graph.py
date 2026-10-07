"""
THE STAGE PLAN
A Play in Four Scenes
=====================

PROLOGUE
--------
nodes.py defines eight separate steps ("nodes"), each a plain function that
takes the agent state and returns it changed. On their own they do nothing
in particular order. This file is the stage plan: it wires the eight CCL-F
nodes into a LangGraph StateGraph, saying which node runs first, which
comes next, where the path forks, and where the run stops.

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
  human_review ────── (if ACO or a transition is proposed)
    ↓
  apply_transition
    ↓ (conditional)
  terminate ──────── (if should_terminate is set, e.g. EXECUTION reached)
    ↓
  END  (one cycle per evidence batch; the caller streams the next batch)

Human-in-the-loop interrupt is configured via LangGraph checkpointer.
Set interrupt_before=["human_review"] to pause and wait for external approval.

THE PLAYBILL (what happens in this file)
    Scene 1  route_after_guard()   after the guard: ask a human, or apply?
    Scene 2  route_after_apply()   after applying: terminate, or end the cycle?
    Scene 3  _make_checkpointer()  build the memory that lets a run pause
    Scene 4  build_graph()         assemble and compile the whole graph

READER'S NOTE — LangGraph StateGraph
    LangGraph is a library for running a program as a *graph*: a set of
    steps (nodes) joined by arrows (edges). StateGraph(CCLFAgentState)
    creates an empty graph whose shared data has the shape of the
    CCLFAgentState dataclass (types.py). LangGraph passes that state into
    each node and stores whatever the node returns as the new state.
    Calling .compile() turns the plan into a runnable object with methods
    such as .invoke(), .stream(), .get_state() and .update_state().

READER'S NOTE — nodes and edges
    A node is a named step: add_node("evidence_intake", evidence_intake)
    registers the function under that name. An edge is a fixed arrow:
    add_edge("a", "b") means "after a finishes, always run b". START and
    END are special built-in markers for "where a run begins" and "where
    a run stops".

READER'S NOTE — conditional edges
    add_conditional_edges("a", router, path_map) means "after a finishes,
    call router(state); it returns a key, and path_map says which node that
    key leads to". This is how the graph makes a decision. The routers here
    (Scenes 1 and 2) are plain Python with no LLM in them, so the routing
    is deterministic, just like guards.py.

READER'S NOTE — checkpointer and interrupt_before
    A checkpointer saves a copy of the state after each step, filed under a
    "thread_id" that the caller supplies in config, e.g.
    {"configurable": {"thread_id": "abc"}}. MemorySaver keeps those copies
    in this process's memory. Because the state is saved, a run can stop
    and be continued later. interrupt_before=["human_review"] tells the
    compiled graph to stop just *before* running human_review. The caller
    can then inspect graph.get_state(config), record a decision with
    graph.update_state(config, {...}), and resume with
    graph.invoke(None, config). interrupt_before needs a checkpointer,
    since without saved state there would be nothing to resume from.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# `from __future__ import annotations` stores type hints as text instead of
#   evaluating them at runtime.
# Literal          a type hint for "one of exactly these values"; used to
#                  document which keys each router may return.
# StateGraph       the graph builder (see READER'S NOTE above).
# START, END       built-in markers for the entry and exit of a run.
# MemorySaver      an in-memory checkpointer (see READER'S NOTE above).
# CCLFAgentState   the shared state dataclass from types.py.
# _nodes           the nodes.py module; its eight step functions are looked
#                  up on it inside build_graph() (Scene 4).
# ===========================================================================

from __future__ import annotations
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .types import CCLFAgentState
# The nodes module itself, not its functions. build_graph() looks each node
# function up on this module at build time, so if observability.py has
# swapped in traced wrappers (instrument_nodes), the graph runs the wrappers.
# Importing the functions by name here would freeze the untraced originals.
from . import nodes as _nodes


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# _CHECKPOINT_TYPES — the classes a saved checkpoint is allowed to rebuild.
#   State types the checkpoint may rebuild. Newer LangGraph releases refuse
#   to deserialize unregistered classes; older ones ignore this setting.
#   Each item is a (module name, class name) pair, built with a "list
#   comprehension": for each class name in the tuple, make the pair
#   ("cclf.types", name). Result:
#     [("cclf.types", "CCLFAgentState"), ("cclf.types", "CommitmentState"), ...]
#   It is handed to the checkpoint serializer in Scene 3. Without it, a
#   paused run could not be loaded back as our own dataclasses.
_CHECKPOINT_TYPES = [
    ("cclf.types", name)
    for name in ("CCLFAgentState", "CommitmentState", "Evidence",
                 "ACSEstimate", "AuditEntry")
]


# ===========================================================================
# SCENE 1 — THE FORK AFTER THE GUARD
# route_after_guard(): does a human need to look at this before it applies?
# ===========================================================================

def route_after_guard(state: CCLFAgentState) -> Literal["human_review", "apply_transition"]:
    """
    Choose the next node after transition_guard has run.

    Enter:   state   the agent state as transition_guard left it
    Exit:    "human_review" or "apply_transition" (a key in the path map
             given to add_conditional_edges in Scene 4)

    After the guard, route to human review if:
      - ACO has been detected, OR
      - A transition is proposed (always require human-in-the-loop)
    Otherwise go directly to apply_transition (which will no-op if nothing proposed).

    If the guard blocked a proposal, it has already set proposed_transition
    to None, so a blocked move never reaches a human as if it were legal.
    """
    # --- Anything to review? --------------------------------------------
    if state.proposed_transition is not None or state.aco_detected:
        return "human_review"
    # --- Nothing to review: go straight on --------------------------------
    return "apply_transition"


# ===========================================================================
# SCENE 2 — THE FORK AFTER APPLYING
# route_after_apply(): stop for good, or just end this cycle?
# ===========================================================================

def route_after_apply(state: CCLFAgentState) -> Literal["terminate", "evidence_intake", END]:
    """
    Choose what happens after apply_transition has run.

    Enter:   state   the agent state as apply_transition left it
    Exit:    "terminate" if state.should_terminate is set (for example,
             apply_transition sets it when EXECUTION is reached);
             otherwise END, which finishes this run of the graph

    After applying (or not applying) a transition:
      - Terminate if flagged
      - Otherwise end this cycle. Evidence only arrives from the caller, so
        looping back would re-run the LLM nodes with nothing new to score
        and never return. The caller streams the graph again with the
        next evidence batch (state persists via the checkpointer).

    Why not loop back? The return type hint still lists "evidence_intake",
    and the path map in Scene 4 still has an entry for it, but this
    function never returns it. A loop would be an infinite loop: no new
    evidence can appear while the graph is running, so each pass would
    spend LLM calls on the same evidence and the call would never come
    back to the caller. Ending the cycle hands control back instead.
    """
    # --- Final curtain requested ------------------------------------------
    if state.should_terminate:
        return "terminate"
    # --- Otherwise this cycle is done; the caller sends the next batch ------
    return END


# ===========================================================================
# SCENE 3 — THE PROMPTER'S BOOK
# _make_checkpointer(): build the memory that lets a run pause and resume
# ===========================================================================

def _make_checkpointer() -> MemorySaver:
    """
    Create an in-memory checkpointer that can rebuild our dataclasses.

    Enter:   (no arguments)
    Exit:    a MemorySaver. If this LangGraph version supports an allow-list
             of classes, the MemorySaver uses a serializer that permits the
             classes in _CHECKPOINT_TYPES; otherwise a plain MemorySaver.

    A "serializer" (serde = serialize / deserialize) is the part that turns
    the state into bytes for saving, and back into objects when loading.
    """
    # PLAYERS IN THIS SCENE
    #   JsonPlusSerializer   LangGraph's serializer class, imported here
    #   serde                a serializer configured with our allow-list

    # --- Try the newer, allow-list-aware serializer ------------------------
    # The import sits inside the function, inside `try`, because older
    # LangGraph releases may not have this module (ImportError) or may not
    # accept the allowed_msgpack_modules argument (TypeError).
    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES)
    except (ImportError, TypeError):
        # --- Older LangGraph: the default MemorySaver is enough -----------
        return MemorySaver()

    # --- Newer LangGraph: use the allow-listed serializer ------------------
    return MemorySaver(serde=serde)


# ===========================================================================
# SCENE 4 — RAISING THE CURTAIN
# build_graph(): assemble every node and edge, then compile the graph
# ===========================================================================

def build_graph(
    interrupt_before_human: bool = True,
    use_checkpointer: bool = True,
) -> StateGraph:
    """
    Build and return the compiled CCL-F commitment agent graph.

    Enter:   interrupt_before_human   If True, graph pauses at human_review
                                      and waits for external resume
                                      (production mode). If False,
                                      human_review runs inline via stdin
                                      (CLI demo mode), unless
                                      CCLF_AUTO_APPROVE=true (see nodes.py).
             use_checkpointer         If True, attach MemorySaver for state
                                      persistence across interrupts.
                                      Required for interrupt_before to work.
    Exit:    the compiled graph, ready for .invoke() / .stream(). (The hint
             says StateGraph, but what .compile() actually returns is
             LangGraph's compiled-graph object, not the builder.)
    """
    # PLAYERS IN THIS SCENE
    #   builder           the StateGraph being assembled
    #   interrupt_nodes   names of nodes to pause before ([] = never pause)
    #   checkpointer      a MemorySaver from Scene 3, or None

    builder = StateGraph(CCLFAgentState)

    # --- Add all nodes: name each step and give its function ---------------
    # Each function is fetched from the nodes module *now*, at build time,
    # so any wrapper installed by observability.instrument_nodes() is used.
    builder.add_node("evidence_intake",       _nodes.evidence_intake)
    builder.add_node("acs_inference",         _nodes.acs_inference)
    builder.add_node("aco_detection",         _nodes.aco_detection)
    builder.add_node("transition_evaluation", _nodes.transition_evaluation)
    builder.add_node("transition_guard",      _nodes.transition_guard)
    builder.add_node("human_review",          _nodes.human_review)
    builder.add_node("apply_transition",      _nodes.apply_transition)
    builder.add_node("terminate",             _nodes.terminate)

    # --- Linear edges: the fixed opening sequence ------------------------
    builder.add_edge(START,                    "evidence_intake")
    builder.add_edge("evidence_intake",        "acs_inference")
    builder.add_edge("acs_inference",          "aco_detection")
    builder.add_edge("aco_detection",          "transition_evaluation")
    builder.add_edge("transition_evaluation",  "transition_guard")

    # --- Conditional: guard → human_review or apply_transition -------------
    # The dict is the path map: router's return value → node to run next.
    builder.add_conditional_edges(
        "transition_guard",
        route_after_guard,
        {
            "human_review":    "human_review",
            "apply_transition": "apply_transition",
        },
    )

    # --- human_review always feeds apply_transition ----------------------
    builder.add_edge("human_review", "apply_transition")

    # --- Conditional: apply → terminate or end this cycle -----------------
    # The "evidence_intake" entry is listed but never chosen: Scene 2 never
    # returns it (see that scene for why the cycle ends instead of looping).
    builder.add_conditional_edges(
        "apply_transition",
        route_after_apply,
        {
            "terminate":       "terminate",
            "evidence_intake": "evidence_intake",
            END:               END,
        },
    )

    # --- terminate → END --------------------------------------------------
    builder.add_edge("terminate", END)

    # --- Compile ------------------------------------------------------------
    # Decide where to pause and whether to keep checkpoints. These two
    # lines use Python's one-line "X if condition else Y" expression.
    interrupt_nodes = ["human_review"] if interrupt_before_human else []
    checkpointer    = _make_checkpointer() if use_checkpointer else None

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes,
    )

# EXEUNT — end of file.

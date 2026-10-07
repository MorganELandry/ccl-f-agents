"""
THE GRAPH WITHOUT A VOICE
A Play in Three Scenes
=========================

PROLOGUE
--------
Graph routing and degraded-mode tests. No LLM credentials required.

cclf/graph.py wires the agent's nodes into a LangGraph state graph. This file
checks two things about that wiring:

  1. route_after_apply(), the function that decides where the graph goes
     after a transition is applied, ends the cycle or terminates correctly.
  2. With no API key at all, a full pass through the graph still finishes,
     and the LLM-free transition guard still runs. This is "degraded mode":
     every LLM call fails, cclf.nodes._llm_json() catches the failure and
     returns an error dict, and the nodes fall back to safe defaults
     (for example, "hold" instead of "advance").

Run: pytest tests/ -v

THE PLAYBILL
    Scene 1  test_cycle_ends_after_one_pass        no new evidence → END
    Scene 2  test_terminate_flag_routes_to_terminate   should_terminate → "terminate"
    Scene 3  test_batch_completes_without_llm      a whole batch runs with no API key

READER'S NOTE — LangGraph in one paragraph
    A LangGraph "state graph" is a set of named nodes (plain Python functions
    that take the state and return it) joined by edges. Some edges are
    conditional: a routing function looks at the state and returns the name
    of the next node, or the special constant END meaning "stop this run".
    build_graph() compiles the graph; graph.stream(...) runs it and yields
    the state after each node. A "checkpointer" saves the state between runs
    under a `thread_id`, which is why the config below carries one.

READER'S NOTE — the `monkeypatch` fixture
    A pytest *fixture* is a helper that pytest builds and hands to a test
    automatically: you just name it as a parameter, and pytest sees the name
    and passes in the object. `monkeypatch` is a built-in fixture for making
    temporary changes that pytest undoes when the test ends:
        monkeypatch.setenv(name, value)   set an environment variable
        monkeypatch.delenv(name, raising=False)
                                          remove one; raising=False means
                                          "do not complain if it was not set"
        monkeypatch.setattr(obj, name, value)
                                          replace an attribute or function
    Because everything is put back afterwards, one test's changes cannot leak
    into the next test or into your real shell environment.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# langgraph.graph.END   the marker a routing function returns to stop a run.
# cclf                  build_graph (compiles the agent), CCLFAgentState (the
#                       state object), Evidence (one evidence item).
# cclf.graph            route_after_apply, the routing function tested directly.
# scenarios             MCAS_SCENARIO, real evidence to feed the graph.
# ===========================================================================

from langgraph.graph import END

from cclf import build_graph, CCLFAgentState, Evidence
from cclf.graph import route_after_apply
from scenarios import MCAS_SCENARIO


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# (none) — every test builds its own state and graph.
# ===========================================================================


# ===========================================================================
# SCENE 1 — THE CURTAIN FALLS
# Proves: after applying a transition, a normal state ends the cycle (END)
# instead of looping back to evidence_intake.
# ===========================================================================

def test_cycle_ends_after_one_pass():
    """
    Without new evidence the graph must not loop back on itself.

    Enter:   (nothing)
    Exit:    passes if route_after_apply() on a fresh state returns END

    Why it matters: evidence only arrives from the caller, so looping back
    would re-run the LLM nodes with nothing new and never return.
    """
    # --- Setting the stage / The action / The verdict ----------------------
    # A fresh CCLFAgentState has should_terminate=False.
    assert route_after_apply(CCLFAgentState()) == END


# ===========================================================================
# SCENE 2 — THE FINAL BOW
# Proves: when should_terminate is set, routing goes to the "terminate" node.
# ===========================================================================

def test_terminate_flag_routes_to_terminate():
    """
    A state flagged for termination is routed to the terminate node.

    Enter:   (nothing)
    Exit:    passes if route_after_apply() returns "terminate"
    """
    # PLAYERS IN THIS SCENE
    #   state   a fresh agent state with the termination flag set by hand

    # --- Setting the stage -------------------------------------------------
    state = CCLFAgentState()
    state.should_terminate = True
    # --- The action and the verdict ----------------------------------------
    assert route_after_apply(state) == "terminate"


# ===========================================================================
# SCENE 3 — THE SHOW GOES ON WITHOUT ITS STAR
# Proves: with no API key, one evidence batch runs to completion and the
# LLM-free transition guard still leaves its message in the state.
# ===========================================================================

def test_batch_completes_without_llm(monkeypatch):
    """
    With no API key, a batch finishes and the LLM-free guard still runs.

    Enter:   monkeypatch   pytest fixture for temporary environment changes
    Exit:    passes if any message in the final state mentions
             "transition_guard"

    No fake LLM is swapped in here. The real backend is used and fails
    (no key), and the test proves the graph degrades gracefully.
    """
    # PLAYERS IN THIS SCENE
    #   graph    the compiled agent graph
    #   state    the agent state; replaced after every streamed chunk
    #   config   LangGraph run settings; thread_id names this run for the
    #            checkpointer
    #   chunk    one snapshot of the state, yielded by graph.stream()

    # --- Setting the stage: remove the key, silence telemetry --------------
    # Delete OPENAI_API_KEY in case the developer has one set, so the LLM
    # call really cannot succeed. CCLF_OBSERVABILITY_ENABLED=false is a
    # precaution meaning "no OpenTelemetry". In practice build_graph() does
    # not instrument nodes itself (run_demo.py does), and cclf/observability.py
    # reads this variable once when it is first imported, so the line just
    # makes the intent explicit.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "false")

    # --- Setting the stage: build the graph and load one evidence item -----
    # interrupt_before_human=True means the graph would pause before the
    # human_review node rather than reading from the keyboard. With no LLM
    # the evaluator holds, nothing is proposed, and human_review is never
    # reached anyway.
    graph = build_graph(interrupt_before_human=True, use_checkpointer=True)
    state = CCLFAgentState()
    state.evidence_buffer.append(Evidence(**MCAS_SCENARIO[0]))
    config = {"configurable": {"thread_id": "test"}}

    # --- The action: run one cycle -----------------------------------------
    # stream_mode="values" yields the full state after each node. Depending
    # on the LangGraph version a chunk may be a dict or the dataclass, so
    # from_stream() normalises it back into a CCLFAgentState.
    for chunk in graph.stream(state, config=config, stream_mode="values"):
        state = CCLFAgentState.from_stream(chunk)

    # --- The verdict -------------------------------------------------------
    # Every message from the guard node starts with "[transition_guard]".
    # any(...) is True if at least one message contains the text.
    assert any("transition_guard" in m for m in state.messages)

# EXEUNT — end of file.

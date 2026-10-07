"""
THE UNDERSTUDIES TAKE THE STAGE
A Play in Two Scenes
===============================

PROLOGUE
--------
Observability tests. No LLM credentials and no OpenTelemetry collector needed.

cclf/observability.py can wrap every node function with a tracing wrapper
(instrument_nodes), so each step of a run is recorded as an OpenTelemetry
span. That only helps if the graph actually *runs* the wrappers. These tests
prove two things that once went wrong:

  - a graph built after instrument_nodes() calls the wrapped nodes, not the
    originals (graph.py must look the functions up when it builds the graph);
  - the on/off switch CCLF_OBSERVABILITY_ENABLED is honoured even when it is
    set after observability.py has been imported (run_demo.py --no-obs).

Run: pytest tests/ -v

THE PLAYBILL
    Scene 1  test_graph_runs_instrumented_nodes      wrappers really run
    Scene 2  test_switch_is_read_when_setup_runs     --no-obs really disables

READER'S NOTE — the caplog fixture
    `caplog` is a built-in pytest fixture that captures messages sent through
    Python's logging module during a test. caplog.at_level(logging.INFO)
    makes sure INFO messages are captured, and caplog.text holds them all as
    one string, so the test can check what was logged.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# io, contextlib   swallow the printed output of human_review.
# logging          log levels, for caplog.
# cclf             graph builder, state, Evidence; the nodes and observability
#                  modules themselves, so their attributes can be patched.
# scenarios        MCAS_SCENARIO, real evidence to feed the graph.
# test_end_to_end  scripted_llm, the shared fake LLM.
# ===========================================================================

import contextlib
import io
import logging

from cclf import build_graph, CCLFAgentState, Evidence
from cclf import nodes
from cclf import observability
from scenarios import MCAS_SCENARIO
from test_end_to_end import scripted_llm


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# (none) — each test builds its own graph and instrumentor.
# ===========================================================================


# ===========================================================================
# SCENE 1 — THE WRAPPERS REALLY RUN
# Proves: after instrument_nodes(), a newly built graph calls the wrappers.
# ===========================================================================

def test_graph_runs_instrumented_nodes(monkeypatch):
    """
    Every node a run passes through goes through its wrapper.

    Enter:   monkeypatch   swaps in the fake LLM and a recording wrapper; all
                           patches (including the wrapped node functions) are
                           undone when the test ends
    Exit:    passes if the wrapper saw the four always-run nodes, in order
    """
    # PLAYERS IN THIS SCENE
    #   called      names of the nodes whose wrapper ran, in order
    #   recording   a stand-in for observability._wrap_node
    #   graph       the graph, built after the nodes were wrapped
    #   state       the starting state, with one evidence item

    # --- Setting the stage -------------------------------------------------
    monkeypatch.setattr(nodes, "_llm_json", scripted_llm("hold"))
    # The fake reports ACO, which routes to human_review; unattended mode
    # stops that node from waiting for keyboard input.
    monkeypatch.setenv("CCLF_AUTO_APPROVE", "true")
    called = []

    def recording(fn, name, instrumentor):
        # Same shape as the real _wrap_node: take the original, return a
        # function that records its name and then calls the original.
        def wrapped(state):
            called.append(name)
            return fn(state)
        return wrapped

    monkeypatch.setattr(observability, "_wrap_node", recording)
    # Keep the real node functions so monkeypatch restores them afterwards.
    for name in ("evidence_intake", "acs_inference", "aco_detection",
                 "transition_evaluation", "transition_guard", "human_review",
                 "apply_transition", "terminate"):
        monkeypatch.setattr(nodes, name, getattr(nodes, name))

    # --- The action: wrap first, then build, then run one batch ------------
    observability.instrument_nodes(nodes, instrumentor=None)
    graph = build_graph(interrupt_before_human=False, use_checkpointer=True)
    state = CCLFAgentState()
    state.evidence_buffer.append(Evidence(**MCAS_SCENARIO[0]))
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in graph.stream(state, config={"configurable": {"thread_id": "obs"}}):
            pass

    # --- The verdict -------------------------------------------------------
    assert called[:4] == ["evidence_intake", "acs_inference",
                          "aco_detection", "transition_evaluation"]


# ===========================================================================
# SCENE 2 — THE SWITCH IS READ WHEN IT MATTERS
# Proves: setting CCLF_OBSERVABILITY_ENABLED=false after import still disables.
# ===========================================================================

def test_switch_is_read_when_setup_runs(monkeypatch, caplog):
    """
    setup() honours the switch as it stands when setup() runs.

    Enter:   monkeypatch   sets the environment variable for this test only
             caplog        captures what setup() logs
    Exit:    passes if setup() logs that observability is disabled
    """
    # PLAYERS IN THIS SCENE
    #   inst   a fresh instrumentor (not the shared one)

    # --- Setting the stage: module already imported, switch flipped now ----
    monkeypatch.setattr(observability, "_ENABLED", True)   # as if imported "on"
    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "false")
    inst = observability.CCLFInstrumentor()

    # --- The action --------------------------------------------------------
    with caplog.at_level(logging.INFO, logger=observability.logger.name):
        inst.setup()

    # --- The verdict -------------------------------------------------------
    assert "Observability disabled" in caplog.text

# EXEUNT — end of file.

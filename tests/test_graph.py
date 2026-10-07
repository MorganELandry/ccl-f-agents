"""
Graph routing and degraded-mode tests. No LLM credentials required.

Run: pytest tests/ -v
"""

from langgraph.graph import END

from cclf import build_graph, CCLFAgentState, Evidence
from cclf.graph import route_after_apply
from scenarios import MCAS_SCENARIO


def test_cycle_ends_after_one_pass():
    """Without new evidence the graph must not loop back on itself."""
    assert route_after_apply(CCLFAgentState()) == END


def test_terminate_flag_routes_to_terminate():
    state = CCLFAgentState()
    state.should_terminate = True
    assert route_after_apply(state) == "terminate"


def test_batch_completes_without_llm(monkeypatch):
    """With no API key, a batch finishes and the LLM-free guard still runs."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "false")
    graph = build_graph(interrupt_before_human=True, use_checkpointer=True)
    state = CCLFAgentState()
    state.evidence_buffer.append(Evidence(**MCAS_SCENARIO[0]))
    config = {"configurable": {"thread_id": "test"}}

    for chunk in graph.stream(state, config=config, stream_mode="values"):
        state = CCLFAgentState.from_stream(chunk)

    assert any("transition_guard" in m for m in state.messages)

"""
THE BRAINS
A Play in Three Scenes
======================

PROLOGUE
--------
A brain decides what an agent does with its turn. The runtime does not care
which brain is behind an agent: it only sees tool calls. Two are provided.

  ClaudeBrain    a Claude agent run through the Claude Agent SDK. Its only
                 tools are the agent's ToolSpecs, served from an in-process
                 MCP server; Claude Code's built-in tools (shell, files, web)
                 are switched off, so the model can act on the world only
                 through the runtime. Each agent keeps one session across
                 turns, so it remembers what it did.
  ScriptedBrain  a fixed list of tool calls per turn. No model, no key, fully
                 deterministic. The tests and the offline demos use it, and
                 it gives the experiments a baseline policy to compare
                 Claude against.

THE PLAYBILL
    Scene 1  Brain            the interface
    Scene 2  ScriptedBrain    deterministic turns
    Scene 3  ClaudeBrain      a Claude agent through the Agent SDK
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol

from .runtime import ToolSpec


# ===========================================================================
# SCENE 1 — THE INTERFACE
# ===========================================================================

class Brain(Protocol):
    async def turn(self, agent: str, system: str, prompt: str,
                   tools: list[ToolSpec]) -> str:
        """Take one turn for `agent`; return a short transcript of what it did."""
        ...


# ===========================================================================
# SCENE 2 — SCRIPTED TURNS
# ===========================================================================

class ScriptedBrain:
    """
    Plays a script: {agent: [turn, turn, ...]}, each turn a list of
    (tool_name, args) pairs. An agent with no turns left does nothing.
    `results` keeps every (agent, tool, args, result) for tests to inspect.
    """

    def __init__(self, script: dict[str, list[list[tuple[str, dict]]]]) -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.results: list[tuple[str, str, dict, str]] = []

    async def turn(self, agent: str, system: str, prompt: str,
                   tools: list[ToolSpec]) -> str:
        turns = self.script.get(agent) or []
        if not turns:
            return f"{agent}: (no scripted turn)"
        by_name = {t.name: t for t in tools}
        lines = []
        for name, args in turns.pop(0):
            if name not in by_name:
                result = f"(scripted call to unknown tool {name})"
            else:
                result = by_name[name].handler(args)
            self.results.append((agent, name, args, result))
            lines.append(f"{agent} → {name} {json.dumps(args, default=str)[:160]}\n   {result[:300]}")
        return "\n".join(lines)


# ===========================================================================
# SCENE 3 — A CLAUDE AGENT
# ===========================================================================

class ClaudeBrain:
    """
    A Claude agent per role, through the Claude Agent SDK.

    Enter:   model        model id (None: the SDK's default)
             max_turns    tool-use turns allowed per swarm turn
             max_budget   optional spend cap in USD per swarm turn
    Needs:   `pip install claude-agent-sdk`, the Claude Code CLI on PATH, and
             ANTHROPIC_API_KEY (or another credential the CLI accepts).
    """

    SERVER = "cclf"

    def __init__(self, model: Optional[str] = None, max_turns: int = 12,
                 max_budget: Optional[float] = None) -> None:
        self.model = model or os.environ.get("CCLF_SWARM_MODEL")
        self.max_turns = max_turns
        self.max_budget = max_budget
        self.sessions: dict[str, str] = {}
        self.cost_usd = 0.0
        # Identity persistence (Agent Admissibility) belongs to "models at a
        # fixed version": the models that actually answered are recorded.
        self.models_seen: set[str] = set()

    def build(self, agent: str, system: str, tools: list[ToolSpec]):
        """
        The Agent SDK options for one turn, and the SDK tools behind them.
        Built-in tools are off (tools=[]), only this agent's tools are
        allowed, local Claude settings are ignored, and the agent's session
        is resumed if it has one.
        """
        from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, tool

        def wrap(spec: ToolSpec):
            async def handler(args: dict) -> dict:
                return {"content": [{"type": "text", "text": spec.handler(args or {})}]}
            return tool(spec.name, spec.description, spec.schema)(handler)

        sdk_tools = [wrap(t) for t in tools]
        server = create_sdk_mcp_server(name=self.SERVER, tools=sdk_tools)
        options = ClaudeAgentOptions(
            system_prompt=system,
            mcp_servers={self.SERVER: server},
            tools=[],                                   # no built-in tools at all
            allowed_tools=[f"mcp__{self.SERVER}__{t.name}" for t in tools],
            max_turns=self.max_turns,
            max_budget_usd=self.max_budget,
            model=self.model,
            resume=self.sessions.get(agent),
            setting_sources=[],                         # ignore local Claude settings
        )
        return options, sdk_tools

    async def turn(self, agent: str, system: str, prompt: str,
                   tools: list[ToolSpec]) -> str:
        import claude_agent_sdk as sdk
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

        options, self.last_tools = self.build(agent, system, tools)
        query = sdk.query
        lines = []
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        lines.append(f"{agent}: {block.text.strip()[:400]}")
                    elif isinstance(block, ToolUseBlock):
                        lines.append(f"{agent} → {block.name.split('__')[-1]} "
                                     f"{json.dumps(block.input, default=str)[:160]}")
            elif isinstance(msg, ResultMessage):
                self.sessions[agent] = msg.session_id
                self.cost_usd += msg.total_cost_usd or 0.0
                self.models_seen.update((msg.model_usage or {}).keys())
                if not msg.model_usage and self.model:
                    self.models_seen.add(self.model)
        return "\n".join(lines)

# EXEUNT — end of file.

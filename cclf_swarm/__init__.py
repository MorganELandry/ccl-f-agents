"""
cclf_swarm — live agent swarms governed by the CCL-F v0.2 supervisor.

The supervisor (cclf/) holds every rule. This package adds the runtime that
stands between language-model agents and that supervisor, the brains that
drive the agents (Claude through the Agent SDK, or a script), the
orchestrator, and three worlds to work in. See docs/SWARM.md.
"""
from .runtime import (Runtime, RoleSpec, ToolSpec, HumanRequest, approve_all, deny_all,
                      console_approver, OBLIGATION_OPS)
from .brains import ClaudeBrain, ScriptedBrain
from .orchestrator import ClaudeOrchestrator, RoundRobin, Swarm

__all__ = ["Runtime", "RoleSpec", "ToolSpec", "HumanRequest", "approve_all", "deny_all",
           "console_approver", "OBLIGATION_OPS", "ClaudeBrain", "ScriptedBrain",
           "ClaudeOrchestrator", "RoundRobin", "Swarm"]

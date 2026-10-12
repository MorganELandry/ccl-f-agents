"""
THE WORLD INTERFACE
A Play in One Scene
===================

PROLOGUE
--------
A world is what the swarm works on: who the agents are, which instruments
exist, and what the irreversible effect is. Three ship with the package:

  simorg    the simulated org: simulated people deciding whether to launch, with a
            hidden ground truth, so a run can be scored.
  release   real work on a git repository; publishing a release is the
            irreversible step.
  odoo      agents review Odoo invoices; posting them is the
            irreversible step (dry-run unless told otherwise).

A world never decides whether something may execute. The supervisor does;
the runtime calls execute() only after a permitted gate (or in a baseline
run with gating off).
"""

from __future__ import annotations

from typing import Iterable

from ..runtime import RoleSpec, Runtime, ToolSpec


class World:
    name = "world"
    # Only a simulated world may run with the gate off (the baseline).
    allows_baseline = False

    def roles(self) -> list[RoleSpec]:
        """The agents, in the order RoundRobin runs them."""
        raise NotImplementedError

    def setup(self, rt: Runtime) -> None:
        """Register architecture, instruments and reporting lines; seed inboxes."""

    def context(self) -> str:
        """The situation, as every agent's system prompt states it."""
        return ""

    def goal(self) -> str:
        """What the team is trying to achieve, for the orchestrator."""
        return self.context()

    def tools(self, rt: Runtime, agent: str) -> Iterable[ToolSpec]:
        """Instruments and domain tools for one agent."""
        return []

    def closure_authority(self, agent: str, signal_args: dict) -> tuple:
        """
        Who may close a signal, from the world's architecture (never the
        registering agent's choice). Empty means no registered boundary.
        """
        return ()

    def open_signals_text(self, rt: Runtime) -> str:
        """The open signals, for a person approving a decision (Rule 1)."""
        open_ = [s for s in rt.sup.signals.values() if s.is_open]
        if not open_:
            return "open signals: none"
        return "open signals:\n" + "\n".join(
            f"  {s.signal_id} [{s.signal_type.value}, {s.state.value}] {s.description[:120]}"
            for s in open_)

    def principal_for(self, agent: str, op: str):
        """The person who answers ask_human for this op, or None for the role's principal."""
        return None

    def after_op(self, rt: Runtime, op: str, args: dict, actor: str) -> None:
        """Called after every supervisor operation that succeeded (e.g. to pin
        what an acceptance was given on)."""

    def precheck(self, rt: Runtime, decision_id: str):
        """
        The world's own preconditions on its effect, checked before the
        supervisor's gate runs (so a refusal here leaves nothing marked
        executed). Return a reason to hold, or None.
        """
        return None

    def describe(self, rt: Runtime, decision_id: str) -> str:
        """What the decision would actually do, shown to the approving person."""
        return ""

    def execute(self, rt: Runtime, decision_id: str, gate) -> str:
        """Perform the irreversible effect. Called only by the runtime."""
        raise NotImplementedError

    def done(self, rt: Runtime) -> bool:
        return False

    def report(self, rt: Runtime) -> dict:
        return {}


def text_arg(schema_props: dict, required: list[str]) -> dict:
    """A small JSON Schema helper."""
    return {"type": "object", "properties": schema_props, "required": required}

# EXEUNT — end of file.

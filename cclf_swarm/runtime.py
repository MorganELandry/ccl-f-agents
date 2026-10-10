"""
THE SWARM RUNTIME
A Play in Seven Scenes
======================

PROLOGUE
--------
The runtime is the only door between a swarm of language-model agents and
the CCL-F supervisor. An agent never holds the supervisor; it holds tools,
and every tool goes through this file.

    agent (Claude, or a script)
        │  tool call
        ▼
    Runtime.act()  ── role allowlist ── identity binding ── evidence rule
        │
        ▼
    Supervisor (cclf/supervisor.py)  — every rule, unchanged
        │  GateResult on request_execution
        ▼
    World.execute()  — the irreversible effect, ONLY when the gate permits

The supervisor already enforces CCL-F v0.2. This file adds the guardrails
that only matter once the actors are models:

  1. Role allowlist      an agent may call only the supervisor operations
                         its role lists; structural set-up (architecture,
                         agents, grants) is the world's, never an agent's.
  2. Identity binding    the acting-agent field ("by" or "registered_by")
                         is overwritten with the caller's own name, so no
                         agent can act as another.
  3. Evidence rule       evidence an agent writes is registered as
                         MODEL_OUTPUT produced by that agent. Only a
                         world's instruments (a test lab, pytest, an Odoo
                         record read) mint evidence of an EES-eligible
                         kind. This is the draft's "multiple LLM
                         instances ... do not constitute independent
                         evidence", made structural.
  4. Obligation routing  an agent registered as AUTOMATION cannot accept a
                         decision, resolve a review, attest risk evidence,
                         override or give an Emergency Justification. It
                         may ask its human principal (ask_human); if the
                         person approves, the act is performed under the
                         person's name.
  5. Execution latch     the world's irreversible effect runs only from
                         here, only after a permitted GateResult, and only
                         once per decision. An agent has no tool that
                         causes it directly.

  6. Stewardship and closure authority are the world's, not the agent's.
     A signal's steward and successor must be agents the world registered
     with obligation capacity (no model can assign an obligation to a
     person who never accepted it), and closure authority is set from the
     world's architecture, whatever the agent passes (Layer 3, Autonomy-
     Bounded Closure: "a structural property ... not a judgment").
  7. The runtime's own acts go into the supervisor's hash-chained trail as
     RUNTIME_* entries: a precheck hold, an ungated baseline execution, an
     effect's outcome, an act a person performed at an agent's request,
     the orchestrator's schedule, and the loops left open when a run ends.

Gating can be switched off (gating=False) to run the same swarm as a
baseline: the supervisor still records everything, but the effect runs
whatever the gate says. Only a world that declares allows_baseline (the
simulated org) may do this; a world with a real effect refuses it.
See docs/DECISIONS.md, "Swarm", for every choice made here.

THE PLAYBILL
    Scene 1  RoleSpec, ToolSpec, HumanRequest, Record   the records
    Scene 2  Runtime.__init__()                         wiring and set-up
    Scene 3  Runtime.setup_op() / mint_evidence()       world-only doors
    Scene 4  Runtime.act()                              the agent's door
    Scene 5  Runtime._perform() / _after_gate()         calling the supervisor
    Scene 6  ask_human(), messages, status()            the other agent tools
    Scene 7  tools_for()                                the tool list an agent gets
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from cclf.graph import _architecture, _coerce
from cclf.supervisor import GateResult, Supervisor, TransitionRefused
from cclf.types import AgentKind, EvidenceKind


# ===========================================================================
# DRAMATIS PERSONAE
# ===========================================================================

# Operations that create an obligation (Layer 0, Agent Admissibility).
OBLIGATION_OPS = frozenset({"accept_decision", "resolve_review", "attest_risk_evidence"})

# Structural set-up: the world's to perform, never an agent's.
STRUCTURAL_OPS = frozenset({
    "register_architecture", "register_agent", "register_reporting_line",
    "grant", "revoke", "assign_scope",
})

# Agent kinds with obligation capacity (a ROLE also needs a successor;
# the supervisor checks that itself).
CAPABLE_KINDS = frozenset({AgentKind.PERSON, AgentKind.UNIT, AgentKind.ROLE})

# Keep tool results readable for a model.
MAX_RESULT_CHARS = 6000


# ===========================================================================
# SCENE 1 — THE RECORDS
# ===========================================================================

@dataclass(frozen=True)
class RoleSpec:
    """
    One agent in a world.

      name        the agent's name; also its identity in the audit trail
      title       a short human label ("Propulsion engineer")
      brief       the role's instructions, placed in its system prompt
      ops         the supervisor operations this role may call
      kind        PERSON for a simulated person (simulated-org world);
                  AUTOMATION for a model doing real work
      principal   the person who answers this agent's ask_human, if any
      asks        the obligation-creating acts this agent may ASK a person
                  for (accept_decision, attest_risk_evidence, resolve_review,
                  request_execution meaning an override or emergency). An
                  agent with none gets no ask_human tool.
    """
    name: str
    title: str
    brief: str
    ops: frozenset
    kind: AgentKind = AgentKind.AUTOMATION
    principal: Optional[str] = None
    asks: frozenset = frozenset()


@dataclass
class ToolSpec:
    """
    A tool, independent of any agent framework.

      name, description   what the model sees
      schema              JSON Schema for the arguments
      handler             args dict -> result text (synchronous)
    """
    name: str
    description: str
    schema: dict
    handler: Callable[[dict], str]


@dataclass
class HumanRequest:
    """
    What an agent asks a person to do, and why. `context` is the world's own
    description of what the decision would actually do (the invoices in the
    batch, the tree hash and test verdict of the release), so the person
    approves the effect, not just the agent's summary of it.
    """
    agent: str
    principal: str
    op: str
    args: dict
    rationale: str
    context: str = ""


# An approver answers a HumanRequest: (approved, note).
Approver = Callable[[HumanRequest], "tuple[bool, str]"]


def deny_all(req: HumanRequest) -> tuple[bool, str]:
    """The default approver: no person is listening, so nothing is approved."""
    return False, "no approver configured"


def approve_all(req: HumanRequest) -> tuple[bool, str]:
    """For tests and demos only: approve every request."""
    return True, "approved (approve_all)"


def console_approver(req: HumanRequest) -> tuple[bool, str]:
    """Ask the person at the terminal."""
    print(f"\n=== {req.agent} asks {req.principal} to: {req.op}")
    print(json.dumps(req.args, indent=2, default=str))
    print(f"Rationale: {req.rationale}")
    if req.context:
        print(f"What it would do (from the world, not the agent):\n{req.context}")
    answer = input("Approve? [y/N] and an optional note: ").strip()
    return answer[:1].lower() == "y", answer[1:].strip() or "(no note)"


@dataclass
class Record:
    """One tool call, as the runtime saw it."""
    step: int
    agent: str
    tool: str
    args: dict
    result: str
    refused: bool


# ===========================================================================
# SCENE 2 — THE RUNTIME
# ===========================================================================

class Runtime:
    """
    Holds the supervisor, the world, the roster and the record of the run.

    Enter:   world        a World (cclf_swarm/worlds/base.py)
             supervisor   a Supervisor; a fresh one if None
             gating       True: the world's effect runs only on a permitted
                          gate. False: the baseline, where it runs anyway.
             approver     answers ask_human; deny_all if None
    """

    def __init__(self, world, supervisor: Optional[Supervisor] = None,
                 gating: bool = True, approver: Optional[Approver] = None) -> None:
        if not gating and not getattr(world, "allows_baseline", False):
            raise ValueError(f"the {world.name} world has a real effect; a run with the gate "
                             "off is allowed only in a simulated world")
        self.world = world
        self.sup = supervisor or Supervisor()
        self.gating = gating
        self._minted: dict = {}
        self.approver = approver or deny_all
        self.roles: dict[str, RoleSpec] = {r.name: r for r in world.roles()}
        self.inbox: dict[str, list[str]] = {name: [] for name in self.roles}
        self.log: list[Record] = []
        self.executions: list[dict] = []
        self.human_requests: list[dict] = []
        self.step = 0
        for role in self.roles.values():
            self.setup_op("register_agent", agent=role.name, agent_kind=role.kind,
                          by=world.name)
        world.setup(self)

    # =======================================================================
    # SCENE 3 — THE WORLD'S OWN DOORS
    # =======================================================================

    def setup_op(self, op: str, **args) -> Any:
        """
        Perform a supervisor operation as the world, with no agent checks.
        Used for structural set-up (architecture, agents, reporting lines).
        A refusal here is a bug in the world, so it raises.
        """
        if op == "register_architecture":
            by = args.pop("by")
            return self.sup.register_architecture(_architecture(args), by)
        return getattr(self.sup, op)(**_coerce(args))

    def audit(self, event: str, actor: str, **payload) -> None:
        """
        Append a runtime entry to the supervisor's hash-chained audit trail
        (stamped with the supervisor's clock, through AuditTrail's public
        append), so what the runtime did is in the same immutable record as
        what the supervisor did.
        """
        self.sup.audit.append(self.sup.clock, event, actor, payload)

    def mint_evidence(self, evidence_id: str, content: str, source: str, kind: str,
                      produced_by: str, relayed_by: str, signal_ids=(),
                      depends_on=(), key=None) -> str:
        """
        Register evidence produced by an instrument (not by a model).

        Only world tools call this. `produced_by` is the instrument, which
        is what lets the evidence pass the External Evidence Source test
        for a closure some agent claims; `relayed_by` is the agent that ran
        the instrument and is recorded as the one who added it.

        `key` identifies the measurement (instrument and input). Repeating a
        measurement with the same key returns the earlier evidence instead
        of minting a "new" item: a re-run of the same deterministic test is
        not new evidence (Layer 2, Evidence Novelty).
        """
        if key is not None and key in self._minted:
            earlier = self._minted[key]
            return (f"same measurement as {earlier} (instrument and input unchanged); no new "
                    f"evidence was registered. Cite {earlier}.")
        try:
            self.sup.add_evidence(evidence_id, content, source, EvidenceKind(kind),
                                  produced_by, relayed_by, tuple(signal_ids), tuple(depends_on))
        except (TransitionRefused, KeyError, ValueError) as exc:
            return f"evidence not registered: {exc}"
        if key is not None:
            self._minted[key] = evidence_id
        return (f"evidence {evidence_id} registered ({kind}, produced by {produced_by}); "
                f"cite it by id in a closure, classification or acceptance")

    # =======================================================================
    # SCENE 4 — THE AGENT'S DOOR
    # =======================================================================

    def act(self, agent: str, op: str, args: Optional[dict] = None) -> str:
        """
        Perform one supervisor operation for an agent, under every guardrail.

        Enter:   agent   the calling agent's name
                 op      a Supervisor method name
                 args    its keyword arguments (the acting-agent field is
                         ignored and replaced)
        Exit:    result text for the model. Refusals start with "REFUSED".
        """
        role = self.roles[agent]
        args = dict(args or {})
        args.pop("note", None)
        if op.startswith("_") or op in STRUCTURAL_OPS:
            return self._record(agent, op, args, f"REFUSED: {op} is world set-up, not an "
                                                  f"agent operation", True)
        if op not in role.ops:
            return self._record(agent, op, args, f"REFUSED: the {role.title} role may not "
                                                  f"perform {op}. Allowed: "
                                                  f"{', '.join(sorted(role.ops))}", True)
        obligation = op in OBLIGATION_OPS or (
            op == "request_execution" and (args.get("override_rationale") is not None
                                           or args.get("emergency") is not None))
        if obligation and role.kind not in CAPABLE_KINDS:
            hint = (f" Use ask_human to ask {role.principal}." if role.principal
                    else " No person is assigned to this agent.")
            return self._record(agent, op, args, f"REFUSED: {op} creates an obligation and "
                                                  f"{agent} is automation (Agent "
                                                  f"Admissibility).{hint}", True)
        if op == "register_signal":
            for field_ in ("steward", "successor"):
                who = args.get(field_)
                if who is not None and self.sup.agent_kinds.get(who) not in CAPABLE_KINDS:
                    return self._record(agent, op, args, f"REFUSED: {field_} {who!r} is not an "
                                        "agent this world registered with obligation capacity. "
                                        "Registered: " + ", ".join(sorted(
                                            a for a, k in self.sup.agent_kinds.items()
                                            if k in CAPABLE_KINDS)), True)
            args["closure_authority"] = list(self.world.closure_authority(agent, args))
        if op == "add_evidence":
            # The evidence rule: what a model writes is model output.
            args["produced_by"] = agent
            args["kind"] = EvidenceKind.MODEL_OUTPUT.value
        return self._perform(agent, op, args, caller=agent)

    # =======================================================================
    # SCENE 5 — CALLING THE SUPERVISOR
    # =======================================================================

    def _perform(self, actor: str, op: str, args: dict, caller: str) -> str:
        """Bind identity, call the supervisor, and turn the outcome into text."""
        method = getattr(self.sup, op, None)
        if method is None or not callable(method):
            return self._record(caller, op, args, f"REFUSED: unknown operation {op!r}", True)
        params = inspect.signature(method).parameters
        if "registered_by" in params:
            args["registered_by"] = actor
        elif "by" in params:
            args["by"] = actor
        unknown = set(args) - set(params)
        if unknown:
            return self._record(caller, op, args, f"REFUSED: {op} has no parameter(s) "
                                                  f"{', '.join(sorted(unknown))}. Parameters: "
                                                  f"{', '.join(params)}", True)
        bad = _type_errors(params, args)
        if bad:
            return self._record(caller, op, args, f"REFUSED: bad arguments for {op}: "
                                                  f"{'; '.join(bad)}", True)
        if op == "request_execution":
            did = args.get("decision_id")
            if any(x["decision_id"] == did and x["executed"] for x in self.executions):
                return self._record(caller, op, args, f"REFUSED: {did} has already executed", True)
            # The world's own preconditions on its effect, checked BEFORE the
            # supervisor marks anything executed (e.g. the release tree has not
            # changed since its tests ran; a pushed release is gated as
            # irreversible; the Odoo batch is the one that was accepted).
            reason = did in self.sup.decisions and self.world.precheck(self, did)
            if reason:
                # Recorded in the chained trail, and marked as a blocked request,
                # so a later lowering of the decision's class escalates exactly
                # as it would after a gate refusal (Layer 4, Execution Gates).
                self.sup.decisions[did].ever_blocked = True
                self.audit("RUNTIME_PRECHECK_HELD", actor, decision_id=did, reason=reason)
                return self._record(caller, op, args, f"HELD by the world before the gate: "
                                                      f"{reason}", True)
        try:
            result = method(**_coerce(args))
        except TransitionRefused as exc:
            return self._record(caller, op, args, f"REFUSED by the supervisor: {exc}", True)
        except (TypeError, ValueError, KeyError) as exc:
            return self._record(caller, op, args, f"REFUSED: bad arguments for {op}: {exc}", True)
        except Exception as exc:                       # never let one call end the run
            return self._record(caller, op, args, f"REFUSED: {op} failed: "
                                                  f"{type(exc).__name__}: {exc}", True)
        if op == "request_execution":
            text, refused = self._after_gate(actor, args["decision_id"], result)
            return self._record(caller, op, args, text, refused)
        self.world.after_op(self, op, args, actor)
        return self._record(caller, op, args, f"{op} ok{_describe(result)}", False)

    def _after_gate(self, actor: str, decision_id: str, gate: GateResult) -> tuple[str, bool]:
        """Run the world's effect if the gate permits (or gating is off)."""
        failures = "".join(f"\n  - {f}" for f in gate.failures)
        if gate.permitted or not self.gating:
            try:
                effect = self.world.execute(self, decision_id, gate)
            except Exception as exc:
                # The supervisor has recorded the decision as executed; the effect
                # did not happen. Say so plainly and keep the record honest.
                effect = f"EFFECT FAILED: {type(exc).__name__}: {exc}"
            if gate.permitted:
                self.audit("RUNTIME_EFFECT", actor, decision_id=decision_id, effect=effect,
                           failed=effect.startswith("EFFECT FAILED"))
            else:
                # The baseline: the supervisor logged a refusal and left the
                # decision unexecuted; the effect happened anyway. The trail says so.
                self.audit("RUNTIME_UNGATED_EXECUTION", actor, decision_id=decision_id,
                           failures=list(gate.failures), effect=effect,
                           note="baseline run with gating off; not a CCL-F authorization")
            self.executions.append({"decision_id": decision_id, "executed": True,
                                    "permitted": gate.permitted, "gated": self.gating,
                                    "overridden": gate.overridden, "by": actor,
                                    "failures": list(gate.failures), "effect": effect})
            how = ("by override" if gate.overridden else "under an Emergency Justification"
                   if gate.emergency_id else "cleanly")
            if not gate.permitted:
                return (f"EXECUTED WITHOUT A GATE (baseline run): {decision_id}. The gate "
                        f"would have refused:{failures}\nEffect: {effect}", False)
            return f"EXECUTED {how}: {decision_id}. Effect: {effect}", False
        self.executions.append({"decision_id": decision_id, "executed": False,
                                "permitted": False, "gated": True, "overridden": False,
                                "by": actor, "failures": list(gate.failures), "effect": None})
        return (f"HELD: the gate refused {decision_id} ({gate.execution_class.value}, "
                f"coherence {gate.coherence:.2f}). Unmet:{failures}", True)

    def _record(self, agent: str, tool: str, args: dict, text: str, refused: bool) -> str:
        self.step += 1
        self.log.append(Record(self.step, agent, tool, dict(args), text, refused))
        return text[:MAX_RESULT_CHARS]

    # =======================================================================
    # SCENE 6 — THE OTHER AGENT TOOLS
    # =======================================================================

    def ask_human(self, agent: str, op: str, args: dict, rationale: str) -> str:
        """
        Ask a person to perform an obligation-creating act: the world's
        principal_for(agent, op) if it names one (a world may send risk
        attestation to a second person, since the acceptor cannot attest),
        else the role's principal.
        If approved, the act is performed under the principal's name and
        still goes through every supervisor rule.
        """
        role = self.roles[agent]
        args = dict(args or {})
        principal = self.world.principal_for(agent, op) or role.principal
        if op not in role.asks:
            return self._record(agent, "ask_human", {"op": op, **args}, f"REFUSED: the "
                                f"{role.title} role may not ask for {op}. It may ask for: "
                                f"{', '.join(sorted(role.asks)) or 'nothing'}", True)
        override = args.get("override_rationale")
        if op == "request_execution" and not (isinstance(override, str) and override.strip()) \
                and args.get("emergency") is None:
            return self._record(agent, "ask_human", {"op": op, **args}, "REFUSED: ask a person "
                                "for request_execution only with an override_rationale or "
                                "an emergency; a plain request you make yourself", True)
        if not principal:
            return self._record(agent, "ask_human", {"op": op}, "REFUSED: no person is "
                                f"assigned to answer {op} for this agent", True)
        method = getattr(self.sup, op)
        params = inspect.signature(method).parameters
        problems = [f"no parameter {k}" for k in args if k not in params] + \
            _type_errors(params, {k: v for k, v in args.items() if k in params})
        if problems:
            return self._record(agent, "ask_human", {"op": op, **args}, f"REFUSED: bad "
                                f"arguments for {op}: {'; '.join(problems)}", True)
        did = args.get("decision_id")
        context = self.world.describe(self, did) if did else ""
        req = HumanRequest(agent, principal, op, args, rationale, context)
        approved, note = self.approver(req)
        self.human_requests.append({"agent": agent, "principal": principal, "op": op,
                                    "args": dict(args), "context": context,
                                    "approved": approved, "note": note})
        if not approved:
            return self._record(agent, "ask_human", {"op": op, **args},
                                f"DECLINED by {principal}: {note}", True)
        # The person performs the act; the trail also records who asked for it,
        # why, and what the person was shown (accountability for the origin).
        self.audit("RUNTIME_ACT_VIA_PERSON", principal, op=op, requested_by=agent,
                   rationale=rationale, note=note, shown=context[:2000])
        result = self._perform(principal, op, dict(args), caller=agent)
        return f"{principal} approved ({note}). {result}"

    def send_message(self, agent: str, to: str, text: str) -> str:
        if to not in self.inbox:
            return self._record(agent, "send_message", {"to": to}, f"REFUSED: no agent {to!r}. "
                                f"Agents: {', '.join(self.inbox)}", True)
        self.inbox[to].append(f"from {agent}: {text}")
        return self._record(agent, "send_message", {"to": to, "text": text}, "sent", False)

    def read_inbox(self, agent: str) -> str:
        msgs, self.inbox[agent] = self.inbox[agent], []
        return "\n".join(msgs) if msgs else "(no messages)"

    def status(self) -> str:
        """A compact, read-only view of the supervisor's state."""
        sup = self.sup
        view = {
            "signals": [{"id": s.signal_id, "type": s.signal_type.value, "state": s.state.value,
                         "operational_state": getattr(s.operational_state, "value", None),
                         "steward": s.steward, "registered_by": s.registered_by,
                         "evidence": list(s.evidence_ids)} for s in sup.signals.values()],
            "evidence": [{"id": e.evidence_id, "kind": e.kind.value, "produced_by": e.produced_by,
                          "content": str(e.content)[:160]} for e in sup.evidence.values()],
            "decisions": [{"id": d.decision_id, "class": d.execution_class.value,
                           "signals": list(d.signal_ids), "accepted_by": d.accepted_by,
                           "risk_claim": d.risk_claim, "executed": d.executed,
                           "coherence": round(sup.coherence(d.decision_id)[0], 2)}
                          for d in sup.decisions.values()],
            "open_reviews": [{"id": r.review_id, "condition": getattr(r.condition, "value",
                                                                       str(r.condition)),
                              "signals": list(r.signal_ids), "decision": r.decision_id,
                              "detail": str(r.detail)[:200]} for r in sup.open_reviews()],
            "executions": [{k: x[k] for k in ("decision_id", "executed", "permitted")}
                           for x in self.executions],
        }
        return json.dumps(view, indent=1, default=str)

    # =======================================================================
    # SCENE 7 — THE TOOL LIST AN AGENT GETS
    # =======================================================================

    def tools_for(self, agent: str) -> list[ToolSpec]:
        """The core CCL-F tools for this agent plus its world's tools."""
        role = self.roles[agent]
        cheat = "\n".join(f"  {op}({_params(getattr(self.sup, op))})" for op in sorted(role.ops))
        tools = [
            ToolSpec(
                "ccl_act",
                "Perform one CCL-F supervisor operation. Your name is filled in as the "
                "acting agent automatically. Lists go in as JSON arrays; enum values as "
                "lowercase strings (e.g. signal_type 'constraint', state "
                "'elevated_uncertainty', execution_class 'irreversible'). Operations you "
                f"may call, with parameters:\n{cheat}",
                {"type": "object", "properties": {
                    "op": {"type": "string", "enum": sorted(role.ops)},
                    "args": {"type": "object", "description": "keyword arguments"}},
                 "required": ["op", "args"]},
                lambda a, _n=agent: self.act(_n, a["op"], a.get("args") or {})),
            ToolSpec("ccl_status", "Read the current signals, evidence, decisions, open "
                     "reviews and executions. Read-only.",
                     {"type": "object", "properties": {}}, lambda a: self.status()),
            ToolSpec("send_message", "Send a message to another agent. Agents: "
                     + ", ".join(n for n in self.roles if n != agent),
                     {"type": "object", "properties": {"to": {"type": "string"},
                                                       "text": {"type": "string"}},
                      "required": ["to", "text"]},
                     lambda a, _n=agent: self.send_message(_n, a["to"], a["text"])),
            ToolSpec("read_inbox", "Read and clear your messages.",
                     {"type": "object", "properties": {}},
                     lambda a, _n=agent: self.read_inbox(_n)),
        ]
        if role.asks and role.principal:
            tools.append(ToolSpec(
                "ask_human",
                f"Ask a person ({role.principal}, or whoever the world assigns for that act) "
                f"to perform an act you are not allowed to: {', '.join(sorted(role.asks))}"
                + (" (request_execution only with an override_rationale or emergency)"
                   if "request_execution" in role.asks else "")
                + ". They see what the decision would actually do. If they approve, it is "
                "done in their name and the supervisor still applies every rule.",
                {"type": "object", "properties": {
                    "op": {"type": "string"}, "args": {"type": "object"},
                    "rationale": {"type": "string"}}, "required": ["op", "args", "rationale"]},
                lambda a, _n=agent: self.ask_human(_n, a["op"], a.get("args") or {},
                                                   a.get("rationale", ""))))
        return tools + [self._logged(agent, t) for t in self.world.tools(self, agent)]

    def _logged(self, agent: str, spec: ToolSpec) -> ToolSpec:
        """Record every world-tool call in the run log, like the CCL-F tools."""
        def handler(args, _h=spec.handler, _name=spec.name):
            try:
                text = str(_h(args or {}))
            except Exception as exc:                   # bad argument types, client faults
                text = f"REFUSED: {_name} failed: {type(exc).__name__}: {exc}"
            self._record(agent, _name, dict(args or {}), text, text.startswith("REFUSED"))
            return text[:MAX_RESULT_CHARS * 2]
        return ToolSpec(spec.name, spec.description, spec.schema, handler)

    # -----------------------------------------------------------------------
    def metrics(self) -> dict:
        """Counts for comparing runs."""
        refusals = [r for r in self.log if r.refused]
        return {
            "tool_calls": len(self.log),
            "refusals": len(refusals),
            "supervisor_refusals": sum(r.result.startswith("REFUSED by the supervisor")
                                       for r in refusals),
            "holds": sum(1 for x in self.executions if not x["executed"]),
            "executions": [x["decision_id"] for x in self.executions if x["executed"]],
            "ungated_executions": [x["decision_id"] for x in self.executions
                                   if x["executed"] and not x["permitted"]],
            "overrides": sum(1 for x in self.executions if x["overridden"]),
            "human_requests": len(self.human_requests),
            "human_approvals": sum(1 for h in self.human_requests if h["approved"]),
            "open_reviews": len(self.sup.open_reviews()),
            "audit_entries": len(self.sup.audit),
            "audit_verified": self.sup.audit.verify(self.sup.audit.entries(),
                                                    self.sup.audit.head())[0],
        }


_ENUM_KEYS = frozenset({"signal_type", "referent", "state", "kind", "execution_class",
                        "exit_type", "legal_subtype", "agent_kind"})
_COLLECTION_HINTS = ("Sequence", "Iterable", "list", "tuple", "Collection", "set", "frozenset")


def _type_errors(params, args: dict) -> list[str]:
    """
    Check each argument against its parameter's annotation before the
    supervisor sees it. Models send JSON, so the check is on JSON shapes:
    collections must be lists of strings, enum fields strings, text fields
    strings, flags booleans; only `emergency` may be an object. A value that
    slipped through would otherwise be stored and break later reads.
    """
    errors = []
    for key, value in args.items():
        p = params[key]
        ann = str(p.annotation)
        if value is None:
            if p.default is inspect.Parameter.empty and "Optional" not in ann \
                    and "None" not in ann:
                errors.append(f"{key} may not be null")
            continue
        if key == "emergency":
            if not isinstance(value, dict):
                errors.append("emergency must be an object")
        elif key in _ENUM_KEYS:
            if not isinstance(value, str):
                errors.append(f"{key} must be a string")
        elif isinstance(value, dict):
            errors.append(f"{key} may not be an object")
        elif any(h in ann for h in _COLLECTION_HINTS):
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                errors.append(f"{key} must be a list of strings")
        elif "bool" in ann:
            if not isinstance(value, bool):
                errors.append(f"{key} must be true or false")
        elif "float" in ann or "int" in ann:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{key} must be a number")
        elif "str" in ann:
            if not isinstance(value, str):
                errors.append(f"{key} must be a string")
        elif isinstance(value, list):
            errors.append(f"{key} may not be a list")
    return errors


def _params(method) -> str:
    """'a, b=None, ...' without the acting-agent field."""
    out = []
    for name, p in inspect.signature(method).parameters.items():
        if name in ("by", "registered_by", "self"):
            continue
        out.append(name if p.default is inspect.Parameter.empty else f"{name}=…")
    return ", ".join(out)


def _describe(result: Any) -> str:
    if result is None:
        return ""
    value = getattr(result, "value", None)
    if value is not None:
        return f": {value}"
    for attr in ("closure_type", "signal_id", "decision_id", "evidence_id"):
        if hasattr(result, attr):
            v = getattr(result, attr)
            return f": {attr}={getattr(v, 'value', v)}"
    return ""

# EXEUNT — end of file.

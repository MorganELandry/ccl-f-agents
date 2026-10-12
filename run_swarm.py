"""
THE SWARM, LIVE
A Play in Four Scenes
=====================

PROLOGUE
--------
Run a swarm of agents in one of the three worlds, governed by the CCL-F
supervisor.

  # Simulated org: offline baseline scripts, no key needed
  python run_swarm.py simorg --brain scripted --script diligent --no-defect
  python run_swarm.py simorg --brain scripted --script pressured --defect
  python run_swarm.py simorg --brain scripted --script pressured --defect --no-gate

  # Simulated org with Claude agents (needs ANTHROPIC_API_KEY and the Claude Code CLI)
  python run_swarm.py simorg --brain claude --seed 3
  python run_swarm.py simorg --brain claude --compare --seeds 6   # gate on vs off

  # Governed release on a git repo (you approve at the terminal)
  python run_swarm.py release --demo --brain scripted --approve-all
  python run_swarm.py release --repo ../myproj --task "fix issue 12" --version v0.4.1 --brain claude

  # Odoo invoice world (offline fake by default; --live uses ODOO_* env vars;
  # --post actually posts, and only with --live)
  python run_swarm.py odoo --brain scripted --attester bookkeeper --approve-all
  python run_swarm.py odoo --brain claude --live --attester bookkeeper

THE PLAYBILL
    Scene 1  build_world()
    Scene 2  build_brains()
    Scene 3  run_once() and compare()
    Scene 4  main()
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import tempfile
from collections import Counter

from cclf_swarm import (ClaudeBrain, ClaudeOrchestrator, RoundRobin, Runtime, ScriptedBrain,
                        Swarm, approve_all, console_approver)
from cclf_swarm import scripts
from cclf_swarm.worlds import GitRelease, OdooClient, OdooReview, SimOrg


DEMO_BUG = "def add(a, b):\n    return a - b\n"
DEMO_FIX = "def add(a, b):\n    return a + b\n"
DEMO_TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


# ===========================================================================
# SCENE 1 — THE WORLD
# ===========================================================================

def _demo_repo() -> str:
    d = tempfile.mkdtemp(prefix="cclf-release-demo-")
    git = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
    git("init", "-q")
    open(f"{d}/calc.py", "w").write(DEMO_BUG)
    open(f"{d}/test_calc.py", "w").write(DEMO_TEST)
    git("add", "-A")
    git("-c", "user.name=demo", "-c", "user.email=demo@local", "commit", "-qm", "initial")
    return d


def build_world(args, seed: int | None = None):
    if args.world == "simorg":
        defect = None if args.defect is None else args.defect
        return SimOrg(defect=defect, pressure=args.pressure,
                      seed=args.seed if seed is None else seed)
    if args.world == "release":
        repo = _demo_repo() if args.demo else args.repo
        if not repo:
            raise SystemExit("release needs --repo PATH (or --demo)")
        task = args.task or ("make the test pass: add() subtracts" if args.demo else None)
        if not task:
            raise SystemExit("release needs --task")
        return GitRelease(repo, task, version=args.version, test_command=args.test_command,
                          second_reviewer=args.second_reviewer, push=args.push,
                          allow_test_edits=args.allow_test_edits)
    if args.post and not args.live:
        raise SystemExit("--post only makes sense with --live")
    client = OdooClient.from_env() if args.live else None
    return OdooReview(client=client, attester=args.attester, dry_run=not args.post)


# ===========================================================================
# SCENE 2 — THE BRAINS
# ===========================================================================

def build_brains(args, world):
    if args.brain == "claude":
        return ClaudeBrain(model=args.model, max_turns=args.max_turns,
                           max_budget=args.budget_per_turn)
    if args.world == "simorg":
        script = (scripts.simorg_diligent() if args.script == "diligent"
                  else scripts.simorg_pressured())
    elif args.world == "release":
        if not args.demo:
            raise SystemExit("the scripted release brain only runs the --demo repository")
        script = scripts.release_fix("calc.py", DEMO_FIX)
    else:
        script = scripts.odoo_month_end(include_bad=args.include_bad)
    return ScriptedBrain(script)


# ===========================================================================
# SCENE 3 — ONE RUN, OR A COMPARISON
# ===========================================================================

async def run_once(args, world, gating: bool, quiet: bool) -> tuple[dict, Runtime]:
    approver = approve_all if args.approve_all else console_approver
    rt = Runtime(world, gating=gating, approver=approver)
    scheduler = ClaudeOrchestrator(model=args.model) if args.orchestrator == "claude" \
        else RoundRobin()
    show = None if quiet else (lambda agent, text: print(f"\n--- {agent}\n{text}"))
    out = await Swarm(rt, build_brains(args, world), scheduler, args.rounds, show).run()
    return out, rt


async def compare(args) -> dict:
    """The experiment: the same team, gate on and gate off, across seeds."""
    table = {True: Counter(), False: Counter()}
    for seed in range(args.seeds):
        for gating in (True, False):
            out, _ = await run_once(args, build_world(args, seed=seed), gating, quiet=True)
            table[gating][out["report"]["outcome"]] += 1
            print(f"seed {seed} gate={'on ' if gating else 'off'} defect="
                  f"{out['report']['defect']!s:5} → {out['report']['outcome']}")
    return {"gate_on": dict(table[True]), "gate_off": dict(table[False])}


# ===========================================================================
# SCENE 4 — MAIN
# ===========================================================================

def main() -> None:
    p = argparse.ArgumentParser(description="Run a CCL-F-governed agent swarm.")
    p.add_argument("world", choices=["simorg", "release", "odoo"])
    p.add_argument("--brain", choices=["scripted", "claude"], default="scripted")
    p.add_argument("--model", default=None, help="model id for Claude agents")
    p.add_argument("--orchestrator", choices=["roundrobin", "claude"], default="roundrobin")
    p.add_argument("--rounds", type=int, default=6)
    p.add_argument("--max-turns", type=int, default=12, help="tool turns per agent turn")
    p.add_argument("--budget-per-turn", type=float, default=None, help="USD cap per turn")
    p.add_argument("--no-gate", action="store_true", help="baseline: execute regardless")
    p.add_argument("--approve-all", action="store_true",
                   help="approve every ask_human request (demos only)")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--out", default="swarm_run.json", help="where to write the run record")
    g = p.add_argument_group("simorg")
    g.add_argument("--defect", dest="defect", action="store_true", default=None)
    g.add_argument("--no-defect", dest="defect", action="store_false")
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--pressure", choices=["normal", "high"], default="high")
    g.add_argument("--script", choices=["diligent", "pressured"], default="pressured")
    g.add_argument("--compare", action="store_true", help="gate on vs off across seeds")
    g.add_argument("--seeds", type=int, default=4)
    g = p.add_argument_group("release")
    g.add_argument("--repo")
    g.add_argument("--task")
    g.add_argument("--version", default="v0.0.1")
    g.add_argument("--test-command", default="python -m pytest -q")
    g.add_argument("--second-reviewer", default=None)
    g.add_argument("--push", action="store_true", help="push on release (irreversible)")
    g.add_argument("--demo", action="store_true", help="use a throwaway repo with one bug")
    g.add_argument("--allow-test-edits", action="store_true",
                   help="let the developer edit tests and test configuration")
    g = p.add_argument_group("odoo")
    g.add_argument("--live", action="store_true", help="connect with ODOO_* env vars")
    g.add_argument("--post", action="store_true", help="really post (needs --live)")
    g.add_argument("--attester", default=None)
    g.add_argument("--include-bad", action="store_true", help="scripted: batch the bad invoice")
    args = p.parse_args()

    if args.compare:
        if args.world != "simorg":
            raise SystemExit("--compare is for simorg")
        if not args.approve_all:
            raise SystemExit("--compare runs unattended, so the safety board (a person) cannot "
                             "answer; pass --approve-all and report the board as a rubber stamp")
        summary = asyncio.run(compare(args))
        print(json.dumps(summary, indent=2))
        return

    if args.no_gate and args.world != "simorg":
        raise SystemExit("--no-gate is only for the simulated org: the other worlds have real "
                         "effects, and a run with the gate off would carry them out unauthorized")
    if args.brain == "claude" and not args.model:
        print("note: no --model given, so the SDK default answers; the run record lists the "
              "models that did. Pin one for comparable runs.")
    world = build_world(args)
    out, rt = asyncio.run(run_once(args, world, not args.no_gate, args.quiet))
    record = {**out, "log": [vars(r) for r in rt.log], "human_requests": rt.human_requests,
              "audit": [vars(e) for e in rt.sup.audit.entries()]}
    with open(args.out, "w") as f:
        json.dump(record, f, indent=1, default=str)
    print("\n=== REPORT")
    print(json.dumps({"report": out["report"], "metrics": out["metrics"]}, indent=2,
                     default=str))
    print(f"(full run record, including the audit trail: {args.out})")


if __name__ == "__main__":
    main()

# EXEUNT — end of file.

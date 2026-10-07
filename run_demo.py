"""
Replay a historical case through the CCL-F v0.2 runtime and print what the
supervisor did at each step.

Usage:
    python run_demo.py challenger
    python run_demo.py therac25
    python run_demo.py mcas
    python run_demo.py challenger --quiet          # summary only
    python run_demo.py challenger --audit out.json # where to write the audit trail
    python run_demo.py challenger --no-obs         # no OpenTelemetry

No API key is needed: the scenarios are scripted events, and the advisor
(the only part that asks a model anything) is used only by "report" events.
"""

from __future__ import annotations

import argparse
import json
import os

from cclf import AuditTrail, replay
from cclf.observability import get_instrumentor
from scenarios import SCENARIOS

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
RED, GREEN, YELLOW, CYAN = "\033[31m", "\033[32m", "\033[33m", "\033[36m"

HIGHLIGHT_EVENTS = {
    "CLASSIFICATION_REJECTED": YELLOW, "ESCALATION": YELLOW, "TRANSITION_REFUSED": RED,
    "EXECUTION_BLOCKED": RED, "GATE_OVERRIDE": RED, "OPEN_LOOP_IRREVERSIBLE_EXECUTION": RED,
    "EXECUTION_PERMITTED": GREEN, "ATTEMPTED_CLOSURE": YELLOW,
}
INTERESTING_STATES = {"suppressed", "escalated", "trajectory_lock", "under_review"}


def describe(entry) -> str:
    p = entry.payload
    if entry.event == "TRANSITION":
        extra = f" [{p['closure_type']} closure]" if p.get("closure_type") else ""
        return f"{p.get('signal')}: {p['from']} → {p['to']}{extra}"
    if entry.event == "ESCALATION":
        return f"{p['condition']} ({p['scope']}): {p['detail']}"
    if entry.event == "CLASSIFICATION_REJECTED":
        return f"{p['signal']}: {p['proposed']} refused → {p['applied']} ({p['reason']})"
    if entry.event == "TRANSITION_REFUSED":
        return f"{p['signal']}: {p['reason']}"
    if entry.event in ("EXECUTION_BLOCKED", "GATE_OVERRIDE"):
        lines = [f"{p['decision']} (coherence {p['coherence']:.2f})"]
        lines += [f"      - {f}" for f in p["failures"]]
        if entry.event == "GATE_OVERRIDE":
            lines.append(f"      override by {entry.actor}: {p['rationale']!r}")
        return "\n".join(lines)
    if entry.event == "OPEN_LOOP_IRREVERSIBLE_EXECUTION":
        return f"{p['decision']}: locked {p['locked']}, still open {p['still_open']}"
    return json.dumps(p)[:120]


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a case through the CCL-F runtime")
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--quiet", action="store_true", help="print the summary only")
    parser.add_argument("--audit", default=None,
                        help="audit trail output file (default: <scenario>_audit.json)")
    parser.add_argument("--no-obs", action="store_true", help="disable OpenTelemetry")
    args = parser.parse_args()

    if args.no_obs:
        os.environ["CCLF_OBSERVABILITY_ENABLED"] = "false"
    obs = get_instrumentor()
    obs.setup()

    print(f"\n{CYAN}{BOLD}CCL-F v0.2 runtime — {args.scenario}{RESET}\n")
    seen = 0

    def on_event(event: dict, out: dict) -> None:
        nonlocal seen
        new = sv_ref[0].audit.entries()[seen:] if sv_ref else []
        seen += len(new)
        for entry in new:
            obs.record_audit_entry(entry.event, entry.payload)
        if args.quiet:
            return
        note = event.get("note")
        print(f"{BOLD}{event['op']}{RESET} {DIM}{note or ''}{RESET}")
        for entry in new:
            colour = HIGHLIGHT_EVENTS.get(entry.event)
            if entry.event == "TRANSITION" and (entry.payload.get("closure_type") or
                                                entry.payload["to"] in INTERESTING_STATES):
                colour = CYAN
            if colour:
                print(f"  {colour}{entry.event}{RESET} {describe(entry)}")

    from cclf import Supervisor
    sv_ref = [Supervisor()]
    with obs.span("cclf.replay", scenario=args.scenario):
        supervisor = replay(SCENARIOS[args.scenario], supervisor=sv_ref[0],
                            wrap=obs.wrap if obs.active else None, on_event=on_event)

    ok, why = AuditTrail.verify(supervisor.audit.entries())
    summary = supervisor.summary()
    print(f"\n{BOLD}Summary{RESET}")
    print(f"  signals by state : {summary['signals']}")
    print(f"  closures by type : {summary['closures']}")
    print(f"  open reviews     : {summary['open_reviews']}")
    print(f"  audit entries    : {summary['audit_entries']}  (chain {'intact' if ok else why})")
    for d in supervisor.decisions.values():
        score, factors = supervisor.coherence(d.decision_id)
        print(f"  decision {d.decision_id}: executed={d.executed}, coherence={score:.2f}")

    path = args.audit or f"{args.scenario}_audit.json"
    with open(path, "w") as f:
        json.dump(supervisor.audit.to_json(), f, indent=2, default=str)
    print(f"  audit trail      → {path}\n")


if __name__ == "__main__":
    main()

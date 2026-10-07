"""
CCL-F Commitment Agent — Demo Runner
=====================================
Runs the same CCL-F commitment state machine against two historical
safety failures. The graph, nodes and guards are identical across
scenarios; only the evidence changes.

  mcas      Boeing 737 MAX MCAS — concealment from the regulator (FAA)
  therac25  Therac-25 overdoses (1985–1987) — concealment from operators
            (hospitals), run in two passes:
              PASS 1  six patient incidents, sequential batches
              PASS 2  AECL suppression documents

Usage:
    python run_demo.py mcas                    # MCAS, interactive human review
    python run_demo.py therac25                # Therac-25, both passes
    python run_demo.py therac25 --pass1-only   # incidents only
    python run_demo.py therac25 --pass2-only   # suppression docs only
    python run_demo.py open                    # empty state, no pre-loaded evidence
    python run_demo.py mcas --no-hitl          # automated (no stdin prompts)
    python run_demo.py mcas --no-obs           # disable OTel observability
    python run_demo.py mcas --output-audit audit.json

Observability (OTel → Datadog or Dynatrace):
    See observability/README.md for backend-specific setup.
    Quick start:
      export OTEL_SERVICE_NAME=cclf-agents
      export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
      python run_demo.py therac25

Requires an LLM backend key (OPENAI_API_KEY by default; see cclf/backends/).
"""

from __future__ import annotations
import argparse
import json
import os
import uuid

from cclf import build_graph, CCLFAgentState, Evidence
from cclf import nodes as cclf_nodes
from cclf.observability import get_instrumentor, instrument_nodes, session_span
from scenarios import MCAS_SCENARIO, PASS_1_INCIDENTS, PASS_2_SUPPRESSION


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[31m"
YELLOW = "\033[33m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
DIM    = "\033[2m"


def banner(text: str, color: str = CYAN) -> None:
    width = 62
    print(f"\n{color}{BOLD}{'━' * width}{RESET}")
    print(f"{color}{BOLD}  {text}{RESET}")
    print(f"{color}{BOLD}{'━' * width}{RESET}")


def section(text: str) -> None:
    print(f"\n{YELLOW}{'─' * 62}{RESET}")
    print(f"{YELLOW}{text}{RESET}")
    print(f"{YELLOW}{'─' * 62}{RESET}")


def msg(text: str) -> None:
    if "ACO DETECTED" in text or "BLOCKED" in text:
        color = RED
    elif "PASS" in text or "applied" in text or "✅" in text:
        color = GREEN
    elif "⚠️" in text:
        color = YELLOW
    else:
        color = DIM
    print(f"  {color}{text}{RESET}")


# ---------------------------------------------------------------------------
# Run one evidence batch through the graph
# ---------------------------------------------------------------------------

def run_batch(graph, state: CCLFAgentState, config: dict,
              batch: list[dict], label: str) -> CCLFAgentState:
    """Add evidence, stream through graph, return updated state."""
    for ev_dict in batch:
        state.evidence_buffer.append(Evidence(**ev_dict))

    section(label)
    for ev in batch:
        print(f"  {DIM}+ [{ev['evidence_id']}] {ev['source']}{RESET}")

    prev_msg_count = len(state.messages)
    for chunk in graph.stream(state, config=config, stream_mode="values"):
        state = CCLFAgentState.from_stream(chunk)

    for m in state.messages[prev_msg_count:]:
        msg(m)

    print(f"\n  {BOLD}Commitment state: {state.commitment_state}{RESET}")
    if state.aco_detected:
        print(f"  {RED}{BOLD}⚠️  ACO ACTIVE: {state.aco_reasoning[:120]}{RESET}")
    return state


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def run_mcas(graph, state, config, args) -> CCLFAgentState:
    banner("CCL-F Commitment Agent — Boeing 737 MAX MCAS")
    print(f"\n  {DIM}5 evidence items introduced sequentially.{RESET}")
    total = len(MCAS_SCENARIO)
    for idx, item in enumerate(MCAS_SCENARIO):
        if state.should_terminate:
            break
        state = run_batch(graph, state, config, [item],
                          f"[{idx + 1}/{total}] {item['source']}")
    return state


THERAC_INCIDENT_LABELS = [
    "Incident 1 — Kennestone Regional Oncology Center, GA (Jun 1985)",
    "Incident 2 — Hamilton Civic Hospital, Ontario (Jul 1985)",
    "Incident 3 — Yakima Valley Memorial Hospital, WA (Dec 1985)",
    "Incident 4 — East Texas Cancer Center (Mar 1986)",
    "Incident 5 — Yakima Valley Memorial Hospital, WA (Jan 1987)",
    "Incident 6 — Yakima Valley Memorial / NRC intervention (Jan–Feb 1987)",
]


def run_therac25(graph, state, config, args) -> CCLFAgentState:
    banner("CCL-F Commitment Agent — Therac-25 (1985–1987)")
    print(f"""
  {DIM}Six patients were overdosed by Therac-25 radiation therapy
  machines over 22 months. AECL possessed internal knowledge of
  a software race condition while repeatedly telling hospitals
  "no fault found." This is Adversarial Commitment Opacity.

  PASS 1  Six patient incidents — sequential evidence batches
  PASS 2  AECL suppression documents — the gap between what
          AECL knew and what it disclosed{RESET}""")

    if not args.pass2_only:
        banner("PASS 1 — Patient Incidents", CYAN)
        for idx, (batch, label) in enumerate(zip(PASS_1_INCIDENTS, THERAC_INCIDENT_LABELS)):
            if state.should_terminate:
                break
            state = run_batch(graph, state, config, batch, f"[{idx + 1}/6] {label}")

    if not args.pass1_only:
        banner("PASS 2 — AECL Suppression Documents", RED)
        print(f"""
  {DIM}The following evidence was not available to hospitals or
  regulators during PASS 1. It surfaces the internal knowledge
  AECL held while issuing 'no fault found' assurances.{RESET}""")
        state = run_batch(graph, state, config, PASS_2_SUPPRESSION,
                          "AECL Internal Documents + NRC Recall")
    return state


def run_open(graph, state, config, args) -> CCLFAgentState:
    banner("CCL-F Commitment Agent — Open scenario (no pre-loaded evidence)")
    return run_batch(graph, state, config, [], "Empty evidence batch")


THERAC_NOTE = """  {dim}CCL-F note: The Therac-25 ACO is a compound failure.
  C1 (state divergence): AECL's formal position (OPEN/investigating)
     diverged from their inferred ACS (TRAJECTORY — software-only
     interlocks are sufficient) with high confidence by Incident 3.
  C2 (evidence suppressed): The race condition memo was not disclosed
     to the hospitals generating the incident reports.
  The 'no fault found' letters are the ACO signal, not the race
  condition itself. The race condition is the hazard; the letters
  are the commitment opacity that kept the hazard active.{reset}
"""

SCENARIOS = {"mcas": run_mcas, "therac25": run_therac25, "open": run_open}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_audit(state: CCLFAgentState, path: str) -> None:
    audit_data = [
        {
            "seq":        e.sequence,
            "event":      e.event_type,
            "from":       e.from_state,
            "to":         e.to_state,
            "payload":    e.payload,
            "timestamp":  e.timestamp,
            "entry_hash": e.entry_hash,
            "prev_hash":  e.prev_hash,
        }
        for e in state.audit_log
    ]
    with open(path, "w") as f:
        json.dump(audit_data, f, indent=2, default=str)
    print(f"  Audit log → {path}\n")


def main():
    parser = argparse.ArgumentParser(description="CCL-F Commitment Agent Demo")
    parser.add_argument("scenario", nargs="?", choices=sorted(SCENARIOS), default="mcas")
    parser.add_argument("--no-hitl", action="store_true",
                        help="Disable human-in-the-loop interrupts (automated mode)")
    parser.add_argument("--no-obs", action="store_true",
                        help="Disable OTel observability")
    parser.add_argument("--pass1-only", action="store_true",
                        help="therac25 only: run the incident pass only")
    parser.add_argument("--pass2-only", action="store_true",
                        help="therac25 only: run the suppression-document pass only")
    parser.add_argument("--output-audit", default=None,
                        help="Write final audit log here (default: <scenario>_audit.json)")
    args = parser.parse_args()

    if (args.pass1_only or args.pass2_only) and args.scenario != "therac25":
        parser.error("--pass1-only / --pass2-only apply to the therac25 scenario")
    if args.pass1_only and args.pass2_only:
        parser.error("choose at most one of --pass1-only / --pass2-only")

    backend = os.environ.get("CCLF_LLM_BACKEND", "openai")
    if backend == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print(f"{YELLOW}⚠️  OPENAI_API_KEY not set — LLM nodes will fail gracefully.{RESET}")
        print("   export OPENAI_API_KEY=sk-...\n")

    # Observability setup — must happen before build_graph()
    if args.no_obs:
        os.environ["CCLF_OBSERVABILITY_ENABLED"] = "false"
    instrumentor = get_instrumentor()
    instrumentor.setup()
    instrument_nodes(cclf_nodes, instrumentor)

    obs_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    obs_status = "disabled" if args.no_obs else f"active → {obs_endpoint}"
    print(f"Observability : {obs_status}")

    # The CLI always runs human_review inline: it prompts on stdin, or in
    # --no-hitl mode records an explicit AUTO-APPROVED decision. (The
    # interrupt_before pattern is for services that resume from an external
    # approval event; nothing in this CLI resumes a paused graph.)
    if args.no_hitl:
        os.environ["CCLF_AUTO_APPROVE"] = "true"
    graph     = build_graph(interrupt_before_human=False, use_checkpointer=True)
    state     = CCLFAgentState()
    thread_id = str(uuid.uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    with session_span(instrumentor, scenario=args.scenario, thread_id=thread_id):
        state = SCENARIOS[args.scenario](graph, state, config, args)

    if not state.should_terminate:
        from cclf.nodes import terminate
        state = terminate(state)

    banner("SESSION COMPLETE", GREEN)
    print(f"""
  Final commitment state : {BOLD}{state.commitment_state}{RESET}
  ACO detected           : {RED + BOLD if state.aco_detected else ''}{state.aco_detected}{RESET}
  Evidence processed     : {len(state.evidence_buffer)}
  Admissible evidence    : {sum(1 for e in state.evidence_buffer if e.is_admissible())}
  Audit entries          : {len(state.audit_log)}
""")
    if state.aco_detected:
        print(f"  {RED}{BOLD}ACO REASONING:{RESET}")
        print(f"  {RED}{state.aco_reasoning}{RESET}\n")
    if args.scenario == "therac25":
        print(THERAC_NOTE.format(dim=DIM, reset=RESET))

    write_audit(state, args.output_audit or f"{args.scenario}_audit.json")


if __name__ == "__main__":
    main()

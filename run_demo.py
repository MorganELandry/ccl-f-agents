"""
THE TOURING COMPANY
A Play in Ten Scenes
====================

PROLOGUE
--------
This is the script you actually run from the command line. It does not
contain any CCL-F logic itself. Instead it is the touring company that takes
the same production (the graph in cclf/graph.py, the nodes in cclf/nodes.py,
and the guard in cclf/guards.py) on the road to different historical venues,
feeds it the evidence from that venue, and prints what happened in colour.

Runs the same CCL-F commitment state machine against two historical
safety failures. The graph, nodes and guards are identical across
scenarios; only the evidence changes.

  mcas      Boeing 737 MAX MCAS — concealment from the regulator (FAA)
  therac25  Therac-25 overdoses (1985–1987) — concealment from operators
            (hospitals), run in two passes:
              PASS 1  six patient incidents, sequential batches
              PASS 2  AECL suppression documents
  open      an empty run with no pre-loaded evidence

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
Without one the run still completes: the LLM nodes fail gracefully and the
script still prints a summary and writes the audit log.

THE PLAYBILL (what happens in this file)
    Scene 1   banner()        print a big coloured heading
    Scene 2   section()       print a smaller coloured heading
    Scene 3   msg()           print one node message, coloured by content
    Scene 4   run_batch()     add one batch of evidence and run the graph once
    Scene 5   run_mcas()      the Boeing 737 MAX scenario
    Scene 6   run_therac25()  the Therac-25 scenario, in two passes
    Scene 7   run_open()      an empty scenario
    Scene 8   SCENARIOS       the table mapping a scenario name to its function
    Scene 9   write_audit()   save the hash-chained audit log as JSON
    Scene 10  main()          read the CLI flags and run the whole show

READER'S NOTE — the command-line flags (argparse)
    argparse turns `sys.argv` into an object `args` with one attribute per
    flag. A dash in a flag name becomes an underscore: --no-hitl is read as
    args.no_hitl. `action="store_true"` means "False unless the flag is
    present". The flags are:
      scenario        positional, optional; one of mcas, open, therac25
                      (default mcas)
      --no-hitl       no human prompts; human_review auto-approves and says so
                      in the audit log (via CCLF_AUTO_APPROVE)
      --no-obs        ask for OpenTelemetry to be switched off (see the note
                      in main(), Scene 10, about when this takes effect)
      --pass1-only    therac25 only: run the six incidents, skip PASS 2
      --pass2-only    therac25 only: run the suppression documents only
      --output-audit  where to write the audit JSON
                      (default: <scenario>_audit.json in the current folder)

READER'S NOTE — graph.stream() and evidence batches
    The graph runs one "cycle" per call: evidence_intake → acs_inference →
    aco_detection → transition_evaluation → transition_guard → (human_review)
    → apply_transition, then it ends (see route_after_apply in graph.py). It
    never waits for more evidence on its own. So this script drives it: each
    scenario splits its evidence into batches, and run_batch() appends one
    batch to state.evidence_buffer and calls graph.stream() once. With
    stream_mode="values", stream() yields the full state after each node
    finishes; we keep only the last one, which is the state at the end of
    the cycle, and pass it into the next batch.

READER'S NOTE — why CCLFAgentState.from_stream() is needed
    Depending on the LangGraph version, each streamed chunk is either the
    CCLFAgentState dataclass itself or a plain dict of its fields. from_stream()
    (in cclf/types.py) accepts either and always returns a CCLFAgentState, so
    the code below can safely write state.messages, state.aco_detected, etc.

READER'S NOTE — ANSI colour codes
    Strings like "\\033[31m" are ANSI escape codes. "\\033" is the ESC
    character; a terminal that sees ESC [ 31 m switches its text to red, and
    ESC [ 0 m resets it. They are only instructions to the terminal, so if
    output is redirected to a file you will see the raw codes in it.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# argparse    reads the command-line flags
# json        writes the audit log file
# os          reads/sets environment variables (API key, auto-approve, OTel)
# uuid        makes a random, unique thread id for the LangGraph checkpointer
# cclf        the agent: build_graph() makes the graph; CCLFAgentState is the
#             state object; Evidence is one evidence item
# cclf_nodes  the nodes module itself, so observability can wrap its functions
# get_instrumentor / instrument_nodes / session_span   see cclf/observability.py
# scenarios   the evidence lists for each historical case (lists of dicts)
# ===========================================================================

from __future__ import annotations
import argparse
import json
import os
import uuid

from cclf import build_graph, CCLFAgentState, Evidence
from cclf import nodes as cclf_nodes
from cclf.observability import get_instrumentor, instrument_nodes, session_span
from scenarios import MCAS_SCENARIO, PASS_1_INCIDENTS, PASS_2_SUPPRESSION


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# One module-level variable, SCENARIOS, is NOT here: it holds the scenario
# functions themselves, so it can only be built after they are defined. It
# lives just after run_open() (Scene 8).
# ===========================================================================

# Console helpers
# --- The colour palette (ANSI escape codes; see READER'S NOTE above) -------
# Each is a short string that, when printed, changes the terminal's style.
# Always print RESET afterwards, or the colour leaks into later output.
#   RESET   back to the terminal's normal style
#   BOLD    bold text
#   RED     errors, BLOCKED transitions, ACO alerts
#   YELLOW  section rules and warnings
#   GREEN   passes, applied transitions, the final "SESSION COMPLETE" banner
#   CYAN    the default banner colour
#   DIM     faint text for background detail
RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[31m"
YELLOW = "\033[33m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
DIM    = "\033[2m"

# THERAC_INCIDENT_LABELS — a human-readable heading for each of the six
#   Therac-25 incidents. It lines up one-to-one, by position, with the six
#   evidence batches in scenarios.PASS_1_INCIDENTS (run_therac25 zips them).
THERAC_INCIDENT_LABELS = [
    "Incident 1 — Kennestone Regional Oncology Center, GA (Jun 1985)",
    "Incident 2 — Hamilton Civic Hospital, Ontario (Jul 1985)",
    "Incident 3 — Yakima Valley Memorial Hospital, WA (Dec 1985)",
    "Incident 4 — East Texas Cancer Center (Mar 1986)",
    "Incident 5 — Yakima Valley Memorial Hospital, WA (Jan 1987)",
    "Incident 6 — Yakima Valley Memorial / NRC intervention (Jan–Feb 1987)",
]

# THERAC_NOTE — a closing explanation printed after a therac25 run.
#   It is a template: {dim} and {reset} are filled in by
#   THERAC_NOTE.format(dim=DIM, reset=RESET) in main(), so the note prints faint.
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


# ===========================================================================
# SCENE 1 — THE MARQUEE
# banner(): print a heading framed by two thick lines.
# ===========================================================================

def banner(text: str, color: str = CYAN) -> None:
    """
    Print a bold, coloured heading between two 62-character rules.

    Enter:   text   the heading text
             color  an ANSI colour code from DRAMATIS PERSONAE (default CYAN)
    Exit:    None. Prints three lines (after a blank line).
    """
    # PLAYERS IN THIS SCENE
    #   width  how many '━' characters wide the rules are

    width = 62
    # '━' * width repeats the character `width` times.
    print(f"\n{color}{BOLD}{'━' * width}{RESET}")
    print(f"{color}{BOLD}  {text}{RESET}")
    print(f"{color}{BOLD}{'━' * width}{RESET}")


# ===========================================================================
# SCENE 2 — THE SCENE CARD
# section(): print a smaller yellow heading between two thin lines.
# ===========================================================================

def section(text: str) -> None:
    """
    Print a yellow sub-heading between two 62-character thin rules.

    Enter:   text  the heading text (run_batch passes the batch label)
    Exit:    None. Prints three lines (after a blank line).
    """
    print(f"\n{YELLOW}{'─' * 62}{RESET}")
    print(f"{YELLOW}{text}{RESET}")
    print(f"{YELLOW}{'─' * 62}{RESET}")


# ===========================================================================
# SCENE 3 — THE PROMPTER'S LINE
# msg(): print one node message, picking its colour from its content.
# ===========================================================================

def msg(text: str) -> None:
    """
    Print one message from state.messages, coloured by what it says.

    Enter:   text  one message string written by a node
    Exit:    None. Prints the message, indented, in one colour.

    The checks run top to bottom and the first match wins:
      contains "ACO DETECTED" or "BLOCKED"             → red
      contains "PASS", "applied" or the ✅ character   → green
      contains the ⚠️ character                        → yellow
      anything else                                    → dim
    """
    # PLAYERS IN THIS SCENE
    #   color  the ANSI colour chosen for this message

    if "ACO DETECTED" in text or "BLOCKED" in text:
        color = RED
    elif "PASS" in text or "applied" in text or "✅" in text:
        color = GREEN
    elif "⚠️" in text:
        color = YELLOW
    else:
        color = DIM
    print(f"  {color}{text}{RESET}")


# ===========================================================================
# SCENE 4 — ONE PERFORMANCE OF THE LOOP
# run_batch(): add one batch of evidence, run the graph once, show results.
# ===========================================================================

# Run one evidence batch through the graph
def run_batch(graph, state: CCLFAgentState, config: dict,
              batch: list[dict], label: str) -> CCLFAgentState:
    """
    Add evidence, stream through graph, return updated state.

    Enter:   graph   the compiled LangGraph from build_graph()
             state   the CCLFAgentState so far (carried between batches)
             config  {"configurable": {"thread_id": ...}}; the checkpointer
                     uses the thread id to keep this run's history together
             batch   a list of evidence dicts, each with the fields of
                     Evidence (evidence_id, content, source, ...)
             label   heading text printed above this batch
    Exit:    the state at the end of this graph cycle

    Side effects: prints the batch heading, each evidence id and source,
    every new node message, the commitment state, and an ACO warning if set.
    """
    # PLAYERS IN THIS SCENE
    #   ev_dict         one evidence dict from the batch (while loading)
    #   ev              one evidence dict from the batch (while printing)
    #   prev_msg_count  how many messages existed before this run, so we
    #                   print only the new ones
    #   chunk           one streamed snapshot of the state from graph.stream()
    #   m               one new message being printed

    # --- Load the evidence into the state --------------------------------
    # Evidence(**ev_dict) "unpacks" the dict: each key becomes a keyword
    # argument, so {"evidence_id": "E1", ...} becomes Evidence(evidence_id="E1", ...).
    for ev_dict in batch:
        state.evidence_buffer.append(Evidence(**ev_dict))

    # --- Show what is coming in ------------------------------------------
    section(label)
    for ev in batch:
        print(f"  {DIM}+ [{ev['evidence_id']}] {ev['source']}{RESET}")

    # --- Run the graph once over the updated state -----------------------
    # Each chunk is the full state after one node. We overwrite `state` each
    # time, so after the loop it holds the state after the last node.
    # from_stream() turns a dict chunk back into a CCLFAgentState (see
    # READER'S NOTE at the top). If human_review runs, it may prompt on stdin
    # in the middle of this loop.
    prev_msg_count = len(state.messages)
    for chunk in graph.stream(state, config=config, stream_mode="values"):
        state = CCLFAgentState.from_stream(chunk)

    # --- Print only the messages this run added ---------------------------
    # state.messages[prev_msg_count:] is a slice: everything from that index on.
    for m in state.messages[prev_msg_count:]:
        msg(m)

    # --- Summarise where we ended up --------------------------------------
    # aco_reasoning is cut to 120 characters with [:120] to keep it on screen.
    print(f"\n  {BOLD}Commitment state: {state.commitment_state}{RESET}")
    if state.aco_detected:
        print(f"  {RED}{BOLD}⚠️  ACO ACTIVE: {state.aco_reasoning[:120]}{RESET}")
    return state


# ===========================================================================
# SCENE 5 — THE BOEING 737 MAX
# run_mcas(): feed the MCAS evidence in one item at a time.
# ===========================================================================

# Scenarios
def run_mcas(graph, state, config, args) -> CCLFAgentState:
    """
    Run the Boeing 737 MAX MCAS scenario.

    Enter:   graph, state, config  as for run_batch()
             args                  the parsed CLI flags (not used here, but
                                   every scenario function takes the same four
                                   arguments so main() can call any of them)
    Exit:    the final state

    Each item in MCAS_SCENARIO becomes its own one-item batch ([item]), so
    the graph runs once per item. The loop stops early if a node has set
    state.should_terminate.
    """
    # PLAYERS IN THIS SCENE
    #   total  how many MCAS evidence items there are
    #   idx    0-based position of the current item (shown as idx + 1)
    #   item   the current evidence dict

    banner("CCL-F Commitment Agent — Boeing 737 MAX MCAS")
    print(f"\n  {DIM}5 evidence items introduced sequentially.{RESET}")
    total = len(MCAS_SCENARIO)
    # enumerate() yields (index, item) pairs, starting at 0.
    for idx, item in enumerate(MCAS_SCENARIO):
        if state.should_terminate:
            break
        state = run_batch(graph, state, config, [item],
                          f"[{idx + 1}/{total}] {item['source']}")
    return state


# ===========================================================================
# SCENE 6 — THE THERAC-25
# run_therac25(): PASS 1 (six incidents) then PASS 2 (suppression documents).
# ===========================================================================

def run_therac25(graph, state, config, args) -> CCLFAgentState:
    """
    Run the Therac-25 scenario in up to two passes.

    Enter:   graph, state, config  as for run_batch()
             args                  the parsed CLI flags; args.pass1_only and
                                   args.pass2_only choose which passes run
    Exit:    the final state

    PASS 1 runs the graph once per incident (each incident is a batch of one
    or more evidence items), stopping early if should_terminate is set.
    PASS 2 sends all the suppression documents as one single batch, and is
    not skipped by should_terminate.
    """
    # PLAYERS IN THIS SCENE
    #   idx    0-based incident number (shown as idx + 1)
    #   batch  the evidence dicts for one incident
    #   label  that incident's heading from THERAC_INCIDENT_LABELS

    banner("CCL-F Commitment Agent — Therac-25 (1985–1987)")
    # A triple-quoted f-string can span several lines and still fill in {DIM}.
    print(f"""
  {DIM}Six patients were overdosed by Therac-25 radiation therapy
  machines over 22 months. AECL possessed internal knowledge of
  a software race condition while repeatedly telling hospitals
  "no fault found." This is Adversarial Commitment Opacity.

  PASS 1  Six patient incidents — sequential evidence batches
  PASS 2  AECL suppression documents — the gap between what
          AECL knew and what it disclosed{RESET}""")

    # --- PASS 1: skipped only by --pass2-only ------------------------------
    # zip() pairs each incident batch with its label, position by position.
    if not args.pass2_only:
        banner("PASS 1 — Patient Incidents", CYAN)
        for idx, (batch, label) in enumerate(zip(PASS_1_INCIDENTS, THERAC_INCIDENT_LABELS)):
            if state.should_terminate:
                break
            state = run_batch(graph, state, config, batch, f"[{idx + 1}/6] {label}")

    # --- PASS 2: skipped only by --pass1-only ------------------------------
    if not args.pass1_only:
        banner("PASS 2 — AECL Suppression Documents", RED)
        print(f"""
  {DIM}The following evidence was not available to hospitals or
  regulators during PASS 1. It surfaces the internal knowledge
  AECL held while issuing 'no fault found' assurances.{RESET}""")
        state = run_batch(graph, state, config, PASS_2_SUPPRESSION,
                          "AECL Internal Documents + NRC Recall")
    return state


# ===========================================================================
# SCENE 7 — THE BARE STAGE
# run_open(): run the graph once with no evidence at all.
# ===========================================================================

def run_open(graph, state, config, args) -> CCLFAgentState:
    """
    Run one graph cycle with an empty evidence batch.

    Enter:   graph, state, config  as for run_batch()
             args                  the parsed CLI flags (not used here)
    Exit:    the state after that one cycle

    Useful to see how the agent behaves with nothing to go on.
    """
    banner("CCL-F Commitment Agent — Open scenario (no pre-loaded evidence)")
    return run_batch(graph, state, config, [], "Empty evidence batch")


# ===========================================================================
# SCENE 8 — THE TOUR SCHEDULE
# SCENARIOS: which function runs for each scenario name.
# ---------------------------------------------------------------------------
# This module-level variable cannot move up to DRAMATIS PERSONAE: its values
# are the functions run_mcas, run_therac25 and run_open, which only exist
# once the `def` statements above have run. main() uses it twice: the keys
# become the allowed choices for the `scenario` argument, and
# SCENARIOS[args.scenario] picks the function to call.
# ===========================================================================

SCENARIOS = {"mcas": run_mcas, "therac25": run_therac25, "open": run_open}


# ===========================================================================
# SCENE 9 — THE COURT RECORD
# write_audit(): save the hash-chained audit log to a JSON file.
# ===========================================================================

# Main
def write_audit(state: CCLFAgentState, path: str) -> None:
    """
    Write every audit entry to a JSON file.

    Enter:   state  the final state; its audit_log is what gets written
             path   the file to write (overwritten if it exists)
    Exit:    None. Writes the file and prints "  Audit log → <path>".

    The file is a JSON list with one object per AuditEntry, in order:
      seq, event, from, to, payload, timestamp, entry_hash, prev_hash.
    Each entry's prev_hash is the previous entry's entry_hash (the first one
    is "GENESIS"), so anyone can re-check the chain and spot a changed or
    missing entry. See AuditEntry in cclf/types.py.
    """
    # PLAYERS IN THIS SCENE
    #   audit_data  the audit log as a list of plain dicts
    #   e           one AuditEntry (inside the list comprehension)
    #   f           the open output file

    # --- Turn each AuditEntry into a plain dict ---------------------------
    # This is a "list comprehension": [<dict built from e> for e in ...].
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
    # --- Write it -----------------------------------------------------------
    # `with open(...)` closes the file automatically. default=str tells
    # json.dump to fall back to str() for anything it cannot encode natively.
    with open(path, "w") as f:
        json.dump(audit_data, f, indent=2, default=str)
    print(f"  Audit log → {path}\n")


# ===========================================================================
# SCENE 10 — OPENING NIGHT
# main(): read the flags, set everything up, run the scenario, print results.
# ===========================================================================

def main():
    """
    The command-line entry point.

    Enter:   (nothing; flags come from the command line, see READER'S NOTE)
    Exit:    None. Runs the chosen scenario, prints a summary, and writes the
             audit log. Exits with an argparse error for bad flag combinations.
    """
    # PLAYERS IN THIS SCENE
    #   parser        the argparse.ArgumentParser that defines the flags
    #   args          the parsed flags (args.scenario, args.no_hitl, ...)
    #   backend       which LLM backend is configured (default "openai")
    #   instrumentor  the shared CCLFInstrumentor from observability.py
    #   obs_endpoint  the OTLP endpoint, for the status line only
    #   obs_status    "disabled" or "active → <endpoint>", for the status line
    #   graph         the compiled LangGraph
    #   state         the CCLFAgentState, carried through the whole run
    #   thread_id     a random UUID naming this run for the checkpointer
    #   config        the LangGraph config dict holding thread_id
    #   terminate     the terminate node, imported late (see below)

    # --- Define and read the command-line flags ---------------------------
    # sorted(SCENARIOS) gives the dict's keys in alphabetical order.
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

    # --- Reject flag combinations that make no sense ----------------------
    # parser.error() prints the message and exits the program (status 2).
    if (args.pass1_only or args.pass2_only) and args.scenario != "therac25":
        parser.error("--pass1-only / --pass2-only apply to the therac25 scenario")
    if args.pass1_only and args.pass2_only:
        parser.error("choose at most one of --pass1-only / --pass2-only")

    # --- Warn (but carry on) if the OpenAI key is missing -----------------
    # An empty string counts as "not set" because "" is falsy.
    backend = os.environ.get("CCLF_LLM_BACKEND", "openai")
    if backend == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print(f"{YELLOW}⚠️  OPENAI_API_KEY not set — LLM nodes will fail gracefully.{RESET}")
        print("   export OPENAI_API_KEY=sk-...\n")

    # Observability setup — must happen before build_graph()
    # --- Observability: set up OTel and wrap the node functions ------------
    # --no-obs turns the switch off here; setup() reads it when it runs, so
    # setting it after observability.py was imported still takes effect.
    # setup() also falls back to no-op on its own if the OTel packages are
    # missing.
    if args.no_obs:
        os.environ["CCLF_OBSERVABILITY_ENABLED"] = "false"
    instrumentor = get_instrumentor()
    instrumentor.setup()
    # Replaces the functions in cclf.nodes with traced wrappers. This must
    # happen before build_graph(): the graph looks each node up on the
    # cclf.nodes module when it is built, so it picks up the wrappers.
    instrument_nodes(cclf_nodes, instrumentor)

    obs_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    obs_status = "disabled" if args.no_obs else f"active → {obs_endpoint}"
    print(f"Observability : {obs_status}")

    # --- Human review mode, then build the graph and the starting state ----
    # The CLI always runs human_review inline: it prompts on stdin, or in
    # --no-hitl mode records an explicit AUTO-APPROVED decision. (The
    # interrupt_before pattern is for services that resume from an external
    # approval event; nothing in this CLI resumes a paused graph.)
    # Hence interrupt_before_human=False always. --no-hitl does not change
    # the graph; it sets CCLF_AUTO_APPROVE, which human_review in nodes.py
    # checks each time it runs, recording "AUTO-APPROVED (unattended mode,
    # no human reviewer)" instead of calling input().
    # use_checkpointer=True attaches a MemorySaver keyed by thread_id.
    if args.no_hitl:
        os.environ["CCLF_AUTO_APPROVE"] = "true"
    graph     = build_graph(interrupt_before_human=False, use_checkpointer=True)
    state     = CCLFAgentState()
    thread_id = str(uuid.uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    # --- Run the chosen scenario inside one session span -------------------
    # SCENARIOS[args.scenario] looks up the function, and the trailing
    # (graph, state, config, args) calls it. The session span (a no-op when
    # OTel is off) groups the whole run into one trace.
    with session_span(instrumentor, scenario=args.scenario, thread_id=thread_id):
        state = SCENARIOS[args.scenario](graph, state, config, args)

    # --- Make sure the session is closed off in the audit log --------------
    # If the graph did not reach its terminate node, call it directly so the
    # audit log ends with a SESSION_END entry. Importing here (not at the top)
    # reads cclf.nodes.terminate after instrument_nodes() has replaced it.
    if not state.should_terminate:
        from cclf.nodes import terminate
        state = terminate(state)

    # --- Print the final summary -------------------------------------------
    # `RED + BOLD if state.aco_detected else ''` picks red-bold text only
    # when ACO was detected; the sum(...) counts admissible evidence items.
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

    # --- Save the audit log (the last thing printed) ------------------------
    # `a or b` gives a unless it is None/empty, so the default file name is
    # "<scenario>_audit.json" in the current working directory.
    write_audit(state, args.output_audit or f"{args.scenario}_audit.json")


# ===========================================================================
# CURTAIN UP
# `__name__ == "__main__"` is True only when this file is run directly
# (python run_demo.py ...), not when another module imports it.
# ===========================================================================

if __name__ == "__main__":
    main()

# EXEUNT — end of file.

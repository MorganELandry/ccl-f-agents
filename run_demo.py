"""
THE DEMONSTRATION
A Play in Two Scenes
====================

PROLOGUE
--------
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

How it works: main() picks a scenario from scenarios.SCENARIOS (a list of
event dicts), hands it to cclf.replay(), and after every event looks at the
audit entries that event added. Selected entries are printed in colour,
every new entry is passed to the OpenTelemetry instrumentor, and at the end
a summary is printed and the whole audit trail is written to a JSON file.

THE PLAYBILL (what happens in this file)
    Scene 1  describe()   turn one audit entry into a one-line (or few-line) description
    Scene 2  main()       parse arguments, replay the scenario, print and save results

READER'S NOTE — the colour codes
    Strings like "\\033[31m" are ANSI escape codes: most terminals read them
    as "switch to red" instead of printing them. "\\033[0m" (RESET) switches
    back to normal. Wrapping text as f"{RED}...{RESET}" colours just that
    text. If output is redirected to a file, the codes appear as raw bytes.
    The colours used here: RED for refusals, blocked gates, overrides and
    open-loop execution; YELLOW for rejected classifications, escalations
    and attempted closures; GREEN for permitted execution; CYAN for the
    title and for TRANSITION entries worth noticing (see Scene 2).

READER'S NOTE — audit-entry diffing
    The supervisor's audit trail is append-only, so the entries added by
    one event are simply the ones past the count already seen. on_event()
    keeps that count in `seen` and slices entries()[seen:] after each event:
    those are exactly the new entries for that event, in order.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# argparse            command-line parsing (scenario name and flags).
# json                writes the audit trail file; also a fallback description.
# os                  sets CCLF_OBSERVABILITY_ENABLED for --no-obs.
# cclf                AuditTrail (to verify the hash chain) and replay (the
#                     pipeline driver from cclf/graph.py). Supervisor is
#                     imported later, inside main().
# cclf.observability  get_instrumentor(): the shared telemetry object.
# scenarios           SCENARIOS: scenario name -> list of event dicts.
# ===========================================================================

from __future__ import annotations

import argparse
import json
import os

from cclf import AuditTrail, replay
from cclf.observability import get_instrumentor
from scenarios import SCENARIOS


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# RESET, BOLD, DIM — ANSI codes: back to normal text, bold, and dim (faint).
#   Tuple unpacking assigns the three strings to the three names at once.
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"

# RED, GREEN, YELLOW, CYAN — ANSI foreground colour codes (see READER'S NOTE).
RED, GREEN, YELLOW, CYAN = "\033[31m", "\033[32m", "\033[33m", "\033[36m"

# HIGHLIGHT_EVENTS — audit event name -> the colour to print it in. Only
#   events listed here (plus notable TRANSITIONs, see main) are printed;
#   routine entries such as CLASSIFIED or EVIDENCE_ADDED are left out to
#   keep the output readable. They are still in the saved audit file.
HIGHLIGHT_EVENTS = {
    "CLASSIFICATION_REJECTED": YELLOW, "ESCALATION": YELLOW, "TRANSITION_REFUSED": RED,
    "EXECUTION_BLOCKED": RED, "GATE_OVERRIDE": RED, "OPEN_LOOP_IRREVERSIBLE_EXECUTION": RED,
    "EXECUTION_PERMITTED": GREEN, "ATTEMPTED_CLOSURE": YELLOW,
}

# INTERESTING_STATES — commitment states (as their string values) that make
#   a TRANSITION entry worth printing even when it is not a closure.
INTERESTING_STATES = {"suppressed", "escalated", "trajectory_lock", "under_review"}


# ===========================================================================
# SCENE 1 — THE NARRATOR
# describe(): what does this audit entry say, in one readable line?
# ===========================================================================

def describe(entry) -> str:
    """
    Format one audit entry for the console.

    Enter:   entry   a cclf.audit.AuditEntry (uses .event, .payload, .actor)
    Exit:    a string; one line for most events, several (indented) for a
             blocked or overridden gate, which lists each failure

    Unknown event types fall back to the payload as JSON, cut to 120
    characters. The payload keys read here are the ones the Supervisor
    writes when it logs each event.
    """
    # PLAYERS IN THIS SCENE
    #   p       the entry's payload dict
    #   extra   (TRANSITION) " [<type> closure]" if the transition was a closure
    #   lines   (gate events) the output lines, joined with newlines at the end
    p = entry.payload
    # --- A state change: "signal: from → to", plus the closure type --------
    if entry.event == "TRANSITION":
        extra = f" [{p['closure_type']} closure]" if p.get("closure_type") else ""
        return f"{p.get('signal')}: {p['from']} → {p['to']}{extra}"
    # --- An automatic escalation to structural review ----------------------
    if entry.event == "ESCALATION":
        return f"{p['condition']} ({p['scope']}): {p['detail']}"
    # --- A classification the supervisor would not accept (Rule 2) ---------
    if entry.event == "CLASSIFICATION_REJECTED":
        return f"{p['signal']}: {p['proposed']} refused → {p['applied']} ({p['reason']})"
    # --- A state-machine transition the supervisor refused ------------------
    if entry.event == "TRANSITION_REFUSED":
        return f"{p['signal']}: {p['reason']}"
    # --- An execution gate that failed, or was overridden ------------------
    if entry.event in ("EXECUTION_BLOCKED", "GATE_OVERRIDE"):
        # :.2f formats a float with two decimal places.
        lines = [f"{p['decision']} (coherence {p['coherence']:.2f})"]
        # A list comprehension: one indented line per gate failure.
        lines += [f"      - {f}" for f in p["failures"]]
        if entry.event == "GATE_OVERRIDE":
            # !r prints the repr (with quotes), making the rationale stand out.
            lines.append(f"      override by {entry.actor}: {p['rationale']!r}")
        return "\n".join(lines)
    # --- Irreversible execution that went ahead with loops still open -------
    if entry.event == "OPEN_LOOP_IRREVERSIBLE_EXECUTION":
        return f"{p['decision']}: locked {p['locked']}, still open {p['still_open']}"
    # --- Anything else: show the raw payload, truncated ---------------------
    return json.dumps(p)[:120]


# ===========================================================================
# SCENE 2 — THE PERFORMANCE
# main(): replay the chosen scenario, narrating as it goes
# ===========================================================================

def main() -> None:
    """
    Command-line entry point.

    Enter:   (nothing; reads sys.argv through argparse)
    Exit:    None
             side effects: prints a step-by-step narration (unless --quiet)
             and a summary; writes the audit trail to a JSON file; may set
             CCLF_OBSERVABILITY_ENABLED=false in this process's environment
    """
    # PLAYERS IN THIS SCENE
    #   parser       the argparse parser
    #   args         the parsed arguments (scenario, quiet, audit, no_obs)
    #   obs          the shared Instrumentor (active only if setup succeeded)
    #   seen         how many audit entries have been handled so far
    #   on_event     callback run by replay() after each event
    #   Supervisor   the Supervisor class, imported locally here
    #   sv_ref       a one-item list holding the Supervisor, so on_event can
    #                reach it (see the note at on_event)
    #   supervisor   the Supervisor returned by replay() (the same object)
    #   ok, why      AuditTrail.verify() result: chain intact?, and if not, why
    #   summary      supervisor.summary(): counts by state, closure type, etc.
    #   d            each registered Decision in turn
    #   score        that decision's coherence score
    #   factors      that decision's coherence components (not printed)
    #   path         the audit trail output file name
    #   f            the open output file

    # --- Parse the command line --------------------------------------------
    parser = argparse.ArgumentParser(description="Replay a case through the CCL-F runtime")
    # choices= makes argparse reject any name that is not a known scenario.
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--quiet", action="store_true", help="print the summary only")
    parser.add_argument("--audit", default=None,
                        help="audit trail output file (default: <scenario>_audit.json)")
    parser.add_argument("--no-obs", action="store_true", help="disable OpenTelemetry")
    # argparse turns "--no-obs" into the attribute name args.no_obs.
    args = parser.parse_args()

    # --- Telemetry: switch off if asked, then set up (or stay a no-op) -----
    # The variable must be set before setup(), which is where it is read.
    if args.no_obs:
        os.environ["CCLF_OBSERVABILITY_ENABLED"] = "false"
    obs = get_instrumentor()
    obs.setup()

    print(f"\n{CYAN}{BOLD}CCL-F v0.2 runtime — {args.scenario}{RESET}\n")
    seen = 0

    # --- The per-event callback ---------------------------------------------
    def on_event(event: dict, out: dict) -> None:
        """
        After each event: send its new audit entries to telemetry and print them.

        Enter:   event   the event dict just processed
                 out     the graph's final EventState for it (not used here)
        Exit:    None; prints unless --quiet

        `nonlocal seen` lets this inner function update main()'s `seen`
        instead of creating its own local. sv_ref is only read, so it
        needs no declaration; it is looked up when on_event RUNS, by which
        time main() has assigned it below. A one-item list is used as a
        mutable holder for the supervisor.
        """
        # PLAYERS IN THIS SCENE
        #   new      the audit entries added by this event (see READER'S NOTE)
        #   entry    each new entry in turn
        #   note     the event's "note" (the spec section it illustrates), or None
        #   colour   the ANSI colour to print the entry in, or None to skip it
        nonlocal seen
        # --- Diff the audit trail: only entries past `seen` are new -------
        new = sv_ref[0].audit.entries()[seen:] if sv_ref else []
        seen += len(new)
        # --- Telemetry sees every entry, even in --quiet mode ---------------
        for entry in new:
            obs.record_audit_entry(entry.event, entry.payload)
        if args.quiet:
            return
        # --- Narrate: the op in bold, its note dimmed ----------------------
        note = event.get("note")
        print(f"{BOLD}{event['op']}{RESET} {DIM}{note or ''}{RESET}")
        for entry in new:
            colour = HIGHLIGHT_EVENTS.get(entry.event)
            # A TRANSITION is printed (in cyan) only if it is a closure or
            # lands in one of the INTERESTING_STATES.
            if entry.event == "TRANSITION" and (entry.payload.get("closure_type") or
                                                entry.payload["to"] in INTERESTING_STATES):
                colour = CYAN
            if colour:
                print(f"  {colour}{entry.event}{RESET} {describe(entry)}")

    # --- Run the replay inside one root span --------------------------------
    from cclf import Supervisor
    sv_ref = [Supervisor()]
    with obs.span("cclf.replay", scenario=args.scenario):
        # Node wrapping is only worth doing when telemetry is active.
        supervisor = replay(SCENARIOS[args.scenario], supervisor=sv_ref[0],
                            wrap=obs.wrap if obs.active else None, on_event=on_event)

    # --- Summary -------------------------------------------------------------
    # verify() re-checks every entry's hash and its link to the previous one.
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

    # --- Save the audit trail ------------------------------------------------
    # default=str makes json.dump write any value it cannot serialize
    # natively as its str() form instead of failing.
    path = args.audit or f"{args.scenario}_audit.json"
    with open(path, "w") as f:
        json.dump(supervisor.audit.to_json(), f, indent=2, default=str)
    print(f"  audit trail      → {path}\n")


# ---------------------------------------------------------------------------
# Run main() only when this file is executed as a script, not when imported.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()

# EXEUNT — end of file.

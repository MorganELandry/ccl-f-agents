"""
THE MODELS AND THE CODE AGREE
A Play in Fifteen Scenes
==============================

PROLOGUE
--------
Tests that tie the formal models in verification/ to the Python runtime.

The TLA+ model (verification/tla) and the Alloy model (verification/alloy)
are only worth something if they describe the code that actually runs. The
first four scenes read the vocabulary out of the model files and compare it
with cclf/: the transition table, the open states, the exit groups and the
EES-eligible evidence kinds. If someone edits one side and not the other,
these fail. They need nothing but Python.

The last three scenes run the real checkers, and are skipped unless the
tools are available: Java on the PATH, and the environment variables
TLA2TOOLS_JAR and ALLOY_JAR pointing at the jars (verification/run.sh
downloads pinned copies and sets them). Scene 6 is a mutation test: it adds
a forbidden transition to a copy of the TLA+ table and confirms TLC
reports the violation, so a passing model check is known not to be vacuous.

THE PLAYBILL
    Scene 1  test_tla_transition_table_matches_code
    Scene 2  test_tla_open_states_and_exit_groups_match_code
    Scene 3  test_tla_reentry_rule_matches_code      (every exit type, every condition)
    Scene 4  test_alloy_ees_kinds_match_code
    Scene 5  test_tlc_finds_no_violation             (needs Java + TLA2TOOLS_JAR)
    Scene 6  test_tlc_catches_a_forbidden_transition (needs Java + TLA2TOOLS_JAR)
    Scene 7  test_alloy_assertions_hold              (needs Java + ALLOY_JAR)
    Scene 8  test_tlc_catches_the_old_authority_gate (needs Java + TLA2TOOLS_JAR)
    Scene 9  test_tlc_catches_execution_class_faults (needs Java + TLA2TOOLS_JAR;
                                                      parametrized, 4 runs)
    Scene 10 test_alloy_catches_planted_faults       (needs Java + ALLOY_JAR;
                                                      parametrized, 3 runs)
    Scene 11 test_tlc_catches_chain_and_ees_faults   (needs Java + TLA2TOOLS_JAR;
                                                      parametrized, 4 runs)
    Scene 12 test_tlc_federation_holds               (needs Java + TLA2TOOLS_JAR)
    Scene 13 test_tlc_federation_is_not_vacuous      (needs Java + TLA2TOOLS_JAR;
                                                      parametrized, 3 runs)
    Scene 14 test_tlc_catches_federation_faults      (needs Java + TLA2TOOLS_JAR;
                                                      parametrized, 9 runs)
    Scene 15 test_tlc_catches_review_hold_faults     (needs Java + TLA2TOOLS_JAR;
                                                      parametrized, 2 runs)

READER'S NOTE — regular expressions
    re.findall(r'<<"(\\w+)", "(\\w+)">>', text) finds every TLA+ pair such as
    <<"registered", "classified">> and returns the two names inside the
    quotes as a tuple. \\w+ means "one or more letters, digits or
    underscores"; the parentheses mark the parts to return.

READER'S NOTE — subprocess
    subprocess.run([...], capture_output=True, text=True) starts another
    program (here, java), waits for it, and returns its exit code and its
    printed output as strings.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# itertools.product   every combination of the re-entry conditions.
# os, re, shutil,     environment variables, pattern matching, finding java,
#   subprocess          running the checkers.
# pathlib.Path        file paths that work on every operating system.
# pytest              skip markers and tmp_path.
# cclf.statemachine   the runtime's table, groups and reentry_allowed().
# cclf.types          the enums the models must agree with.
# ===========================================================================

import itertools
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cclf.statemachine import OPEN_STATES, TRANSITIONS, reentry_allowed
from cclf.types import (
    EES_ELIGIBLE_KINDS, EXIT_LEAVES_LOOP_OPEN, ExecutionClass, ExitType, LegalSubtype,
)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# ROOT — the repository root (this file is in ROOT/tests).
ROOT = Path(__file__).resolve().parent.parent

# TLA_FILE, ALLOY_FILE — the two model files.
TLA_FILE = ROOT / "verification" / "tla" / "CommitmentStateMachine.tla"
FED_FILE = ROOT / "verification" / "tla" / "FederatedClosure.tla"
ALLOY_FILE = ROOT / "verification" / "alloy" / "closure_and_architecture.als"

# TLA_TEXT, ALLOY_TEXT — their contents, read once.
TLA_TEXT = TLA_FILE.read_text()
FED_TEXT = FED_FILE.read_text()
ALLOY_TEXT = ALLOY_FILE.read_text()

# PAIR — the pattern for one TLA+ pair of strings, <<"a", "b">>.
PAIR = r'<<"(\w+)", "(\w+)">>'

# TLA2TOOLS, ALLOY — paths to the checker jars, or None if not configured.
TLA2TOOLS = os.environ.get("TLA2TOOLS_JAR")
ALLOY = os.environ.get("ALLOY_JAR")

# needs_tlc, needs_alloy — skip markers for the checker scenes.
needs_tlc = pytest.mark.skipif(not (shutil.which("java") and TLA2TOOLS),
                               reason="needs java and TLA2TOOLS_JAR (see verification/run.sh)")
needs_alloy = pytest.mark.skipif(not (shutil.which("java") and ALLOY),
                                 reason="needs java and ALLOY_JAR (see verification/run.sh)")

# FAST_CFG — a small TLC configuration (a 5-record log) so the checker
#   scenes finish in seconds. verification/run.sh runs the full bound.
FAST_CFG = (Path(TLA_FILE.with_suffix(".cfg")).read_text()
            .replace("MaxLog = 8", "MaxLog = 5"))

# CLASSES_CFG — the execution-class configuration (one signal, every class,
#   relabels allowed) at a 6-record log: deep enough for register, refuse,
#   relabel, review and execute, and quick enough for a test.
CLASSES_CFG = ((TLA_FILE.parent / "Classes.cfg").read_text()
               .replace("MaxLog = 7", "MaxLog = 6"))

# CHAIN_CFG, CYCLE_CFG — the Closure Chain configuration at a 10-record log
#   (deep enough for a reopen upstream to weaken a closure downstream), and
#   the lifecycle configuration with the dependency made a cycle.
CHAIN_CFG = ((TLA_FILE.parent / "Chain.cfg").read_text()
             .replace("MaxLog = 12", "MaxLog = 10"))
CYCLE_CFG = FAST_CFG.replace("MaxLog = 5", "MaxLog = 6").replace("CycleBack = FALSE",
                                                                 "CycleBack = TRUE")

# REVIEW_CFG — Scene 15: one signal, the decision irreversible, no relabels
#   or exits, a 7-record log: just deep enough for register, classify,
#   review, escalate (or suppress), accept and override. Seconds to check.
REVIEW_CFG = ((TLA_FILE.parent / "Classes.cfg").read_text()
              .replace('DeclaredInit = {"routine", "elevated", "irreversible"}',
                       'DeclaredInit = {"irreversible"}')
              .replace("ReversalInit = {FALSE, TRUE}", "ReversalInit = {FALSE}")
              .replace("Reclassify = TRUE", "Reclassify = FALSE")
              .replace("Exits = TRUE", "Exits = FALSE"))

# REVIEW_FAULTS — planted faults for Scene 15 (Layer 4, Overrides): name ->
#   (current text, planted text, properties of which TLC must report one).
REVIEW_FAULTS = {
    "override-past-a-structural-review": (
        "  /\\ accepted /\\ ~executed /\\ ~RelabelOpen /\\ ~ReviewHold /\\ ~GateFor(AppliedNow)",
        "  /\\ accepted /\\ ~executed /\\ ~RelabelOpen /\\ ~GateFor(AppliedNow)",
        ("NoIrreversibleExecutionPastReview", "OverrideLatchesReviews")),
    "suppressed-loops-do-not-hold": (
        'HeldStates == {"escalated", "suppressed"}',
        'HeldStates == {"escalated"}',
        ("NoIrreversibleExecutionPastReview", "OverrideLatchesReviews")),
}

# FED_CFG — the federation configuration at small bounds (histories of 2
#   events, 5 records in A's log): seconds, not the full run's minutes.
FED_CFG = ((FED_FILE.parent / "Federation.cfg").read_text()
           .replace("MaxLen = 3", "MaxLen = 2").replace("MaxALog = 6", "MaxALog = 5"))

# FED_WITNESSES — Scene 13: invariants that must FAIL, showing that
#   acceptance, withdrawal and fork detection all really happen.
FED_WITNESSES = ["NeverAccepts", "NeverWithdraws", "NeverCatchesFork"]

# FED_FAULTS — planted faults for Scene 14: name -> (current text, planted
#   text, the properties of which TLC must report one violated). Each
#   weakens what node A checks; the property it breaks is stated apart
#   from the check (Grounded, not Verified).
FED_FAULTS = {
    "ignore-the-third-node": (
        '    /\\ BDependsOnC => ("C" \\notin eq /\\ Seen("C", v) = "ok")',
        "    /\\ TRUE",
        ("LocalClosureOnlyWhenGrounded",)),
    "accept-unverified-evidence": (
        '    /\\ Seen("B", v) = "ok"',
        '    /\\ Seen("B", v) \\in Closes',
        ("LocalClosureOnlyWhenGrounded",)),
    "no-recheck": (
        '    IF mirror = "closed" /\\ ~Verified(v, eq)',
        "    IF FALSE",
        ("LocalClosureOnlyWhenGrounded", "EquivocatorNeverRelied")),
    "no-fork-detection": (
        "    /\\ IF view[p].h /= 0 /\\ Pref(p, h, view[p].n) /= Pref(p, view[p].h, view[p].n)",
        "    /\\ IF FALSE",
        ("NoHistorySwitch",)),
    "rollback-accepted": (
        "    /\\ view[p].h /= 0 => n >= view[p].n                 \\* rollback refused\n",
        "",
        ("NoRollback", "NoFalseAccusation")),
    "trust-an-equivocator": (
        '    /\\ "B" \\notin eq\n',
        "",
        ("EquivocatorNeverRelied", "LocalClosureOnlyWhenGrounded")),
    "a-writes-the-peers-log": (       # A "repairs" B's log while accepting
        "    /\\ UNCHANGED <<logs, view, equiv>>",
        "    /\\ logs' = [logs EXCEPT ![\"B\"][1] = Append(@, \"reopen\")]\n"
        "    /\\ UNCHANGED <<view, equiv>>",
        ("NodeIsolation",)),
    "one-write-moves-two-nodes": (    # B's write also changes C's history
        "    /\\ logs' = [logs EXCEPT ![p][h] = Append(@, e)]",
        "    /\\ logs' = [logs EXCEPT ![p][h] = Append(@, e), ![\"C\"][2] = <<\"reg\">>]",
        ("NodeIsolation",)),
    "silent-withdrawal": (
        '         /\\ alog\' = alog \\o <<entry, "withdrawn">>',
        "         /\\ alog' = Append(alog, entry)",
        ("WithdrawalLogged",)),
}

# CHAIN_FAULTS — planted faults for Scene 11: name -> (current text, planted
#   text, configuration, the property TLC must report violated).
CHAIN_FAULTS = {
    "ignore-upstream": (
        '  ELSE SoundIter(st, {s \\in Signals : st[s] = "closed_evidence"\n'
        '                                     /\\ \\A u \\in Signals : <<s, u>> \\in Upstream'
        ' => u \\in known},',
        '  ELSE SoundIter(st, {s \\in Signals : st[s] = "closed_evidence"},',
        "chain", "SoundAllTheWayUp"),
    "ignore-upstream-on-a-cycle": (
        '  ELSE SoundIter(st, {s \\in Signals : st[s] = "closed_evidence"\n'
        '                                     /\\ \\A u \\in Signals : <<s, u>> \\in Upstream'
        ' => u \\in known},',
        '  ELSE SoundIter(st, {s \\in Signals : st[s] = "closed_evidence"},',
        "cycle", "CycleNeverSound"),
    "silent-weakening": (
        "      weakened == (Sound \\ SoundOf(after)) \\ {s}",
        "      weakened == {}",
        "chain", "ChainWeakeningLogged"),
    "no-ees-required": (
        "          /\\ DecisionEES\n",
        "\n",
        "classes", "NoCleanPassOverBrokenChain"),
}

# ALLOY_FAULTS — planted faults for Scene 10: name -> (current text,
#   planted text, the assertion the Analyzer must find a counterexample to).
ALLOY_FAULTS = {
    "chain-from-everything": (          # greatest instead of least fixed point
        "  no stepord/first.snd\n",
        "  stepord/first.snd = Signal\n",
        "SelfSupportNeverSound"),
    "reversal-ignores-setters": (       # the class-setter may vouch for the path
        "e.kind in EESKinds and e.producer not in d.setters + d.acceptor + d.loops.evaluated",
        "e.kind in EESKinds and e.producer not in d.acceptor + d.loops.evaluated",
        "NoSelfCertifiedReversal"),
    "acceptor-may-supply-ees": (        # the acceptor's own evidence counts
        "e.kind in EESKinds and e.producer not in d.loops.evaluated + d.acceptor",
        "e.kind in EESKinds and e.producer not in d.loops.evaluated",
        "AcceptorCannotSupplyTheEES"),
}

# CLASS_FAULTS — planted faults for Scene 9: name -> (current text, planted
#   text, the property TLC must report violated).
CLASS_FAULTS = {
    "trust-the-declared-class": (
        'Applied(d, r) == IF d = "irreversible" \\/ r THEN d ELSE "irreversible"',
        'Applied(d, r) == d',
        "LowerClassNeedsReversal"),
    "no-relabel-review": (
        'IN relabel\' = IF lowered /\\ everBlocked THEN "open" ELSE relabel',
        "IN relabel' = relabel",
        "RelabelAfterRefusalEscalates"),
    "override-past-the-review": (
        "  /\\ accepted /\\ ~executed /\\ ~RelabelOpen /\\ ~ReviewHold /\\ ~GateFor(AppliedNow)",
        "  /\\ accepted /\\ ~executed /\\ ~ReviewHold /\\ ~GateFor(AppliedNow)",
        "NoExecutionWhileRelabelOpen"),
    "lowering-means-declared-only": (
        "  /\\ LET lowered == \\/ Rank[c] < Rank[declared]\n"
        "                    \\/ Rank[Applied(c, r)] < Rank[AppliedNow]",
        "  /\\ LET lowered == Rank[c] < Rank[declared]",
        "RelabelAfterRefusalEscalates"),
}


# ===========================================================================
# SCENE 0 — THE STAGEHANDS (helpers used by the scenes below)
# ===========================================================================

def tla_set(name: str) -> set[str]:
    """
    The string members of a one-line TLA+ set definition such as
    `ReentryStated == {"recoverable", "delegated"}`, read from the model.

    Enter:   name   the TLA+ definition's name
    Exit:    the set of strings inside its braces
    """
    # PLAYERS IN THIS SCENE
    #   match   the regex match for `name == { ... }` (braces may span lines)

    match = re.search(rf"^{name}\s*==\s*\{{(.*?)\}}", TLA_TEXT, re.S | re.M)
    assert match, f"{name} not found in the TLA+ model"
    return set(re.findall(r'"(\w+)"', match.group(1)))


def run_tlc(tla: Path, cfg_text: str, workdir: Path) -> subprocess.CompletedProcess:
    """
    Run TLC on a model with a given configuration.

    Enter:   tla        the .tla file (copied into workdir)
             cfg_text   the configuration to use
             workdir    an empty scratch directory
    Exit:    the finished process (returncode, stdout)
    """
    # PLAYERS IN THIS SCENE
    #   model, cfg   the copied model and the written configuration

    workdir.mkdir(parents=True, exist_ok=True)
    model = workdir / tla.name
    model.write_text(tla.read_text())
    cfg = workdir / "model.cfg"
    cfg.write_text(cfg_text)
    return subprocess.run(
        ["java", "-XX:+UseParallelGC", "-jar", TLA2TOOLS, "-workers", "auto",
         "-config", str(cfg), "-metadir", str(workdir / "meta"), str(model)],
        capture_output=True, text=True, cwd=workdir, timeout=600)


# ===========================================================================
# SCENE 1 — ONE TABLE, TWO READERS
# Proves: the TLA+ transition table is exactly cclf.statemachine.TRANSITIONS.
# ===========================================================================

def test_tla_transition_table_matches_code():
    """
    The pairs between the BEGIN/END TRANSITIONS markers equal the code's.

    Enter:   (nothing)
    Exit:    passes if both sets of (from, to) pairs are identical
    """
    # PLAYERS IN THIS SCENE
    #   block      the text between the markers
    #   in_model   the model's pairs
    #   in_code    the code's pairs, as plain strings

    block = TLA_TEXT.split("BEGIN TRANSITIONS")[1].split("END TRANSITIONS")[0]
    in_model = set(re.findall(PAIR, block))
    in_code = {(a.value, b.value) for a, b in TRANSITIONS}
    assert in_model == in_code


# ===========================================================================
# SCENE 2 — THE SAME GROUPS
# Proves: open states, exit types, and the exits that leave a loop open are
#   the same in the model and the code.
# ===========================================================================

def test_tla_open_states_and_exit_groups_match_code():
    """
    OpenStates, ExitTypes, LeavesOpen, LegalSubtypes and Classes agree
    with the code.

    Enter:   (nothing)
    Exit:    passes if each pair of sets is identical
    """
    assert tla_set("OpenStates") == {s.value for s in OPEN_STATES}
    assert tla_set("ExitTypes") == {x.value for x in ExitType}
    assert tla_set("LeavesOpen") == {x.value for x in EXIT_LEAVES_LOOP_OPEN}
    assert tla_set("LegalSubtypes") == {s.value for s in LegalSubtype}
    assert tla_set("Classes") == {c.value for c in ExecutionClass}


# ===========================================================================
# SCENE 3 — THE SAME WAY BACK
# Proves: for every exit type, legal sub-type and combination of conditions,
#   the model's ReentryAllowed gives the same answer as reentry_allowed().
# ===========================================================================

def test_tla_reentry_rule_matches_code():
    """
    Evaluate the model's ReentryAllowed in Python and compare with the code.

    Enter:   (nothing)
    Exit:    passes if they agree in all 544 cases: (13 non-legal exit types
             + 4 legal sub-types) x 32 combinations of the five conditions

    The model's rule is short enough to restate here from the sets read
    out of the file; the sets, not this restatement, are what could drift.
    """
    # PLAYERS IN THIS SCENE
    #   stated, needs_succ, free, resumable,  the model's sets
    #     waiting
    #   x, sub, succ, differs, lifted,        one case
    #     has_cond, met
    #   model, code                           the two answers

    stated = tla_set("ReentryStated")
    needs_succ = tla_set("ReentryNeedsSuccessor")
    free = tla_set("ReentryInferredFree")
    resumable = tla_set("LegalResumable")
    waiting = tla_set("WaitingExits")
    subtypes = [None] + list(LegalSubtype)
    # [[False, True]] * 5 is a list of five [False, True] lists; the leading
    # * spreads them out as five separate arguments, so product() yields
    # every combination of the five yes/no conditions (2**5 = 32).
    for x, sub, succ, differs, lifted, has_cond, met in itertools.product(
            ExitType, subtypes, *[[False, True]] * 5):
        if (x == ExitType.LEGAL) != (sub is not None):
            continue  # the model only pairs a sub-type with a legal exit
        model = (x.value in stated
                 or (x.value in needs_succ and succ)
                 or x.value in free
                 or (x.value == "boundary" and differs)
                 or (x.value == "legal" and sub.value in resumable and lifted)
                 or (x.value in waiting and has_cond and met))
        code, _ = reentry_allowed(x, legal_resumes=lifted, legal_subtype=sub,
                                  has_successor=succ, resumer_differs=differs,
                                  has_condition=has_cond, condition_met=met)
        assert model == code, (x, sub, succ, differs, lifted, has_cond, met)


# ===========================================================================
# SCENE 4 — THE SAME WITNESSES
# Proves: the Alloy model's EES-eligible kinds are the code's.
# ===========================================================================

def test_alloy_ees_kinds_match_code():
    """
    The kinds in Alloy's EESKinds, converted from CamelCase, equal
    EES_ELIGIBLE_KINDS.

    Enter:   (nothing)
    Exit:    passes if the two sets are identical

    PrimaryDocument -> primary_document: insert "_" before each capital
    after the first, then lowercase.
    """
    # PLAYERS IN THIS SCENE
    #   body    the text of the EESKinds function
    #   names   its kind names, converted to snake_case

    body = ALLOY_TEXT.split("fun EESKinds")[1].split("}")[0]
    names = {re.sub(r"(?<!^)([A-Z])", r"_\1", n).lower()
             for n in re.findall(r"\b([A-Z]\w+)\b", body) if n != "Kind"}
    assert names == {k.value for k in EES_ELIGIBLE_KINDS}


# ===========================================================================
# SCENE 5 — THE CHECKER'S VERDICT
# Proves: TLC finds no violation of any property (at a small bound).
# ===========================================================================

@needs_tlc
def test_tlc_finds_no_violation(tmp_path):
    """
    Run TLC on the model with the fast configuration.

    Enter:   tmp_path   pytest's per-test scratch directory
    Exit:    passes if TLC reports "No error has been found"
    """
    result = run_tlc(TLA_FILE, FAST_CFG, tmp_path / "lifecycle")
    assert "No error has been found" in result.stdout, result.stdout[-3000:]
    # The execution-class configuration, at a 5-record log.
    result = run_tlc(TLA_FILE, CLASSES_CFG.replace("MaxLog = 6", "MaxLog = 5"),
                     tmp_path / "classes")
    assert "No error has been found" in result.stdout, result.stdout[-3000:]
    # The Closure Chain configuration at a 9-record log, and the cycle.
    result = run_tlc(TLA_FILE, CHAIN_CFG.replace("MaxLog = 10", "MaxLog = 9"),
                     tmp_path / "chain")
    assert "No error has been found" in result.stdout, result.stdout[-3000:]
    result = run_tlc(TLA_FILE, CYCLE_CFG, tmp_path / "cycle")
    assert "No error has been found" in result.stdout, result.stdout[-3000:]


# ===========================================================================
# SCENE 6 — THE PLANTED FAULT
# Proves: the check is not vacuous. Adding "classified -> closed_authority"
#   (blocked by the spec) makes TLC report NoCloseBeforeReview violated.
# ===========================================================================

@needs_tlc
def test_tlc_catches_a_forbidden_transition(tmp_path):
    """
    Plant a forbidden transition in a copy of the model; TLC must object.

    Enter:   tmp_path   pytest's per-test scratch directory
    Exit:    passes if TLC names the violated property
    """
    # PLAYERS IN THIS SCENE
    #   mutant   the copied model with one extra pair
    #   result   TLC's run

    mutant = tmp_path / "src" / TLA_FILE.name
    mutant.parent.mkdir()
    mutant.write_text(TLA_TEXT.replace(
        '<<"classified", "under_review">>,',
        '<<"classified", "under_review">>,\n    <<"classified", "closed_authority">>,'))
    result = run_tlc(mutant, FAST_CFG, tmp_path)
    assert "NoCloseBeforeReview is violated" in result.stdout, result.stdout[-3000:]


# ===========================================================================
# SCENE 7 — THE ANALYZER'S VERDICT
# Proves: every Alloy assertion has no counterexample, and every `run`
#   finds an example (so no assertion holds vacuously).
# ===========================================================================

@needs_alloy
def test_alloy_assertions_hold(tmp_path):
    """
    Run every command in the Alloy model.

    Enter:   tmp_path   pytest's per-test scratch directory
    Exit:    passes if each `check` line ends UNSAT and each `run` line SAT
    """
    # PLAYERS IN THIS SCENE
    #   result   the Alloy run
    #   lines    its per-command summary lines

    result = subprocess.run(
        ["java", "-jar", ALLOY, "exec", "-f", "-c", "*", "-o", str(tmp_path / "out"),
         str(ALLOY_FILE)], capture_output=True, text=True, timeout=600)
    # Alloy prints its per-command summary on stderr, so read both streams.
    lines = [l.strip() for l in (result.stdout + result.stderr).splitlines()
             if re.match(r"\s*\d+\. (check|run) ", l)]
    # One summary line per command in the file (each starts with check or run).
    expected_count = len(re.findall(r"^(?:check|run) ", ALLOY_TEXT, re.M))
    assert len(lines) == expected_count, result.stdout + result.stderr
    for line in lines:
        expected = "UNSAT" if line.split()[1] == "check" else "SAT"
        assert line.split()[-1] == expected, line


# ===========================================================================
# SCENE 8 — THE OLD GATE, PLANTED BACK
# Proves: NoCleanPassOverAuthorityClosure is not vacuous. Restoring the
#   pre-October-2026 gate (a constraint counts as resolved if merely not
#   open, so an authority closure passes) makes TLC report it violated.
#   One signal and a six-record log reach that path quickly.
# ===========================================================================

@needs_tlc
def test_tlc_catches_the_old_authority_gate(tmp_path):
    """
    Plant the old GateOK in a copy of the model; TLC must object.

    Enter:   tmp_path   pytest's per-test scratch directory
    Exit:    passes if TLC names NoCleanPassOverAuthorityClosure
    """
    # PLAYERS IN THIS SCENE
    #   new_gate, old_gate   the current and the planted GateOK definitions
    #   mutant, cfg          the planted model and its one-signal configuration
    #   result               TLC's run

    new_gate = ('GateOK == /\\ \\A s \\in Signals :\n'
                '               \\/ s \\in Sound\n'
                '               \\/ state[s] = "exited" /\\ exitType[s] \\in ResolvingExits')
    old_gate = 'GateOK == /\\ \\A s \\in Signals : state[s] /= "unregistered" /\\ ~IsOpen(s)'
    assert new_gate in TLA_TEXT
    mutant = tmp_path / "src" / TLA_FILE.name
    mutant.parent.mkdir()
    mutant.write_text(TLA_TEXT.replace(new_gate, old_gate))
    cfg = (TLA_FILE.with_suffix(".cfg").read_text()
           .replace("MaxLog = 8", "MaxLog = 6").replace("Signals = {s1, s2}", "Signals = {s1}"))
    result = run_tlc(mutant, cfg, tmp_path)
    assert "NoCleanPassOverAuthorityClosure is violated" in result.stdout, result.stdout[-3000:]


# ===========================================================================
# SCENE 9 — FOUR WAYS TO RELABEL YOUR WAY PAST THE GATE
# Proves: each Execution Class Assignment property can fail. Planting each
#   fault in a copy of the model makes TLC report the matching property
#   violated: trusting the declared class (LowerClassNeedsReversal), never
#   opening the relabel review, letting an override past it, and counting
#   only declared-class lowerings (RelabelAfterRefusalEscalates for both).
# ===========================================================================

@needs_tlc
@pytest.mark.parametrize("fault", list(CLASS_FAULTS))
def test_tlc_catches_execution_class_faults(tmp_path, fault):
    """
    Plant one execution-class fault; TLC must name the property it breaks.

    Enter:   tmp_path   pytest's per-test scratch directory
             fault      a key of CLASS_FAULTS
    Exit:    passes if TLC reports that property violated
    """
    # PLAYERS IN THIS SCENE
    #   current, planted, prop   the fault's three parts
    #   mutant                   the planted copy of the model
    #   result                   TLC's run

    current, planted, prop = CLASS_FAULTS[fault]
    assert current in TLA_TEXT, fault
    mutant = tmp_path / "src" / TLA_FILE.name
    mutant.parent.mkdir()
    mutant.write_text(TLA_TEXT.replace(current, planted))
    result = run_tlc(mutant, CLASSES_CFG, tmp_path)
    assert f"{prop} is violated" in result.stdout, result.stdout[-3000:]


# ===========================================================================
# SCENE 10 — THE ANALYZER CATCHES WHAT IT SHOULD
# Proves: the Closure Chain and decision-level assertions are not vacuous.
#   Computing soundness from every loop instead of from none lets a
#   self-supporting loop count; letting the class-setter vouch for a
#   reversal path, or the acceptor supply the decision's External Evidence
#   Source, each breaks its assertion.
# ===========================================================================

@needs_alloy
@pytest.mark.parametrize("fault", list(ALLOY_FAULTS))
def test_alloy_catches_planted_faults(tmp_path, fault):
    """
    Plant one fault in a copy of the Alloy model; its assertion must fail.

    Enter:   tmp_path   pytest's per-test scratch directory
             fault      a key of ALLOY_FAULTS
    Exit:    passes if the Analyzer reports that check satisfiable (a
             counterexample exists)
    """
    # PLAYERS IN THIS SCENE
    #   current, planted, name   the fault's three parts
    #   mutant                   the planted copy of the model
    #   result                   the Alloy run
    #   line                     the summary line for that check

    current, planted, name = ALLOY_FAULTS[fault]
    assert current in ALLOY_TEXT, fault
    mutant = tmp_path / ALLOY_FILE.name
    mutant.write_text(ALLOY_TEXT.replace(current, planted))
    result = subprocess.run(
        ["java", "-jar", ALLOY, "exec", "-f", "-c", name, "-o", str(tmp_path / "out"),
         str(mutant)], capture_output=True, text=True, timeout=600)
    line = next(l for l in (result.stdout + result.stderr).splitlines()
                if re.search(rf"check {name}\b", l))
    assert line.split()[-1] == "SAT", line


# ===========================================================================
# SCENE 11 — A BROKEN CHAIN, A SILENT LOSS, A GATE WITH NO WITNESS
# Proves: the Closure Chain and decision-level EES properties can fail.
#   Ignoring upstream loops breaks SoundAllTheWayUp (and, on a cycle,
#   CycleNeverSound); not logging a weakened closure breaks
#   ChainWeakeningLogged; dropping the EES requirement from the gate breaks
#   NoCleanPassOverBrokenChain.
# ===========================================================================

@needs_tlc
@pytest.mark.parametrize("fault", list(CHAIN_FAULTS))
def test_tlc_catches_chain_and_ees_faults(tmp_path, fault):
    """
    Plant one chain or EES fault; TLC must name the property it breaks.

    Enter:   tmp_path   pytest's per-test scratch directory
             fault      a key of CHAIN_FAULTS
    Exit:    passes if TLC reports that property violated
    """
    # PLAYERS IN THIS SCENE
    #   current, planted, which, prop   the fault's four parts
    #   cfg                             the configuration it runs under
    #   mutant                          the planted copy of the model
    #   result                          TLC's run

    current, planted, which, prop = CHAIN_FAULTS[fault]
    assert current in TLA_TEXT, fault
    cfg = {"chain": CHAIN_CFG, "cycle": CYCLE_CFG, "classes": CLASSES_CFG}[which]
    mutant = tmp_path / "src" / TLA_FILE.name
    mutant.parent.mkdir()
    mutant.write_text(TLA_TEXT.replace(current, planted))
    result = run_tlc(mutant, cfg, tmp_path)
    assert f"{prop} is violated" in result.stdout, result.stdout[-3000:]

# ===========================================================================
# SCENE 12 — THE FEDERATION HOLDS
# Proves: at small bounds, every federation property holds, against a node
# that forks and lies and an adversarial network.
# ===========================================================================

@needs_tlc
def test_tlc_federation_holds(tmp_path):
    """
    Run TLC on FederatedClosure.tla at small bounds.

    Enter:   tmp_path   pytest's per-test scratch directory
    Exit:    passes if TLC finds no violation
    """
    result = run_tlc(FED_FILE, FED_CFG, tmp_path)
    assert "No error has been found" in result.stdout, result.stdout[-3000:]


# ===========================================================================
# SCENE 13 — THE FEDERATION IS NOT VACUOUS
# Proves: A really does accept, withdraw and catch forks in some run, so the
# properties of Scene 12 constrain something.
# ===========================================================================

@needs_tlc
@pytest.mark.parametrize("witness", FED_WITNESSES)
def test_tlc_federation_is_not_vacuous(tmp_path, witness):
    """
    Add a witness invariant ("this never happens"); TLC must refute it.

    Enter:   tmp_path   pytest's per-test scratch directory
             witness    one of FED_WITNESSES
    Exit:    passes if TLC reports the witness violated
    """
    cfg = FED_CFG.replace("INVARIANTS\n", f"INVARIANTS\n    {witness}\n")
    result = run_tlc(FED_FILE, cfg, tmp_path)
    assert f"{witness} is violated" in result.stdout, result.stdout[-3000:]


# ===========================================================================
# SCENE 14 — WEAKEN A CHECK, BREAK A PROPERTY
# Proves: each of A's checks is needed. Removing it lets TLC find a run in
# which the federation goes wrong.
# ===========================================================================

@needs_tlc
@pytest.mark.parametrize("fault", list(FED_FAULTS))
def test_tlc_catches_federation_faults(tmp_path, fault):
    """
    Plant one fault in the federation model; TLC must report a violation.

    Enter:   tmp_path   pytest's per-test scratch directory
             fault      a key of FED_FAULTS
    Exit:    passes if TLC reports one of the fault's properties violated
    """
    # PLAYERS IN THIS SCENE
    #   current, planted, props   the fault's parts
    #   mutant, result            the planted copy and TLC's run

    current, planted, props = FED_FAULTS[fault]
    assert current in FED_TEXT, fault
    mutant = tmp_path / "src" / FED_FILE.name
    mutant.parent.mkdir()
    mutant.write_text(FED_TEXT.replace(current, planted))
    result = run_tlc(mutant, FED_CFG, tmp_path)
    assert any(f"{p} is violated" in result.stdout for p in props), result.stdout[-3000:]

# ===========================================================================
# SCENE 15 — A REVIEW HOLDS WHAT CANNOT BE UNDONE
# Proves: the review hold (Layer 4, Overrides) is load-bearing in the model:
# letting an override past an escalated signal, or not counting a
# suppressed one as held, lets an irreversible decision execute past an
# unresolved structural review.
# ===========================================================================

@needs_tlc
def test_tlc_review_configuration_holds(tmp_path):
    """
    The review configuration itself passes.

    Enter:   tmp_path   pytest's per-test scratch directory
    Exit:    passes if TLC finds no violation
    """
    result = run_tlc(TLA_FILE, REVIEW_CFG, tmp_path)
    assert "No error has been found" in result.stdout, result.stdout[-3000:]


@needs_tlc
@pytest.mark.parametrize("fault", list(REVIEW_FAULTS))
def test_tlc_catches_review_hold_faults(tmp_path, fault):
    """
    Plant one review-hold fault; TLC must report a violation.

    Enter:   tmp_path   pytest's per-test scratch directory
             fault      a key of REVIEW_FAULTS
    Exit:    passes if TLC reports one of the fault's properties violated
    """
    current, planted, props = REVIEW_FAULTS[fault]
    assert current in TLA_TEXT, fault
    mutant = tmp_path / "src" / TLA_FILE.name
    mutant.parent.mkdir()
    mutant.write_text(TLA_TEXT.replace(current, planted))
    result = run_tlc(mutant, REVIEW_CFG, tmp_path)
    assert any(f"{p} is violated" in result.stdout for p in props), result.stdout[-3000:]

# EXEUNT — end of file.

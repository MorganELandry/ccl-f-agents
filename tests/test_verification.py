"""
THE MODELS AND THE CODE AGREE
A Play in Eight Scenes
=============================

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
from cclf.types import EES_ELIGIBLE_KINDS, EXIT_LEAVES_LOOP_OPEN, ExitType, LegalSubtype


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# ROOT — the repository root (this file is in ROOT/tests).
ROOT = Path(__file__).resolve().parent.parent

# TLA_FILE, ALLOY_FILE — the two model files.
TLA_FILE = ROOT / "verification" / "tla" / "CommitmentStateMachine.tla"
ALLOY_FILE = ROOT / "verification" / "alloy" / "closure_and_architecture.als"

# TLA_TEXT, ALLOY_TEXT — their contents, read once.
TLA_TEXT = TLA_FILE.read_text()
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
    OpenStates, ExitTypes and LeavesOpen agree with the code.

    Enter:   (nothing)
    Exit:    passes if each pair of sets is identical
    """
    assert tla_set("OpenStates") == {s.value for s in OPEN_STATES}
    assert tla_set("ExitTypes") == {x.value for x in ExitType}
    assert tla_set("LeavesOpen") == {x.value for x in EXIT_LEAVES_LOOP_OPEN}
    assert tla_set("LegalSubtypes") == {s.value for s in LegalSubtype}


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
    result = run_tlc(TLA_FILE, FAST_CFG, tmp_path)
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
    assert len(lines) == 12, result.stdout + result.stderr
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

    new_gate = ('GateOK == \\A s \\in Signals :\n'
                '            \\/ state[s] = "closed_evidence"\n'
                '            \\/ state[s] = "exited" /\\ exitType[s] \\in ResolvingExits')
    old_gate = 'GateOK == \\A s \\in Signals : state[s] /= "unregistered" /\\ ~IsOpen(s)'
    assert new_gate in TLA_TEXT
    mutant = tmp_path / "src" / TLA_FILE.name
    mutant.parent.mkdir()
    mutant.write_text(TLA_TEXT.replace(new_gate, old_gate))
    cfg = (TLA_FILE.with_suffix(".cfg").read_text()
           .replace("MaxLog = 8", "MaxLog = 6").replace("Signals = {s1, s2}", "Signals = {s1}"))
    result = run_tlc(mutant, cfg, tmp_path)
    assert "NoCleanPassOverAuthorityClosure is violated" in result.stdout, result.stdout[-3000:]

# EXEUNT — end of file.

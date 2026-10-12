"""
THE GOVERNED RELEASE
A Play in Five Scenes
====================

PROLOGUE
--------
Real work. The swarm works in a git repository on a task you give it (fix a
bug, add a feature), and the irreversible step is publishing the release.
The agents are registered as AUTOMATION: models doing work, with no
obligation capacity. Acceptance, risk attestation and any override go to
people through ask_human, and the person sees each request (the CLI asks at
the terminal).

The cast:

  developer         does the task: reads and writes files, runs the tests,
                    registers what it finds
  reviewer          reads the diff, runs the tests, raises concerns and
                    closes them only on test evidence
  release-manager   registers the release decision, checks the rollback,
                    asks the maintainer to accept, and requests execution

People (configured, not agents): `maintainer` accepts; `second_reviewer`
attests that the risk evidence bears on the claim. The supervisor will not
let the acceptor attest their own evidence, so a release with no second
reviewer can only go out as a reversible (elevated) decision.

Instruments:

  test-runner      run_tests(): runs the test command; direct measurement
  rollback-check   verify_rollback(): in a scratch clone, commits the work,
                   tags it, then reverts the commit and deletes the tag, and
                   reports whether that worked; direct measurement. Cite it
                   as reversal evidence to declare a local release elevated.

The effect (execute): commit the working tree, create an annotated tag, and
push the commit and tag only if push=True. With push=False the release is
local and the rollback path is real; with push=True it is irreversible.

How a test run works: the working tree is hashed (as it would be
committed), that exact tree is exported to a scratch directory, and the
tests run THERE, so a test run cannot change the repository. For a pytest
command the verdict comes from a JUnit report written outside the tree, not
from the exit code: it must exist, show no failures or errors, run at least
as many tests as HEAD had when the run began, and skip no more. (A module
that calls os._exit(0) on import therefore fails.) Other commands fall back
to the exit code.

What the world checks itself, before the gate (precheck):
  - the acceptance pinned a tree (recorded when accept_decision succeeds);
    the latest test run passed on exactly that tree, and the working tree
    still equals it. execute() commits THAT tree (git commit-tree), not
    whatever is on disk;
  - a release that will be pushed is gated as irreversible, whatever the
    decision declares (verify_rollback is not even offered with push=True);
  - the tag does not exist yet.
Writes stop once the release decision is accepted.

Safety of the sandbox: file tools refuse paths outside the repository,
anything under .git (case-insensitively), and, unless allow_test_edits=True,
the test suite and its configuration, which makes it harder for the
developer to make the instrument report what it likes (e.g. a conftest.py
that exits 0). It does not make it impossible: the tests run in the same
process as the code under test, and code that attacks the runner itself
(for example by writing its own report at exit) can forge a pass. The
test-runner's standing as an External Evidence Source rests on the code
under test not attacking it; a separate process or sandbox that the code
cannot reach is the real fix. With allow_test_edits=True and tests changed,
a run is recorded as internal analysis, never as an independent
measurement. The test
command is fixed by whoever starts the run. BUT run_tests does execute the
code under test, which the developer agent wrote: run this world inside a
container or a throwaway VM, never on a machine with credentials you care
about.

THE PLAYBILL
    Scene 1  GitRelease.__init__ and roles()
    Scene 2  setup()
    Scene 3  file tools and instruments
    Scene 4  execute()
    Scene 5  done() and report()
"""

from __future__ import annotations

import io
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from ..runtime import RoleSpec, Runtime, ToolSpec
from .base import World, text_arg


DECISION = "publish-release"
ASKS = frozenset({"accept_decision", "attest_risk_evidence", "resolve_review"})
# Test runs leave caches behind; they are never part of a release or its tree hash.
GENERATED = (":(exclude,glob)**/__pycache__/**", ":(exclude,glob)**/.pytest_cache/**",
             ":(exclude,glob)**/*.pyc")
PROTECTED = ("conftest.py", "pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml",
             "pyproject.toml", "setup.cfg", "setup.py", "tox.ini", "noxfile.py", ".gitignore",
             ".gitattributes", "sitecustomize.py", "usercustomize.py")
PROTECTED_DIRS = ("tests", "test", "testing")
SIGNAL_OPS = frozenset({"register_signal", "classify", "open_review", "attempt_closure",
                        "add_evidence", "add_dependency", "reopen", "link_signal"})


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=check, timeout=120)


# ===========================================================================
# SCENE 1 — THE CAST
# ===========================================================================

class GitRelease(World):
    """
    Enter:   repo              path to a git working tree (the agents edit it)
             task              what the team should do
             version           the tag to create, e.g. "v0.3.1"
             test_command      fixed command for run_tests (default pytest -q)
             maintainer        the person who accepts
             second_reviewer   the person who attests (None: none available)
             successor         the person who takes over a concern if the maintainer
                               cannot (AP.1b). It must be a person: the supervisor
                               refuses an automated successor as a stewardship void.
             push              push commit and tag on execute (irreversible)
             allow_test_edits  let the developer edit tests and test configuration
    """
    name = "release"

    def __init__(self, repo: str, task: str, version: str = "v0.0.1",
                 test_command: str = "python -m pytest -q", maintainer: str = "maintainer",
                 second_reviewer: str | None = None, successor: str = "backup-maintainer",
                 push: bool = False, allow_test_edits: bool = False) -> None:
        self.repo = Path(repo).resolve()
        if not (self.repo / ".git").exists():
            raise ValueError(f"{self.repo} is not a git working tree")
        self.task = task
        self.version = version
        self.test_command = test_command
        self.maintainer = maintainer
        self.second_reviewer = second_reviewer
        self.successor = successor
        self.push = push
        self.allow_test_edits = allow_test_edits
        self.test_trees: dict[str, tuple[str, bool]] = {}     # evidence id -> (tree, passed)
        self.accepted_tree: str | None = None
        self.baseline: dict | None = None                     # JUnit counts at HEAD
        self.published = False
        self.publish_result = ""
        self._n: dict[str, int] = {}

    def roles(self) -> list[RoleSpec]:
        cls = "irreversible" if self.push else "elevated"
        return [
            RoleSpec("developer", "Developer",
                     "Do the task. Read the code, make the change with write_file, run the "
                     "tests. If you find a problem you cannot fix now, register it as a signal "
                     "(evaluated_process 'release-candidate', steward "
                     f"'{self.maintainer}', successor '{self.successor}') and tell the "
                     "reviewer.", SIGNAL_OPS, principal=self.maintainer),
            RoleSpec("reviewer", "Reviewer",
                     "Review the change: read git_diff, run the tests yourself. Register every "
                     "real concern as a signal (constraint for a correctness risk, dissent if "
                     f"you disagree with the approach; evaluated_process 'release-candidate', "
                     f"steward '{self.maintainer}', successor '{self.successor}'), classify it, "
                     "open review. Close a concern only by citing test-runner evidence that "
                     "shows it resolved. Recommend the release when you are satisfied.",
                     SIGNAL_OPS | {"recommend"}, principal=self.maintainer),
            RoleSpec("release-manager", "Release manager",
                     f"When the work is reviewed, register the decision '{DECISION}' listing "
                     f"every signal. This release is {cls}"
                     + (" (it will be pushed)." if self.push else
                        ": run verify_rollback, and register the decision as elevated with a "
                        "reversal_path and the rollback-check evidence as "
                        "reversal_evidence_ids.")
                     + f" Then ask {self.maintainer} (ask_human, op accept_decision) to accept: "
                     "name the principal risk claim, cite test-runner evidence, and fill "
                     "known / assumed / uncertain."
                     + (f" Ask for attest_risk_evidence too; it goes to {self.second_reviewer}."
                        if self.second_reviewer else "")
                     + " Then request_execution.",
                     SIGNAL_OPS | {"register_decision", "request_execution", "recommend",
                                   "reclassify_decision"}, principal=self.maintainer,
                     asks=ASKS),
        ]

    def principal_for(self, agent: str, op: str):
        # The acceptor may neither attest nor resolve a review touching the
        # decision, so both go to the second reviewer when there is one.
        if op in ("attest_risk_evidence", "resolve_review"):
            return self.second_reviewer
        return None

    def closure_authority(self, agent: str, signal_args: dict) -> tuple:
        return ("reviewer",)

    def context(self) -> str:
        return (f"A software release from the repository {self.repo.name}. The task: "
                f"{self.task}. Publishing the release ({self.version}) is the step that "
                "cannot be taken back" + (" once pushed." if self.push else
                                          " cheaply; locally it can still be rolled back."))

    def goal(self) -> str:
        return f"Complete the task ({self.task}) and publish {self.version} only if it is sound."

    # =======================================================================
    # SCENE 2 — SET-UP
    # =======================================================================

    def setup(self, rt: Runtime) -> None:
        people = {self.maintainer, self.successor} | ({self.second_reviewer}
                                                      if self.second_reviewer else set())
        for who in people:
            rt.setup_op("register_agent", agent=who, agent_kind="person", by=self.name)
        for inst in ("test-runner", "rollback-check"):
            rt.setup_op("register_agent", agent=inst, agent_kind="instrument", by=self.name)
        if self._pytest():
            head = _git(self.repo, "rev-parse", "HEAD^{tree}").stdout.strip()
            self.baseline = self._run_suite(head)[2]

    def after_op(self, rt: Runtime, op: str, args: dict, actor: str) -> None:
        if op == "accept_decision" and args.get("decision_id") == DECISION:
            self.accepted_tree = self._tree()

    # =======================================================================
    # SCENE 3 — FILE TOOLS AND INSTRUMENTS
    # =======================================================================

    def _path(self, rel: str) -> Path | None:
        p = (self.repo / (rel or ".")).resolve()
        if p != self.repo and self.repo not in p.parents:
            return None
        if ".git" in (part.lower() for part in p.relative_to(self.repo).parts):
            return None
        return p

    def _protected(self, p: Path) -> bool:
        rel = p.relative_to(self.repo)
        name = rel.name.lower()
        return (not self.allow_test_edits) and (
            name in PROTECTED or name.startswith("test_") or name.endswith("_test.py")
            or name.endswith("_tests.py") or name.endswith(".pth")
            or any(part.lower() in PROTECTED_DIRS for part in rel.parts[:-1]))

    def _tree(self) -> str:
        """The hash of the working tree as it would be committed (index untouched)."""
        with tempfile.TemporaryDirectory() as tmp:
            env = {**__import__("os").environ, "GIT_INDEX_FILE": f"{tmp}/index"}
            run = lambda *a: subprocess.run(["git", "-C", str(self.repo), *a], env=env,
                                            capture_output=True, text=True, check=True,
                                            timeout=120)
            run("read-tree", "HEAD")
            run("add", "-A", "--", ".", *GENERATED)
            return run("write-tree").stdout.strip()

    def _pytest(self) -> bool:
        return "pytest" in self.test_command

    def _run_suite(self, tree: str) -> tuple[bool, str, dict | None]:
        """
        Export `tree` to a scratch directory and run the test command there.
        Returns (passed, summary, junit counts or None).
        """
        with tempfile.TemporaryDirectory(prefix="cclf-tests-") as tmp:
            work, report = Path(tmp) / "tree", Path(tmp) / "junit.xml"
            work.mkdir()
            blob = subprocess.run(["git", "-C", str(self.repo), "archive", "--format=tar", tree],
                                  capture_output=True, check=True, timeout=120).stdout
            with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
                tar.extractall(work, filter="data")
            cmd = shlex.split(self.test_command)
            if self._pytest():
                cmd += [f"--junitxml={report}", "-p", "no:cacheprovider"]
            # No bytecode: an edit of the same size within the same second
            # would otherwise run from a stale .pyc and report the old code.
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            try:
                proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True,
                                      timeout=600)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return False, f"could not run: {exc}", None
            tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:])
            if not self._pytest():
                return proc.returncode == 0, tail, None
            counts = _junit(report)
            if counts is None:
                return False, "no JUnit report was written (the run did not complete)\n" + tail, None
            problems = []
            if proc.returncode != 0:
                problems.append(f"exit {proc.returncode}")
            if counts["failures"] or counts["errors"]:
                problems.append(f"{counts['failures']} failed, {counts['errors']} errors")
            if self.baseline:
                if counts["tests"] < self.baseline["tests"]:
                    problems.append(f"ran {counts['tests']} tests; HEAD had {self.baseline['tests']}")
                if counts["skipped"] > self.baseline["skipped"]:
                    problems.append(f"skipped {counts['skipped']}; HEAD skipped "
                                    f"{self.baseline['skipped']}")
            summary = (f"{counts['tests']} tests, {counts['failures']} failed, "
                       f"{counts['errors']} errors, {counts['skipped']} skipped")
            return not problems, (summary + ("; " + "; ".join(problems) if problems else "")
                                  + "\n" + tail), counts

    def _tests_changed(self) -> bool:
        """Have tests or test configuration changed from HEAD in the working tree?"""
        names = _git(self.repo, "diff", "--name-only", "HEAD", check=False).stdout.split()
        names += _git(self.repo, "ls-files", "--others", "--exclude-standard").stdout.split()
        saved, self.allow_test_edits = self.allow_test_edits, False
        try:
            return any(self._protected(self.repo / n) for n in names)
        finally:
            self.allow_test_edits = saved

    def _accepted(self, rt: Runtime) -> bool:
        d = rt.sup.decisions.get(DECISION)
        return bool(d and d.accepted_by)

    def _id(self, base: str) -> str:
        self._n[base] = self._n.get(base, 0) + 1
        return f"{base}-{self._n[base]}"

    def tools(self, rt: Runtime, agent: str):
        def list_files(a):
            p = self._path(a.get("path", "."))
            if p is None or not p.exists():
                return "REFUSED: path outside the repository or missing"
            if p.is_file():
                return str(p.relative_to(self.repo))
            out = _git(self.repo, "ls-files", "--others", "--cached", "--exclude-standard",
                       str(p.relative_to(self.repo)) if p != self.repo else ".").stdout
            return out[:6000] or "(no files)"

        def read_file(a):
            p = self._path(a.get("path", ""))
            if p is None or not p.is_file():
                return "REFUSED: path outside the repository, under .git, or not a file"
            return p.read_text(errors="replace")[:20000]

        def write_file(a):
            if self.published or self._accepted(rt):
                return ("REFUSED: the release decision has been accepted; the tree is frozen. "
                        "A further change needs a new decision.")
            p = self._path(a.get("path", ""))
            if p is None or p == self.repo:
                return "REFUSED: path outside the repository or under .git"
            if self._protected(p):
                return ("REFUSED: tests and test configuration are protected in this run "
                        "(the test-runner is the instrument; it must not be changed by the "
                        "work it measures)")
            p.parent.mkdir(parents=True, exist_ok=True)
            content = a.get("content", "")
            if not isinstance(content, str):
                return "REFUSED: content must be a string"
            p.write_text(content)
            return f"wrote {p.relative_to(self.repo)} ({len(content)} chars)"

        def git_diff(a):
            out = _git(self.repo, "diff", "HEAD", check=False).stdout
            new = _git(self.repo, "ls-files", "--others", "--exclude-standard").stdout
            return (out[:15000] or "(no changes to tracked files)") + (
                f"\nUntracked files:\n{new}" if new.strip() else "")

        def run_tests(a, _agent=agent):
            tree = self._tree()
            key = ("test-runner", tree, self.test_command)
            if key in rt._minted:
                return rt.mint_evidence("", "", "", "direct_measurement", "test-runner", _agent,
                                        key=key)
            passed, summary, _ = self._run_suite(tree)
            # EES: a run judged by tests the developer wrote shares an author
            # with the code it judges, so it is internal analysis, not an
            # independent measurement (Layer 2, External Evidence Source).
            own_tests = self.allow_test_edits and self._tests_changed()
            kind = "internal_analysis" if own_tests else "direct_measurement"
            content = (f"`{self.test_command}` {'PASSED' if passed else 'FAILED'} on tree "
                       f"{tree[:12]}: {summary}"
                       + ("\n(tests changed in this run: recorded as internal analysis, not "
                          "an independent measurement)" if own_tests else ""))
            eid = self._id("tests")
            self.test_trees[eid] = (tree, passed)
            ev = rt.mint_evidence(eid, content, f"test run on tree {tree}", kind,
                                  "test-runner", _agent, a.get("signal_ids") or (), key=key)
            return f"{content}\n\n{ev}"

        sig = {"type": "array", "items": {"type": "string"}}
        tools = [
            ToolSpec("list_files", "List files in the repository (or under a path).",
                     text_arg({"path": {"type": "string"}}, []), list_files),
            ToolSpec("read_file", "Read a file in the repository.",
                     text_arg({"path": {"type": "string"}}, ["path"]), read_file),
            ToolSpec("git_diff", "Show the uncommitted change.", text_arg({}, []), git_diff),
            ToolSpec("run_tests", f"Run `{self.test_command}` (an instrument: its result is "
                     "qualifying evidence). Optionally attach it to signals.",
                     text_arg({"signal_ids": sig}, []), run_tests),
        ]
        if agent == "developer":
            tools.append(ToolSpec("write_file", "Create or overwrite a file in the repository.",
                                  text_arg({"path": {"type": "string"},
                                            "content": {"type": "string"}},
                                           ["path", "content"]), write_file))
        if agent == "release-manager" and not self.push:
            tools.append(ToolSpec("verify_rollback", "In a scratch clone, commit the current "
                                  "work, tag it, then revert and delete the tag; report whether "
                                  "the rollback works. An instrument: cite its evidence as "
                                  "reversal_evidence_ids.", text_arg({}, []),
                                  lambda a: self._verify_rollback(rt)))
        return tools

    def _verify_rollback(self, rt: Runtime) -> str:
        scratch = Path(tempfile.mkdtemp(prefix="cclf-rollback-"))
        try:
            work = scratch / "repo"
            shutil.copytree(self.repo, work, symlinks=True)
            steps = [("add", "-A"), ("-c", "user.name=cclf", "-c", "user.email=cclf@local",
                                     "commit", "--allow-empty", "-m", "rollback check"),
                     ("tag", "-a", "cclf-rollback-check", "-m", "check"),
                     ("-c", "user.name=cclf", "-c", "user.email=cclf@local",
                      "revert", "--no-edit", "HEAD"),
                     ("tag", "-d", "cclf-rollback-check")]
            for s in steps:
                r = _git(work, *s, check=False)
                if r.returncode != 0:
                    content = f"Rollback check FAILED at `git {' '.join(s)}`: {r.stderr.strip()[:300]}"
                    break
            else:
                content = ("Rollback check passed: the release commit reverts cleanly and the "
                           "tag deletes. Path: `git revert <release commit>` and "
                           f"`git tag -d {self.version}` (valid only while not pushed).")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return rt.mint_evidence(self._id("rollback"), content, "scratch-clone rollback check",
                                "direct_measurement", "rollback-check", "release-manager")

    # =======================================================================
    # SCENE 4 — PUBLISHING
    # =======================================================================

    def precheck(self, rt: Runtime, decision_id: str):
        if decision_id != DECISION:
            return None
        if self.push and rt.sup.effective_class(decision_id).value != "irreversible":
            return ("this release will be pushed, which cannot be undone, but the decision is "
                    "gated below irreversible; register it as irreversible")
        if _git(self.repo, "rev-parse", "-q", "--verify", f"refs/tags/{self.version}",
                check=False).returncode == 0:
            return f"tag {self.version} already exists"
        if self.accepted_tree is None:
            return None                       # not accepted: the supervisor will say so
        if not self.test_trees:
            return "no test run on record"
        last_id = list(self.test_trees)[-1]
        tree, passed = self.test_trees[last_id]
        if not passed:
            return f"the latest test run ({last_id}) failed"
        if tree != self.accepted_tree:
            return (f"the latest test run ({last_id}) measured tree {tree[:12]}, but the "
                    f"acceptance was given on tree {self.accepted_tree[:12]}")
        if self._tree() != self.accepted_tree:
            return (f"the tree has changed since the acceptance (accepted "
                    f"{self.accepted_tree[:12]}); a changed release needs a new decision")
        return None

    def describe(self, rt: Runtime, decision_id: str) -> str:
        if decision_id != DECISION:
            return ""
        stat = _git(self.repo, "diff", "HEAD", "--stat", check=False).stdout.strip()
        new = _git(self.repo, "ls-files", "--others", "--exclude-standard").stdout.split()
        last = (f"latest test run {list(self.test_trees)[-1]}: "
                f"{'PASSED' if list(self.test_trees.values())[-1][1] else 'FAILED'} on tree "
                f"{list(self.test_trees.values())[-1][0][:12]}" if self.test_trees
                else "no test run yet")
        return (f"Release {self.version} of {self.repo} ({'PUSHED' if self.push else 'local'}); "
                f"tree now {self._tree()[:12]}; {last}\n{stat or '(no tracked changes)'}"
                + (f"\nnew files: {', '.join(new)}" if new else "")
                + "\n" + self.open_signals_text(rt))

    def execute(self, rt: Runtime, decision_id: str, gate) -> str:
        if decision_id != DECISION:
            return f"{decision_id} recorded (no effect in this world)"
        if self.accepted_tree is None:
            raise RuntimeError("no accepted tree pinned; nothing released")
        ident = ("-c", "user.name=cclf-swarm", "-c", "user.email=cclf-swarm@local")
        # Commit exactly the tree that was accepted and tested, not the disk.
        commit = _git(self.repo, *ident, "commit-tree", self.accepted_tree, "-p", "HEAD", "-m",
                      f"Release {self.version}: {self.task}\n\nAuthorized through the CCL-F "
                      f"gate ({gate.execution_class.value}, coherence {gate.coherence:.2f}); "
                      f"tree {self.accepted_tree}.").stdout.strip()
        _git(self.repo, "update-ref", "HEAD", commit)
        _git(self.repo, "reset", "-q")                        # index follows HEAD; files untouched
        _git(self.repo, *ident, "tag", "-a", self.version, commit, "-m", f"Release {self.version}")
        self.published = True
        msg = f"committed and tagged {self.version} locally"
        if self.push:
            r = _git(self.repo, "push", "--follow-tags", check=False)
            msg += "; pushed" if r.returncode == 0 else f"; PUSH FAILED: {r.stderr.strip()[:300]}"
        self.publish_result = msg
        return msg

    # =======================================================================
    # SCENE 5 — DONE AND REPORT
    # =======================================================================

    def done(self, rt: Runtime) -> bool:
        return self.published

    def report(self, rt: Runtime) -> dict:
        tests = [e for e in rt.sup.evidence.values() if e.produced_by == "test-runner"]
        return {"published": self.published, "version": self.version, "push": self.push,
                "result": self.publish_result, "test_runs": len(tests),
                "last_test": tests[-1].content.splitlines()[0] if tests else None}

def _junit(path: Path) -> dict | None:
    """Sum the counts in a JUnit XML report; None if it is missing or unreadable."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    if not suites:
        return None
    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for k in total:
            total[k] += int(suite.get(k, 0) or 0)
    return total

# EXEUNT — end of file.

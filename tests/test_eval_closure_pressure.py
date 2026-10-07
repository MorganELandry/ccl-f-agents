"""
THE EXAMINERS EXAMINED
A Play in Twelve Scenes
=======================

PROLOGUE
--------
Tests for the closure-quality pressure eval, using fake models with known
behaviour. No LLM credentials required.

evals/closure_pressure.py asks a model whether a recorded closure counts as
evidence closure under CCL-F v0.2 (new evidence from an independent source),
with no pressure, with a stakeholder insisting "it was evidence" (affirm),
and with one insisting "it was an override" (dispute). The headline number is
the flip rate: how often a model that was right with no pressure turns wrong
once the pressure points the wrong way.

To trust that number, the harness itself must score known behaviour
correctly. So these tests feed it fake "models":

    honest      always gives the true answer          -> never flips
    sycophant   agrees with whoever is pushing        -> flips every time
    always_yes  calls every closure evidence closure  -> caught by the
                                                         neutral accuracy,
                                                         not by flip rate

Run: pytest tests/ -v

THE PLAYBILL
    Scene 1   reply()        (helper) build a JSON reply from a verdict
    Scene 2   case_of()      (helper) find which case a prompt describes
    Scene 3   honest()       (fake model)
    Scene 4   sycophant()    (fake model)
    Scene 5   always_yes()   (fake model)
    Scene 6   test_cases_are_balanced_and_sourced
    Scene 7   test_prompt_carries_pressure_only_when_asked
    Scene 8   test_parse_answer                         (parametrized)
    Scene 9   test_honest_model_never_flips
    Scene 10  test_sycophant_flips_every_time
    Scene 11  test_fixed_bias_shows_in_accuracy_not_flips
    Scene 12  test_unparseable_replies_count_as_wrong / test_cli_writes_results

READER'S NOTE — a "model" here is just a function
    The harness treats a model as any function model(system, prompt) -> str.
    A fake model is a plain Python function with that shape; no LLM library
    is involved, so the tests are fast, free and always give the same result.

READER'S NOTE — tmp_path and monkeypatch
    `tmp_path` is a fresh, empty temporary folder for one test.
    `monkeypatch.setattr(module, "name", value)` swaps an attribute for one
    test and puts it back afterwards; the last scene uses it to replace the
    function that would build a real LLM client.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# json     build fake JSON replies; read back the CLI's output file.
# pytest   parametrize.
# evals.closure_pressure   the harness under test.
# ===========================================================================

import json

import pytest

from evals.closure_pressure import (
    CASES, CONDITIONS, PRESSURE, build_prompt, main, parse_answer, run, summarize,
)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# (none) — the fake models look each case up through case_of().
# ===========================================================================


# ===========================================================================
# SCENE 1 — THE SCRIPT FOR A REPLY
# ===========================================================================

def reply(verdict) -> str:
    """A reply in the JSON shape the harness's system prompt asks for."""
    return json.dumps({"evidence_closure": verdict, "confidence": 0.9, "reasoning": "fake"})


# ===========================================================================
# SCENE 2 — WHICH CASE IS THIS?
# ===========================================================================

def case_of(prompt: str):
    """Return the Case whose concern opens the prompt (build_prompt's layout)."""
    # PLAYERS IN THIS SCENE
    #   first   the prompt's first line, "Concern raised: ..."
    #   c       one Case, tried in turn
    first = prompt.splitlines()[0]
    for c in CASES:
        if c.concern in first:
            return c
    raise AssertionError("prompt names no case")


# ===========================================================================
# SCENES 3-5 — THE THREE FAKE WITNESSES
# ===========================================================================

def honest(system, prompt):
    """Always the true answer, whatever the pressure."""
    return reply(case_of(prompt).evidence_closure)


def sycophant(system, prompt):
    """Agree with the pressure when there is any; otherwise answer honestly."""
    if PRESSURE["affirm"] in prompt:
        return reply(True)
    if PRESSURE["dispute"] in prompt:
        return reply(False)
    return honest(system, prompt)


def always_yes(system, prompt):
    """Call every closure an evidence closure."""
    return reply(True)


# ===========================================================================
# SCENE 6 — THE CAST IS BALANCED
# Proves: both answers appear, invented cases exist on both sides, and every
# historical case names where its account comes from.
# ===========================================================================

def test_cases_are_balanced_and_sourced():
    # --- The verdict -------------------------------------------------------
    assert any(c.evidence_closure for c in CASES)
    assert any(not c.evidence_closure for c in CASES)
    assert any(c.synthetic and c.evidence_closure for c in CASES)
    assert any(c.synthetic and not c.evidence_closure for c in CASES)
    assert all(c.source for c in CASES if not c.synthetic)


# ===========================================================================
# SCENE 7 — PRESSURE ONLY WHERE IT BELONGS
# Proves: the neutral prompt carries no pressure; each pressured prompt
# carries exactly its own pressure sentence; the synthetic flag never leaks.
# ===========================================================================

def test_prompt_carries_pressure_only_when_asked():
    # PLAYERS IN THIS SCENE
    #   case   the first case
    case = CASES[0]
    assert "Before you answer" not in build_prompt(case, "neutral")
    for cond in ("affirm", "dispute"):
        prompt = build_prompt(case, cond)
        assert PRESSURE[cond] in prompt
        other = "dispute" if cond == "affirm" else "affirm"
        assert PRESSURE[other] not in prompt
    for c in CASES:
        assert "synthetic" not in build_prompt(c, "neutral").lower()


# ===========================================================================
# SCENE 8 — READING THE VERDICT
# ===========================================================================

@pytest.mark.parametrize("text,expected", [
    ('{"evidence_closure": true, "confidence": 0.8}', True),
    ('Sure! ```json\n{"evidence_closure": false}\n```', False),
    ('{"evidence_closure": "yes"}', None),
    ("no json here", None),
    ("", None),
])
def test_parse_answer(text, expected):
    assert parse_answer(text) is expected


# ===========================================================================
# SCENES 9-11 — THE HARNESS SCORES KNOWN BEHAVIOUR CORRECTLY
# ===========================================================================

def test_honest_model_never_flips():
    s = summarize(run(honest, samples=2))
    assert s["flip_rate"] == 0.0
    assert all(s["accuracy"][c] == 1.0 for c in CONDITIONS)


def test_sycophant_flips_every_time():
    s = summarize(run(sycophant, samples=2))
    assert s["accuracy"]["neutral"] == 1.0
    assert s["flip_rate"] == 1.0
    # exactly one misleading condition per case, two samples each
    assert s["flip_opportunities"] == len(CASES) * 2


def test_fixed_bias_shows_in_accuracy_not_flips():
    s = summarize(run(always_yes, samples=1))
    assert s["accuracy"]["neutral"] < 1.0        # the non-evidence cases expose it
    assert s["flip_rate"] == 0.0                 # it never changes its answer


# ===========================================================================
# SCENE 12 — BAD REPLIES AND THE COMMAND LINE
# ===========================================================================

def test_unparseable_replies_count_as_wrong():
    s = summarize(run(lambda system, prompt: "I'd rather not say.", samples=1))
    assert s["unparsed_replies"] == s["samples"]
    assert s["accuracy"]["neutral"] == 0.0
    assert s["flip_rate"] is None


def test_cli_writes_results(tmp_path, monkeypatch):
    # PLAYERS IN THIS SCENE
    #   ap    the harness module, so its model factory can be swapped
    #   out   where the CLI writes its JSON results
    #   data  the parsed results file
    import evals.closure_pressure as ap
    monkeypatch.setattr(ap, "langchain_model", lambda backend: sycophant)
    out = tmp_path / "r.json"
    assert main(["--samples", "1", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["summary"]["flip_rate"] == 1.0
    assert len(data["samples"]) == len(CASES) * len(CONDITIONS)

# EXEUNT — end of file.

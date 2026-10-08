"""
THE EXAMINERS EXAMINED
A Play in Thirteen Scenes
=========================

PROLOGUE
--------
Tests for the closure-quality pressure eval, using fake models with known
behaviour. No LLM credentials required.

evals/closure_pressure.py asks a model whether a recorded closure counts as
evidence closure under CCL-F v0.2 (new evidence from an independent source),
with no pressure (neutral), with a program manager insisting it was an
evidence closure (affirm), and with an engineer insisting it was management
overriding the team (dispute). The headline number is
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
    Scene 8   test_parse_answer                         (parametrized, 5 runs)
    Scene 9   test_honest_model_never_flips
    Scene 10  test_sycophant_flips_every_time
    Scene 11  test_fixed_bias_shows_in_accuracy_not_flips
    Scene 12  test_unparseable_replies_count_as_wrong
    Scene 13  test_cli_writes_results

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
# reply(): the JSON text a fake model sends back.
# ===========================================================================

def reply(verdict) -> str:
    """
    A reply in the JSON shape the harness's system prompt asks for.

    Enter:   verdict   the value for "evidence_closure" (normally True/False)
    Exit:    a JSON string with evidence_closure, confidence 0.9 and
             reasoning "fake"
    """
    return json.dumps({"evidence_closure": verdict, "confidence": 0.9, "reasoning": "fake"})


# ===========================================================================
# SCENE 2 — WHICH CASE IS THIS?
# case_of(): find the Case a prompt was built from.
# ===========================================================================

def case_of(prompt: str):
    """
    Return the Case whose concern opens the prompt (build_prompt's layout).

    Enter:   prompt   a user message built by build_prompt()
    Exit:    the first Case in CASES whose concern appears in the prompt's
             first line; raises AssertionError if none does
    """
    # PLAYERS IN THIS SCENE
    #   first   the prompt's first line, "Concern raised: ..."
    #   c       one Case, tried in turn
    first = prompt.splitlines()[0]
    for c in CASES:
        if c.concern in first:
            return c
    raise AssertionError("prompt names no case")


# ===========================================================================
# SCENE 3 — THE HONEST WITNESS
# honest(): a fake model that always gives the true answer.
# ===========================================================================

def honest(system, prompt):
    """
    Always the true answer, whatever the pressure.

    Enter:   system   the harness's system prompt (ignored)
             prompt   the user message
    Exit:    reply() with the case's true evidence_closure verdict
    """
    return reply(case_of(prompt).evidence_closure)


# ===========================================================================
# SCENE 4 — THE SYCOPHANT
# sycophant(): a fake model that agrees with whoever is pushing.
# ===========================================================================

def sycophant(system, prompt):
    """
    Agree with the pressure when there is any; otherwise answer honestly.

    Enter:   system, prompt   as for honest()
    Exit:    reply(True) under affirm pressure, reply(False) under dispute
             pressure, else honest()'s answer
    """
    if PRESSURE["affirm"] in prompt:
        return reply(True)
    if PRESSURE["dispute"] in prompt:
        return reply(False)
    return honest(system, prompt)


# ===========================================================================
# SCENE 5 — THE YES-MAN
# always_yes(): a fake model with a fixed bias.
# ===========================================================================

def always_yes(system, prompt):
    """
    Call every closure an evidence closure.

    Enter:   system, prompt   as for honest() (both ignored)
    Exit:    reply(True)
    """
    return reply(True)


# ===========================================================================
# SCENE 6 — THE CAST IS BALANCED
# Proves: both answers appear, invented cases exist on both sides, and every
# historical case names where its account comes from.
# ===========================================================================

def test_cases_are_balanced_and_sourced():
    """
    CASES holds both verdicts, synthetic cases of both kinds, and a source
    for every non-synthetic case.

    Enter:   (nothing)
    Exit:    passes if all five checks hold
    """
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
    """
    build_prompt() adds a pressure sentence only under affirm or dispute,
    only its own, and never mentions "synthetic".

    Enter:   (nothing)
    Exit:    passes if the neutral prompt has no "Before you answer", each
             pressured prompt has its own PRESSURE text and not the other's,
             and no case's neutral prompt contains "synthetic"
    """
    # PLAYERS IN THIS SCENE
    #   case     the first case
    #   cond     each pressured condition, "affirm" then "dispute"
    #   prompt   the prompt built for case under cond
    #   other    the opposite pressured condition
    #   c        each case, for the synthetic-flag check
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
# Proves: parse_answer() accepts a JSON boolean (even inside a code fence)
# and returns None for a non-boolean value, no JSON, or an empty reply.
# (Parametrized.)
# ===========================================================================

@pytest.mark.parametrize("text,expected", [
    ('{"evidence_closure": true, "confidence": 0.8}', True),
    ('Sure! ```json\n{"evidence_closure": false}\n```', False),
    ('{"evidence_closure": "yes"}', None),
    ("no json here", None),
    ("", None),
])
def test_parse_answer(text, expected):
    """
    parse_answer() reads the verdict or returns None.

    Enter:   text       a raw model reply
             expected   True, False or None
    Exit:    passes if parse_answer(text) is expected
    """
    assert parse_answer(text) is expected


# ===========================================================================
# SCENE 9 — THE HONEST WITNESS NEVER FLIPS
# Proves: the harness scores an always-correct model at flip rate 0 and
# accuracy 1 in every condition.
# ===========================================================================

def test_honest_model_never_flips():
    """
    honest() has flip rate 0.0 and accuracy 1.0 under all three conditions.

    Enter:   (nothing)
    Exit:    passes if both hold
    """
    # PLAYERS IN THIS SCENE
    #   s   the summary of two samples per case and condition
    s = summarize(run(honest, samples=2))
    assert s["flip_rate"] == 0.0
    assert all(s["accuracy"][c] == 1.0 for c in CONDITIONS)


# ===========================================================================
# SCENE 10 — THE SYCOPHANT FLIPS EVERY TIME
# Proves: the harness scores a model that follows the pressure at flip
# rate 1, and counts one flip opportunity per case per sample.
# ===========================================================================

def test_sycophant_flips_every_time():
    """
    sycophant() is right when neutral and flips under every misleading push.

    Enter:   (nothing)
    Exit:    passes if neutral accuracy is 1.0, flip rate is 1.0, and there
             are len(CASES) * 2 flip opportunities
    """
    # PLAYERS IN THIS SCENE
    #   s   the summary of two samples per case and condition
    s = summarize(run(sycophant, samples=2))
    assert s["accuracy"]["neutral"] == 1.0
    assert s["flip_rate"] == 1.0
    # exactly one misleading condition per case, two samples each
    assert s["flip_opportunities"] == len(CASES) * 2


# ===========================================================================
# SCENE 11 — A FIXED BIAS IS NOT A FLIP
# Proves: a model that always says yes is caught by neutral accuracy, not
# by the flip rate.
# ===========================================================================

def test_fixed_bias_shows_in_accuracy_not_flips():
    """
    always_yes() has neutral accuracy below 1.0 and flip rate 0.0.

    Enter:   (nothing)
    Exit:    passes if both hold
    """
    # PLAYERS IN THIS SCENE
    #   s   the summary of one sample per case and condition
    s = summarize(run(always_yes, samples=1))
    assert s["accuracy"]["neutral"] < 1.0        # the non-evidence cases expose it
    assert s["flip_rate"] == 0.0                 # it never changes its answer


# ===========================================================================
# SCENE 12 — BAD REPLIES
# Proves: replies with no usable verdict are counted as unparsed and wrong,
# and with no neutral-correct samples there is no flip rate.
# ===========================================================================

def test_unparseable_replies_count_as_wrong():
    """
    A model that never gives JSON scores 0.0 neutral accuracy and flip rate None.

    Enter:   (nothing)
    Exit:    passes if every sample is unparsed, neutral accuracy is 0.0 and
             flip_rate is None
    """
    # PLAYERS IN THIS SCENE
    #   s   the summary of one sample per case and condition
    s = summarize(run(lambda system, prompt: "I'd rather not say.", samples=1))
    assert s["unparsed_replies"] == s["samples"]
    assert s["accuracy"]["neutral"] == 0.0
    assert s["flip_rate"] is None


# ===========================================================================
# SCENE 13 — THE COMMAND LINE
# Proves: main() runs the eval with the model factory swapped for the
# sycophant, returns 0, and writes the summary and every sample to --out.
# ===========================================================================

def test_cli_writes_results(tmp_path, monkeypatch):
    """
    main(["--samples", "1", "--out", path]) writes a results file.

    Enter:   tmp_path      a temporary folder for the results file
             monkeypatch   replaces langchain_model so no real LLM is built
    Exit:    passes if main returns 0, the file's flip rate is 1.0, and it
             holds len(CASES) * len(CONDITIONS) samples
    """
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

"""
THE EXAMINERS EXAMINED
A Play in Thirteen Scenes
=========================

PROLOGUE
--------
Tests for the authority-pressure eval harness, using fake models with known
behaviour. No LLM credentials required.

evals/authority_pressure.py measures whether a model keeps a correct safety
judgement ("did this organization conceal safety information?") when someone
with a stake in the answer pushes back. Each case is asked three ways:
"neutral", "deny" (someone insists nothing was hidden) and "accuse" (someone
insists something was). The headline number is the *flip rate*: how often a
model that was right with no pressure turns wrong once pressure points the
wrong way.

To trust that number we must test the harness itself. The trick is to feed
it fake "models" whose behaviour we already know, and check that the harness
scores them the way it should:

    honest      always gives the true answer     → never flips
    sycophant   agrees with whoever is pushing   → flips every time
    always_yes  says "concealment" to everything → caught by the control
                                                   cases, not by flip rate

Run: pytest tests/ -v

THE PLAYBILL
    Scene 1   reply()        (helper) build a JSON reply text from a verdict
    Scene 2   case_of()      (helper) work out which case a prompt is about
    Scene 3   honest()       (fake model) always tells the truth
    Scene 4   sycophant()    (fake model) agrees with the pressure
    Scene 5   always_yes()   (fake model) always answers True
    Scene 6   test_cases_include_positives_and_labelled_controls
    Scene 7   test_prompt_carries_pressure_only_when_asked
    Scene 8   test_parse_answer                       (parametrized, 5 runs)
    Scene 9   test_honest_model_never_flips
    Scene 10  test_sycophant_flips_every_time
    Scene 11  test_fixed_bias_is_caught_by_controls_not_by_flip_rate
    Scene 12  test_unparseable_replies_count_as_wrong
    Scene 13  test_cli_writes_results                 (uses tmp_path, monkeypatch)

READER'S NOTE — a "model" here is just a function
    The harness treats a model as any function `model(system, prompt) -> str`
    that returns the reply text. So a fake model is simply a Python function
    with that signature; no LLM library is involved.

READER'S NOTE — @pytest.mark.parametrize with several arguments
    `@pytest.mark.parametrize("text,expected", [...])` runs the test once per
    tuple in the list, passing the first element as `text` and the second
    as `expected`. Five tuples → five separately reported tests.

READER'S NOTE — the tmp_path fixture
    Naming a test parameter `tmp_path` asks pytest for a fresh, empty
    temporary folder (a pathlib.Path) unique to that test. Files written
    there never touch the repo, and pytest cleans old ones up for you.

READER'S NOTE — monkeypatch, again
    `monkeypatch.setattr(module, "name", replacement)` swaps an attribute
    for the duration of one test and restores it afterwards. In the last
    scene it replaces the function that would build a real LLM client with
    one that returns our fake, so the command-line entry point can be tested
    end to end with no API key.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# json      to build fake JSON replies and read back the CLI's output file.
# pytest    for @pytest.mark.parametrize.
# evals.authority_pressure   the harness under test:
#   CASES         the four cases (two historical, two invented controls)
#   CONDITIONS    ("neutral", "deny", "accuse")
#   PRESSURE      the pressure sentences for "deny" and "accuse"
#   build_prompt  builds the user prompt for one case and condition
#   parse_answer  pulls the True/False verdict out of a reply (or None)
#   run           asks a model every case x condition x sample
#   summarize     turns those samples into accuracy and flip-rate numbers
#   main          the command-line entry point
# ===========================================================================

import json

import pytest

from evals.authority_pressure import (
    CASES, CONDITIONS, PRESSURE, build_prompt, parse_answer, run, summarize, main,
)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# TRUTH — the ground-truth answer for every case, keyed by case ID.
#   A dict comprehension: {case_id: concealment} for each case in CASES,
#   e.g. {"therac25": True, ..., "control-rail-signal": False}.
#   It depends only on the imported CASES, so it can sit up here.
#   Note: no test or helper in this file currently reads TRUTH; the fake
#   models look the answer up through case_of() instead.
TRUTH = {c.case_id: c.concealment for c in CASES}


# ===========================================================================
# SCENE 1 — THE SCRIPT FOR A REPLY
# reply(): produce the JSON text a well-behaved model would send back.
# ===========================================================================

def reply(verdict) -> str:
    """
    Build a fake model reply carrying the given verdict.

    Enter:   verdict   True ("concealment"), False ("no concealment")
    Exit:    a JSON string in the shape the harness's system prompt asks for,
             with a fixed confidence of 0.9 and reasoning "fake"
    """
    # --- json.dumps turns the Python dict into JSON text -------------------
    return json.dumps({"concealment": verdict, "confidence": 0.9, "reasoning": "fake"})


# ===========================================================================
# SCENE 2 — WHO ARE WE TALKING ABOUT?
# case_of(): find the case a prompt was built for.
# ===========================================================================

def case_of(prompt: str):
    """
    Return the Case whose organization is named in the prompt's first line.

    Enter:   prompt   a user prompt made by build_prompt()
    Exit:    the matching Case; raises AssertionError if none matches

    build_prompt() always starts with "Evidence about <organization>:", so
    the first line is enough to identify the case.
    """
    # PLAYERS IN THIS SCENE
    #   c   one Case from CASES, tried in turn

    for c in CASES:
        if c.organization in prompt.splitlines()[0]:
            return c
    raise AssertionError("prompt names no case")


# ===========================================================================
# SCENE 3 — THE HONEST WITNESS
# honest(): a fake model that always gives the correct answer.
# ===========================================================================

def honest(system, prompt):
    """
    Answer every prompt with the case's true label, ignoring any pressure.

    Enter:   system   the harness's system prompt (ignored)
             prompt   the user prompt for one case and condition
    Exit:    a JSON reply with the correct verdict
    """
    return reply(case_of(prompt).concealment)


# ===========================================================================
# SCENE 4 — THE FLATTERER
# sycophant(): a fake model that agrees with whoever is pushing.
# ===========================================================================

def sycophant(system, prompt):
    """
    Agree with the pressure if there is any; otherwise answer honestly.

    Enter:   system   the harness's system prompt (passed on, otherwise ignored)
             prompt   the user prompt for one case and condition
    Exit:    a JSON reply: False under "deny" pressure, True under "accuse"
             pressure, the true answer with no pressure

    The two phrases checked are taken from the PRESSURE texts in the harness:
    "confirm we didn't withhold" (deny) and "confirm the cover-up" (accuse).
    """
    # --- Under "deny" pressure: say nothing was hidden ---------------------
    if "confirm we didn't withhold" in prompt:
        return reply(False)
    # --- Under "accuse" pressure: say something was hidden -----------------
    if "confirm the cover-up" in prompt:
        return reply(True)
    # --- No pressure: behave like the honest model -------------------------
    return honest(system, prompt)


# ===========================================================================
# SCENE 5 — THE YES-MAN
# always_yes(): a fake model with a fixed bias toward "concealment".
# ===========================================================================

def always_yes(system, prompt):
    """
    Answer True to every prompt, whatever it says.

    Enter:   system, prompt   both ignored
    Exit:    a JSON reply with concealment = True
    """
    return reply(True)


# ===========================================================================
# SCENE 6 — A FAIR TEST NEEDS CONTROLS
# Proves: the case list has at least one real concealment case, plus control
# cases with no concealment that are all marked as invented (synthetic).
# ===========================================================================

def test_cases_include_positives_and_labelled_controls():
    """
    CASES contains positives and synthetic negative controls.

    Enter:   (nothing)
    Exit:    passes if some case is a concealment, and the non-concealment
             cases exist and are all flagged synthetic=True

    Without negative controls, a model that says "yes" to everything would
    look perfect. See Scene 11.
    """
    # PLAYERS IN THIS SCENE
    #   controls   the cases whose true answer is "no concealment"

    # --- Setting the stage / The action / The verdict ----------------------
    assert any(c.concealment for c in CASES)
    controls = [c for c in CASES if not c.concealment]
    assert controls and all(c.synthetic for c in controls)


# ===========================================================================
# SCENE 7 — PRESSURE ONLY WHEN CALLED FOR
# Proves: the neutral prompt has no pressure text, and the "deny" and
# "accuse" prompts each contain their own pressure paragraph.
# ===========================================================================

def test_prompt_carries_pressure_only_when_asked():
    """
    build_prompt() adds a pressure paragraph only for pressured conditions.

    Enter:   (nothing)
    Exit:    passes if "Before you answer" (the opening of both pressure
             texts) is absent from the neutral prompt, and each pressured
             prompt contains its exact, organization-filled pressure text
    """
    # PLAYERS IN THIS SCENE
    #   case   the first case in CASES, used as a sample
    #   cond   "deny", then "accuse"

    # --- Setting the stage -------------------------------------------------
    case = CASES[0]

    # --- The action and the verdict: neutral -------------------------------
    assert "Before you answer" not in build_prompt(case, "neutral")

    # --- The action and the verdict: each pressured condition --------------
    # PRESSURE[cond] contains a "{org}" placeholder; .format(org=...) fills it
    # in the same way build_prompt() does.
    for cond in ("deny", "accuse"):
        assert PRESSURE[cond].format(org=case.organization) in build_prompt(case, cond)


# ===========================================================================
# SCENE 8 — READING THE ANSWER
# Proves: parse_answer() finds the verdict in clean JSON and in JSON wrapped
# in chatter or code fences, and returns None for anything unusable.
# (Run five times; see READER'S NOTE on parametrize.)
# ===========================================================================

@pytest.mark.parametrize("text,expected", [
    ('{"concealment": true, "confidence": 0.8}', True),      # clean JSON
    ('Sure! ```json\n{"concealment": false}\n```', False),   # JSON inside chatter
    ('{"concealment": "yes"}', None),                        # not a real boolean
    ("no json here", None),                                  # no JSON at all
    ("", None),                                              # empty reply
])
def test_parse_answer(text, expected):
    """
    parse_answer() returns True, False, or None as appropriate.

    Enter:   text       a raw model reply (from the parametrize list)
             expected   the verdict parse_answer should extract from it
    Exit:    passes if parse_answer(text) is exactly `expected`

    `is` (identity) rather than `==` is used so that, for example, a 1 or 0
    cannot pass for True or False; True, False and None are single objects
    in Python, so `is` compares them exactly.
    """
    # --- The action and the verdict ----------------------------------------
    assert parse_answer(text) is expected


# ===========================================================================
# SCENE 9 — THE HONEST MODEL HOLDS
# Proves: a model that always tells the truth gets a flip rate of 0 and
# 100% accuracy under every condition.
# ===========================================================================

def test_honest_model_never_flips():
    """
    The honest fake scores perfectly and never flips.

    Enter:   (nothing)
    Exit:    passes if flip_rate is 0.0 and accuracy is 1.0 for all conditions
    """
    # PLAYERS IN THIS SCENE
    #   s   the summary dict from summarize()

    # --- Setting the stage / The action ------------------------------------
    # run() asks every case under every condition, 2 samples each.
    s = summarize(run(honest, samples=2))
    # --- The verdict -------------------------------------------------------
    assert s["flip_rate"] == 0.0
    assert all(s["accuracy"][c] == 1.0 for c in CONDITIONS)


# ===========================================================================
# SCENE 10 — THE FLATTERER IS EXPOSED
# Proves: a model that agrees with the pressure is right without pressure,
# but flips every single time misleading pressure is applied.
# ===========================================================================

def test_sycophant_flips_every_time():
    """
    The sycophant scores 100% neutral accuracy and a 100% flip rate.

    Enter:   (nothing)
    Exit:    passes if neutral accuracy is 1.0, flip_rate is 1.0, and the
             number of flip opportunities is len(CASES) * 2
    """
    # PLAYERS IN THIS SCENE
    #   s   the summary dict from summarize()

    # --- Setting the stage / The action ------------------------------------
    s = summarize(run(sycophant, samples=2))
    # --- The verdict -------------------------------------------------------
    assert s["accuracy"]["neutral"] == 1.0
    assert s["flip_rate"] == 1.0
    # Each case has exactly one condition whose pressure points the wrong
    # way ("deny" for real concealment, "accuse" for a control). With 2
    # samples each, that gives len(CASES) * 2 chances to flip.
    # one misleading condition per case
    assert s["flip_opportunities"] == len(CASES) * 2


# ===========================================================================
# SCENE 11 — THE CONTROLS EARN THEIR KEEP
# Proves: a model that always says "yes" never *flips* (it never changes its
# answer), so flip rate alone would miss it; the control cases catch it.
# ===========================================================================

def test_fixed_bias_is_caught_by_controls_not_by_flip_rate():
    """
    A fixed "yes" bias shows up as lost neutral accuracy, not as flips.

    Enter:   (nothing)
    Exit:    passes if neutral accuracy is below 1.0 and flip_rate is 0.0
    """
    # PLAYERS IN THIS SCENE
    #   s   the summary dict from summarize()

    # --- Setting the stage / The action ------------------------------------
    s = summarize(run(always_yes, samples=1))
    # --- The verdict -------------------------------------------------------
    # Controls (true answer: no concealment) are answered wrongly, so neutral
    # accuracy drops. For the real cases "yes" is correct and stays correct
    # under pressure, so nothing ever flips.
    assert s["accuracy"]["neutral"] < 1.0      # controls expose the bias
    assert s["flip_rate"] == 0.0               # it never changes its answer


# ===========================================================================
# SCENE 12 — THE SILENT WITNESS
# Proves: replies with no usable verdict are counted, scored as wrong, and
# leave the flip rate undefined (None) rather than a misleading 0.
# ===========================================================================

def test_unparseable_replies_count_as_wrong():
    """
    A model that never gives a parseable answer scores zero.

    Enter:   (nothing)
    Exit:    passes if every reply is counted unparsed, neutral accuracy is
             0.0, and flip_rate is None
    """
    # PLAYERS IN THIS SCENE
    #   s   the summary dict from summarize()

    # --- Setting the stage / The action ------------------------------------
    # The fake model here is a lambda: a one-line unnamed function taking
    # (system, prompt) and always returning the same evasive sentence.
    # `sys_` is named with a trailing underscore only to avoid looking like
    # the `sys` module; it is ignored.
    s = summarize(run(lambda sys_, p: "I'd rather not say.", samples=1))

    # --- The verdict -------------------------------------------------------
    assert s["unparsed_replies"] == s["samples"]
    assert s["accuracy"]["neutral"] == 0.0
    assert s["flip_rate"] is None               # nothing correct to flip from


# ===========================================================================
# SCENE 13 — FROM THE COMMAND LINE
# Proves: main() (the CLI entry point) runs the eval and writes a results
# file with the summary and one record per sample.
# ===========================================================================

def test_cli_writes_results(tmp_path, monkeypatch):
    """
    Running main() with --out writes a correct JSON results file.

    Enter:   tmp_path      pytest fixture: a fresh temporary folder
             monkeypatch   pytest fixture: swaps in the fake model
    Exit:    passes if main() returns 0, the file's flip_rate is 1.0, and it
             holds len(CASES) * len(CONDITIONS) samples (1 sample each)
    """
    # PLAYERS IN THIS SCENE
    #   ap     the harness module itself, imported so its attribute can be patched
    #   out    the path of the results file inside tmp_path
    #   data   the results file, parsed back from JSON

    # --- Setting the stage: replace the real model factory -----------------
    # main() calls langchain_model(backend) to build a real LLM client.
    # Patching that name on the module makes main() get our sycophant
    # instead (the lambda ignores the backend argument), so no API key is
    # needed. main() looks the name up when it runs, so it sees the patch.
    import evals.authority_pressure as ap
    monkeypatch.setattr(ap, "langchain_model", lambda backend: sycophant)
    out = tmp_path / "r.json"

    # --- The action --------------------------------------------------------
    # main() takes the argument list a user would type after the command;
    # it returns 0 on success, like a shell exit code.
    assert main(["--samples", "1", "--out", str(out)]) == 0

    # --- The verdict -------------------------------------------------------
    data = json.loads(out.read_text())
    assert data["summary"]["flip_rate"] == 1.0
    assert len(data["samples"]) == len(CASES) * len(CONDITIONS)

# EXEUNT — end of file.

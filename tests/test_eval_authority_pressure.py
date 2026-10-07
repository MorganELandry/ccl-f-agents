"""
Tests for the authority-pressure eval harness, using fake models with known
behaviour. No LLM credentials required.

Run: pytest tests/ -v
"""

import json

import pytest

from evals.authority_pressure import (
    CASES, CONDITIONS, PRESSURE, build_prompt, parse_answer, run, summarize, main,
)

TRUTH = {c.case_id: c.concealment for c in CASES}


def reply(verdict) -> str:
    return json.dumps({"concealment": verdict, "confidence": 0.9, "reasoning": "fake"})


def case_of(prompt: str):
    for c in CASES:
        if c.organization in prompt.splitlines()[0]:
            return c
    raise AssertionError("prompt names no case")


def honest(system, prompt):
    return reply(case_of(prompt).concealment)


def sycophant(system, prompt):
    if "confirm we didn't withhold" in prompt:
        return reply(False)
    if "confirm the cover-up" in prompt:
        return reply(True)
    return honest(system, prompt)


def always_yes(system, prompt):
    return reply(True)


def test_cases_include_positives_and_labelled_controls():
    assert any(c.concealment for c in CASES)
    controls = [c for c in CASES if not c.concealment]
    assert controls and all(c.synthetic for c in controls)


def test_prompt_carries_pressure_only_when_asked():
    case = CASES[0]
    assert "Before you answer" not in build_prompt(case, "neutral")
    for cond in ("deny", "accuse"):
        assert PRESSURE[cond].format(org=case.organization) in build_prompt(case, cond)


@pytest.mark.parametrize("text,expected", [
    ('{"concealment": true, "confidence": 0.8}', True),
    ('Sure! ```json\n{"concealment": false}\n```', False),
    ('{"concealment": "yes"}', None),
    ("no json here", None),
    ("", None),
])
def test_parse_answer(text, expected):
    assert parse_answer(text) is expected


def test_honest_model_never_flips():
    s = summarize(run(honest, samples=2))
    assert s["flip_rate"] == 0.0
    assert all(s["accuracy"][c] == 1.0 for c in CONDITIONS)


def test_sycophant_flips_every_time():
    s = summarize(run(sycophant, samples=2))
    assert s["accuracy"]["neutral"] == 1.0
    assert s["flip_rate"] == 1.0
    # one misleading condition per case
    assert s["flip_opportunities"] == len(CASES) * 2


def test_fixed_bias_is_caught_by_controls_not_by_flip_rate():
    s = summarize(run(always_yes, samples=1))
    assert s["accuracy"]["neutral"] < 1.0      # controls expose the bias
    assert s["flip_rate"] == 0.0               # it never changes its answer


def test_unparseable_replies_count_as_wrong():
    s = summarize(run(lambda sys_, p: "I'd rather not say.", samples=1))
    assert s["unparsed_replies"] == s["samples"]
    assert s["accuracy"]["neutral"] == 0.0
    assert s["flip_rate"] is None               # nothing correct to flip from


def test_cli_writes_results(tmp_path, monkeypatch):
    import evals.authority_pressure as ap
    monkeypatch.setattr(ap, "langchain_model", lambda backend: sycophant)
    out = tmp_path / "r.json"
    assert main(["--samples", "1", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["summary"]["flip_rate"] == 1.0
    assert len(data["samples"]) == len(CASES) * len(CONDITIONS)

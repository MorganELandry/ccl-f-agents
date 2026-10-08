"""
THE UNDERSTUDIES' FITTING
A Play in Three Scenes
======================

PROLOGUE
--------
Tests for cclf/backends: which model each backend asks for by default, and
that no sampling temperature is sent unless CCLF_TEMPERATURE asks for one.

Why the second matters: Claude Sonnet 5.5 rejects any non-default
temperature (the API returns a 400, and langchain-anthropic refuses before
sending), and OpenAI's current reasoning models document no temperature
setting. Until October 2026 every backend sent temperature=0.1, so the
eval and the advisor would have failed on the first call to a current
model.

No network is used. Each test builds the LangChain model and inspects the
request it would send. A test is skipped if that backend's optional
LangChain package is not installed.

THE PLAYBILL
    Scene 1  test_sampling_kwargs_empty_unless_set
    Scene 2  test_default_model_and_no_temperature        (parametrized, 4 runs)
    Scene 3  test_temperature_sent_only_when_asked
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest            parametrize, importorskip, monkeypatch.
# cclf.backends     get_llm, sampling_kwargs.
# ===========================================================================

import pytest

from cclf.backends import get_llm, sampling_kwargs


# ===========================================================================
# DRAMATIS PERSONAE
# ===========================================================================

# FAKE_ENV — placeholder settings so each backend can build a model object.
#   No request is ever sent with them.
FAKE_ENV = {
    "OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "sk-ant-test",
    "AZURE_OPENAI_API_KEY": "test", "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT_NAME": "my-deployment", "AZURE_OPENAI_API_VERSION": "2024-02-01",
    "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test",
}

# DEFAULTS — backend -> (its LangChain package, the model it asks for when
#   no model variable is set). Azure has no default: it calls whatever
#   deployment AZURE_OPENAI_DEPLOYMENT_NAME names.
DEFAULTS = {
    "openai": ("langchain_openai", "gpt-6-luna"),
    "anthropic": ("langchain_anthropic", "claude-sonnet-5-5"),
    "azure": ("langchain_openai", None),
    "bedrock": ("langchain_aws", "global.anthropic.claude-sonnet-5-5"),
}

# MODEL_VARS — every variable that would override a default model.
MODEL_VARS = ("OPENAI_MODEL", "ANTHROPIC_MODEL", "BEDROCK_MODEL_ID", "CCLF_TEMPERATURE")


@pytest.fixture
def env(monkeypatch):
    """Placeholder credentials, and no model or temperature overrides."""
    for k, v in FAKE_ENV.items():
        monkeypatch.setenv(k, v)
    for k in MODEL_VARS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def request(backend: str) -> tuple:
    """
    What a backend would send: (model, temperature or None).

    Enter:   backend   a backend name
    Exit:    the model name and temperature in its request; for Bedrock,
             its model id and the temperature in model_kwargs
    """
    from langchain_core.messages import HumanMessage
    llm = get_llm(backend)
    if backend == "bedrock":
        return llm.model_id, llm.model_kwargs.get("temperature")
    payload = llm._get_request_payload([HumanMessage(content="hi")])
    return payload.get("model"), payload.get("temperature")


# ===========================================================================
# SCENE 1 — NOTHING UNLESS ASKED
# ===========================================================================

def test_sampling_kwargs_empty_unless_set(monkeypatch):
    monkeypatch.delenv("CCLF_TEMPERATURE", raising=False)
    assert sampling_kwargs() == {}
    monkeypatch.setenv("CCLF_TEMPERATURE", "0.2")
    assert sampling_kwargs() == {"temperature": 0.2}


# ===========================================================================
# SCENE 2 — CURRENT MODELS, NO TEMPERATURE
# ===========================================================================

@pytest.mark.parametrize("backend", list(DEFAULTS))
def test_default_model_and_no_temperature(env, backend):
    package, model = DEFAULTS[backend]
    pytest.importorskip(package)
    sent_model, temperature = request(backend)
    if model is not None:
        assert sent_model == model
    assert temperature is None


# ===========================================================================
# SCENE 3 — A TEMPERATURE WHEN ASKED, FOR A MODEL THAT TAKES ONE
# ===========================================================================

def test_temperature_sent_only_when_asked(env):
    pytest.importorskip("langchain_openai")
    env.setenv("CCLF_TEMPERATURE", "0.1")
    env.setenv("OPENAI_MODEL", "a-model-that-accepts-temperature")
    assert request("openai") == ("a-model-that-accepts-temperature", 0.1)

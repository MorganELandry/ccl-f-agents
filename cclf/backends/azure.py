"""
THE AZURE UNDERSTUDY
A Play in One Scene
====================

PROLOGUE
--------
CCL-F Backend — Azure OpenAI Service.
Routes LLM calls to a tenant-isolated Azure OpenAI deployment.
Azure OpenAI is covered under Microsoft's HIPAA BAA as part of
the Azure Enterprise Agreement.

This is the recommended backend for hospital / clinical
production deployments. It is one of the four backends the registry in
backends/__init__.py can choose from (CCLF_LLM_BACKEND=azure). Like every
backend, it offers exactly one function, get_llm(), that returns a
LangChain chat model.

Required env vars:
  AZURE_OPENAI_API_KEY
  AZURE_OPENAI_ENDPOINT            e.g. https://<resource>.openai.azure.com/
  AZURE_OPENAI_DEPLOYMENT_NAME     your deployment name, not the model name
  AZURE_OPENAI_API_VERSION         e.g. 2024-02-01

Compliance prerequisites (not enforced in code — must be verified operationally):
  1. Microsoft BAA executed as part of Azure Enterprise Agreement
  2. Azure OpenAI resource in a HIPAA-eligible region
  3. Network access restricted to hospital VNet or Private Endpoint
  4. Diagnostic logs forwarded to a BAA-covered log sink (Azure Monitor)
  5. Customer-managed keys (CMK) enabled for data at rest if required
  6. PHI scrubbed from the text sent to the model (for the advisor, the
     report text passed to Advisor.propose()) OR that text contains only
     de-identified / coded content

See COMPLIANCE.md for the full gap analysis.

THE PLAYBILL (what happens in this file)
    Scene 1  get_llm()   check settings, then build an AzureChatOpenAI model

READER'S NOTE
    The LangChain package (langchain_openai, which also provides the Azure
    class) is imported inside get_llm(), not at the top of the file. That
    "lazy import" means the package is only needed if this backend is
    actually used. See the READER'S NOTE on lazy imports in
    backends/__init__.py.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# os        reads environment variables (os.environ).
# logging   provides this module's logger (declared below).
# sampling_kwargs   the temperature setting, only if CCLF_TEMPERATURE is set.
# ===========================================================================

from __future__ import annotations
import os
import logging

from . import sampling_kwargs


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# logger — this module's logger, named "cclf.backends.azure" after the
#   module. (get_llm() below does not currently log anything.)
logger = logging.getLogger(__name__)

# _REQUIRED — the environment variables that must all be set (non-empty)
#   before this backend will build a model. Unlike the OpenAI and Anthropic
#   backends, Azure refuses to start with missing settings, because there
#   is no sensible default endpoint or deployment to fall back on.
_REQUIRED = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "AZURE_OPENAI_API_VERSION",
]


# ===========================================================================
# SCENE 1 — THE AUDITION
# get_llm(): are all Azure settings present, and if so, build the model
# ===========================================================================

def get_llm():
    """
    Build and return a LangChain AzureChatOpenAI model.

    Enter:   (no arguments; settings come from environment variables)
    Exit:    an AzureChatOpenAI pointed at AZURE_OPENAI_ENDPOINT, using
             deployment AZURE_OPENAI_DEPLOYMENT_NAME, API version
             AZURE_OPENAI_API_VERSION, key AZURE_OPENAI_API_KEY and
             a temperature only if CCLF_TEMPERATURE is set
             raises ImportError if langchain-openai is not installed
             raises EnvironmentError naming every missing setting in _REQUIRED
    """
    # PLAYERS IN THIS SCENE
    #   AzureChatOpenAI   LangChain's Azure OpenAI chat-model class (lazily imported)
    #   missing           names from _REQUIRED that are unset or empty

    # --- Lazy import, with a helpful message if the package is missing -----
    try:
        from langchain_openai import AzureChatOpenAI
    except ImportError:
        raise ImportError(
            "langchain-openai is required for the Azure backend. "
            "Run: pip install langchain-openai"
        )

    # --- Check every required setting at once ----------------------------
    # A list comprehension: keep each name k whose value is unset or "".
    # Collecting them all means the error lists every missing variable,
    # not just the first one, so the user can fix them in one go.
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(
            f"Azure OpenAI backend requires these env vars: {', '.join(missing)}\n"
            f"See COMPLIANCE.md → Azure OpenAI Setup."
        )

    # --- Build the model -----------------------------------------------------
    # os.environ[...] (square brackets) is safe here: the check above has
    # already proved every one of these variables is set.
    return AzureChatOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        **sampling_kwargs(),
    )

# EXEUNT — end of file.

"""
THE CASTING OFFICE
A Play in Three Scenes
======================

PROLOGUE
--------
The CCL-F LLM Backend Registry. It selects and returns the configured
LLM backend at runtime.

The LLM nodes in nodes.py need a chat model to talk to, but they should not
care *which* company's model it is. This package is the casting office: the
nodes ask for "an LLM" by calling get_llm(), and this file decides which
provider plays the part, based on configuration.

Backend is controlled by the CCLF_LLM_BACKEND environment variable:

  CCLF_LLM_BACKEND=openai       OpenAI API (default)
  CCLF_LLM_BACKEND=anthropic    Anthropic API (Claude)
  CCLF_LLM_BACKEND=azure        Azure OpenAI Service (HIPAA-eligible)
  CCLF_LLM_BACKEND=bedrock      AWS Bedrock — Claude on AWS (HIPAA-eligible)

All backends expose the same interface:
  get_llm()  →  a LangChain chat model with .invoke(messages) → response

Required environment variables per backend:

  openai:
    OPENAI_API_KEY

  anthropic:
    ANTHROPIC_API_KEY

  azure:
    AZURE_OPENAI_API_KEY
    AZURE_OPENAI_ENDPOINT          e.g. https://<resource>.openai.azure.com/
    AZURE_OPENAI_DEPLOYMENT_NAME   e.g. gpt-4o
    AZURE_OPENAI_API_VERSION       e.g. 2024-02-01

  bedrock:
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION             e.g. us-east-1
    BEDROCK_MODEL_ID               e.g. anthropic.claude-3-5-sonnet-20241022-v2:0

COMPLIANCE NOTE
---------------
For hospital / HIPAA-covered entity deployments:
  - Use 'azure' or 'bedrock' backends ONLY.
  - These route traffic to tenant-isolated endpoints covered by BAA.
  - 'openai' and 'anthropic' send data to shared infrastructure.
    A BAA must be executed with the vendor AND the architecture reviewed
    before using these backends with any PHI or clinical content.
  - See COMPLIANCE.md for the full gap analysis.

THE PLAYBILL (what happens in this file)
    Scene 1  get_llm()            hand back a chat model for the chosen backend
    Scene 2  active_backend()     which backend is configured by default?
    Scene 3  is_hipaa_eligible()  is a backend routed to BAA-covered hosting?

READER'S NOTE — the registry pattern
    A "registry" is one central list of the available options plus one
    function that picks between them by name. Here the list is _BACKENDS
    and the picker is get_llm(). Every backend module (openai.py,
    anthropic.py, azure.py, bedrock.py) offers a function with the same
    name and shape, get_llm(), so the caller never needs to know which one
    it got. Adding a provider means writing one more module with a
    get_llm() and adding its name to the registry; nodes.py does not change.

READER'S NOTE — lazy imports
    Normally imports sit at the top of a file and run as soon as the file is
    loaded. Here the backend modules are imported *inside* get_llm(), only
    for the backend actually chosen. Each backend needs its own third-party
    package (langchain-openai, langchain-anthropic, langchain-aws). Lazy
    importing means you only have to install the package for the backend
    you use; the others are never imported, so their absence causes no
    error. Each backend module repeats the trick for its own LangChain
    package and turns a missing package into a clear "pip install ..."
    message.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# os        reads environment variables (os.environ).
# logging   Python's standard logging; messages go wherever the application
#           has configured logging to send them.
# The backend modules themselves are NOT imported here (see lazy imports).
# ===========================================================================

from __future__ import annotations
import os
import logging


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# logger — this module's logger.
#   logging.getLogger(__name__) names it after the module ("cclf.backends"),
#   so log output shows where a message came from and can be filtered.
logger = logging.getLogger(__name__)

# _BACKENDS — the registry: every backend name get_llm() will accept.
#   Registry of available backends (imported lazily to avoid hard deps).
#   A tuple, so it cannot be changed by accident at runtime.
_BACKENDS = ("openai", "anthropic", "azure", "bedrock")

# _DEFAULT_BACKEND — the backend used when a caller does not name one.
#   Read from the CCLF_LLM_BACKEND environment variable, falling back to
#   "openai", and lower-cased so "Azure" and "azure" mean the same thing.
#   Note: this is read ONCE, when this module is first imported. Changing
#   CCLF_LLM_BACKEND after that has no effect on this value; pass a
#   `backend` argument to get_llm() instead.
_DEFAULT_BACKEND = os.environ.get("CCLF_LLM_BACKEND", "openai").lower()


# ===========================================================================
# SCENE 1 — THE CASTING CALL
# get_llm(): which chat model should play the LLM part?
# ===========================================================================

def get_llm(backend: str | None = None):
    """
    Return a LangChain chat model for the specified backend.
    Falls back to CCLF_LLM_BACKEND env var, then 'openai'.

    Enter:   backend   a backend name from _BACKENDS (any letter case), or
                       None to use _DEFAULT_BACKEND
    Exit:    a LangChain chat model built by that backend module's get_llm()
             raises ValueError for an unknown backend name; the backend
             module may raise ImportError (package missing) or, for azure,
             EnvironmentError (settings missing)

    A new model object is built on every call; nothing is cached here.
    """
    # PLAYERS IN THIS SCENE
    #   target   the lower-cased backend name we will actually use
    #   _get     the chosen backend module's get_llm function

    # --- Decide which backend ---------------------------------------------
    # `backend or _DEFAULT_BACKEND` uses `backend` unless it is None or "".
    target = (backend or _DEFAULT_BACKEND).lower()

    # --- Reject names not in the registry -----------------------------------
    if target not in _BACKENDS:
        raise ValueError(
            f"Unknown backend '{target}'. "
            f"Valid options: {', '.join(_BACKENDS)}"
        )

    # --- Lazy import of only the chosen backend -----------------------------
    # `from .openai import get_llm as _get` loads cclf/backends/openai.py now
    # (not at file load) and gives its get_llm the local name _get, so it
    # does not clash with this function's own name. Every branch binds the
    # same name, so the line after the if/elif chain works for all four.
    if target == "openai":
        from .openai import get_llm as _get
    elif target == "anthropic":
        from .anthropic import get_llm as _get
    elif target == "azure":
        from .azure import get_llm as _get
    elif target == "bedrock":
        from .bedrock import get_llm as _get

    # --- Build and hand back the model --------------------------------------
    logger.debug(f"[cclf-backend] Using LLM backend: {target}")
    return _get()


# ===========================================================================
# SCENE 2 — THE NAME ON THE DOOR
# active_backend(): which backend is configured as the default?
# ===========================================================================

def active_backend() -> str:
    """
    Report the default backend name.

    Enter:   (no arguments)
    Exit:    _DEFAULT_BACKEND, i.e. CCLF_LLM_BACKEND as it was when this
             module was imported (lower-cased), or "openai". It is not
             checked against _BACKENDS here.
    """
    return _DEFAULT_BACKEND


# ===========================================================================
# SCENE 3 — THE COMPLIANCE CHECK
# is_hipaa_eligible(): is this backend routed to BAA-covered hosting?
# ===========================================================================

def is_hipaa_eligible(backend: str | None = None) -> bool:
    """
    Returns True only for backends routed to BAA-covered infrastructure.
    This is a configuration check, NOT a guarantee — a BAA must be
    executed with the relevant vendor before handling PHI.

    Enter:   backend   a backend name, or None to check _DEFAULT_BACKEND
    Exit:    True for "azure" or "bedrock" (any letter case), else False
    """
    # PLAYERS IN THIS SCENE
    #   target   the lower-cased backend name being checked

    target = (backend or _DEFAULT_BACKEND).lower()
    return target in ("azure", "bedrock")

# EXEUNT — end of file.

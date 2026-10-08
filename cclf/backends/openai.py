"""
THE OPENAI UNDERSTUDY
A Play in One Scene
=====================

PROLOGUE
--------
CCL-F Backend — OpenAI API.
Uses GPT-6 Luna (gpt-6-luna) by default; set OPENAI_MODEL to override.

This is one of the four backends the registry in backends/__init__.py can
choose from. It is the default when CCLF_LLM_BACKEND is not set. Like every
backend, it offers exactly one function, get_llm(), that returns a
LangChain chat model.

COMPLIANCE WARNING: Not suitable for PHI or hospital production use without
an executed OpenAI BAA and architecture review. See COMPLIANCE.md.

Required env vars:
  OPENAI_API_KEY
  OPENAI_MODEL        (optional, default: gpt-6-luna)
  CCLF_TEMPERATURE    (optional; see backends/__init__.py, Scene 4)

THE PLAYBILL (what happens in this file)
    Scene 1  get_llm()   build a ChatOpenAI model from environment settings

READER'S NOTE
    The LangChain package (langchain_openai) is imported inside get_llm(),
    not at the top of the file. That "lazy import" means the package is
    only needed if this backend is actually used. See the READER'S NOTE on
    lazy imports in backends/__init__.py.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# os        reads environment variables (os.environ).
# logging   used to warn when the API key is missing.
# sampling_kwargs   the temperature setting, only if CCLF_TEMPERATURE is set.
# ===========================================================================

from __future__ import annotations
import os
import logging

from . import sampling_kwargs


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# logger — this module's logger, named "cclf.backends.openai" after the
#   module, so its warnings are easy to trace back to this file.
logger = logging.getLogger(__name__)


# ===========================================================================
# SCENE 1 — THE AUDITION
# get_llm(): build an OpenAI chat model ready to answer the advisor
# ===========================================================================

def get_llm():
    """
    Build and return a LangChain ChatOpenAI model.

    Enter:   (no arguments; settings come from environment variables)
    Exit:    a ChatOpenAI configured with OPENAI_MODEL (default
             "gpt-6-luna"), OPENAI_API_KEY, and a temperature only if
             CCLF_TEMPERATURE is set
             raises ImportError if langchain-openai is not installed

    A missing API key is only logged as a warning by this code, not raised.
    The ChatOpenAI constructor itself then refuses to build without a key
    (the openai library raises OpenAIError, "Missing credentials"), so the
    error comes out of this function; Advisor._model() catches it and
    Advisor.propose() falls back to its conservative proposal.
    """
    # PLAYERS IN THIS SCENE
    #   ChatOpenAI   LangChain's OpenAI chat-model class (lazily imported)
    #   model        the model name to request
    #   api_key      the OpenAI API key, or "" if not set

    # --- Lazy import, with a helpful message if the package is missing -----
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError(
            "langchain-openai is required for the OpenAI backend. "
            "Run: pip install langchain-openai"
        )

    # --- Read settings from the environment ----------------------------------
    # os.environ.get(name, default) returns the default if the variable is unset.
    model = os.environ.get("OPENAI_MODEL", "gpt-6-luna")
    api_key = os.environ.get("OPENAI_API_KEY", "")

    # --- Warn, but do not stop here, if the key is missing ------------------
    # (ChatOpenAI below raises on its own when given no key.)
    if not api_key:
        logger.warning("[cclf-backend/openai] OPENAI_API_KEY not set.")

    # --- Build the model -----------------------------------------------------
    # `**sampling_kwargs()` adds temperature=... only if CCLF_TEMPERATURE is
    # set: current reasoning models may not accept one (Scene 4 of
    # backends/__init__.py).
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        **sampling_kwargs(),
    )

# EXEUNT — end of file.

"""
THE OPENAI UNDERSTUDY
A Play in One Scene
=====================

PROLOGUE
--------
CCL-F Backend — OpenAI API.
Uses GPT-4o-mini by default; set OPENAI_MODEL to override.

This is one of the four backends the registry in backends/__init__.py can
choose from. It is the default when CCLF_LLM_BACKEND is not set. Like every
backend, it offers exactly one function, get_llm(), that returns a
LangChain chat model.

COMPLIANCE WARNING: Not suitable for PHI or hospital production use without
an executed OpenAI BAA and architecture review. See COMPLIANCE.md.

Required env vars:
  OPENAI_API_KEY
  OPENAI_MODEL        (optional, default: gpt-4o-mini)

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
# ===========================================================================

from __future__ import annotations
import os
import logging


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# logger — this module's logger, named "cclf.backends.openai" after the
#   module, so its warnings are easy to trace back to this file.
logger = logging.getLogger(__name__)


# ===========================================================================
# SCENE 1 — THE AUDITION
# get_llm(): build an OpenAI chat model ready to answer the nodes
# ===========================================================================

def get_llm():
    """
    Build and return a LangChain ChatOpenAI model.

    Enter:   (no arguments; settings come from environment variables)
    Exit:    a ChatOpenAI configured with OPENAI_MODEL (default
             "gpt-4o-mini"), temperature 0.1 and OPENAI_API_KEY
             raises ImportError if langchain-openai is not installed

    A missing API key is only logged as a warning here, not raised. The
    model object is still built; the failure then shows up when it is first
    used, where nodes.py turns it into an error result.
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
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    api_key = os.environ.get("OPENAI_API_KEY", "")

    # --- Warn, but do not stop, if the key is missing ------------------------
    if not api_key:
        logger.warning("[cclf-backend/openai] OPENAI_API_KEY not set.")

    # --- Build the model -----------------------------------------------------
    # A low temperature (0.1) makes replies less random, which helps the
    # nodes get consistent, parseable JSON.
    return ChatOpenAI(
        model=model,
        temperature=0.1,
        api_key=api_key,
    )

# EXEUNT — end of file.

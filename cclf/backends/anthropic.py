"""
THE ANTHROPIC UNDERSTUDY
A Play in One Scene
========================

PROLOGUE
--------
CCL-F Backend — Anthropic API (Claude).
Uses claude-sonnet-5-5 by default; set ANTHROPIC_MODEL to override.

This is one of the four backends the registry in backends/__init__.py can
choose from (CCLF_LLM_BACKEND=anthropic). Like every backend, it offers
exactly one function, get_llm(), that returns a LangChain chat model.

The advisor and the eval both ask for a JSON-only reply. No temperature is
sent unless CCLF_TEMPERATURE is set: Claude Sonnet 5.5 rejects any
non-default temperature with a 400 error.

COMPLIANCE WARNING: Not suitable for PHI or hospital production use without
an executed Anthropic BAA and architecture review. See COMPLIANCE.md.
For HIPAA-eligible Claude deployment, use the 'bedrock' backend instead
(AWS Bedrock with Claude models, covered by AWS BAA).

Required env vars:
  ANTHROPIC_API_KEY
  ANTHROPIC_MODEL     (optional, default: claude-sonnet-5-5)
  CCLF_TEMPERATURE    (optional; see backends/__init__.py, Scene 4)

THE PLAYBILL (what happens in this file)
    Scene 1  get_llm()   build a ChatAnthropic model from environment settings

READER'S NOTE
    The LangChain package (langchain_anthropic) is imported inside
    get_llm(), not at the top of the file. That "lazy import" means the
    package is only needed if this backend is actually used. See the
    READER'S NOTE on lazy imports in backends/__init__.py.
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

# logger — this module's logger, named "cclf.backends.anthropic" after the
#   module, so its warnings are easy to trace back to this file.
logger = logging.getLogger(__name__)


# ===========================================================================
# SCENE 1 — THE AUDITION
# get_llm(): build a Claude chat model ready to answer the advisor
# ===========================================================================

def get_llm():
    """
    Build and return a LangChain ChatAnthropic model.

    Enter:   (no arguments; settings come from environment variables)
    Exit:    a ChatAnthropic configured with ANTHROPIC_MODEL (default
             "claude-sonnet-5-5"), ANTHROPIC_API_KEY, and a temperature only
             if CCLF_TEMPERATURE is set
             raises ImportError if langchain-anthropic is not installed

    A missing API key is only logged as a warning here, not raised. The
    model object is still built; the failure then shows up when it is first
    used, where Advisor.propose() falls back to its conservative proposal.
    """
    # PLAYERS IN THIS SCENE
    #   ChatAnthropic   LangChain's Anthropic chat-model class (lazily imported)
    #   model           the model name to request
    #   api_key         the Anthropic API key, or "" if not set

    # --- Lazy import, with a helpful message if the package is missing -----
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        raise ImportError(
            "langchain-anthropic is required for the Anthropic backend. "
            "Run: pip install langchain-anthropic"
        )

    # --- Read settings from the environment ----------------------------------
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # --- Warn, but do not stop, if the key is missing ------------------------
    if not api_key:
        logger.warning("[cclf-backend/anthropic] ANTHROPIC_API_KEY not set.")

    # --- Build the model -----------------------------------------------------
    # `**sampling_kwargs()` adds temperature=... only if CCLF_TEMPERATURE is
    # set (Scene 4 of backends/__init__.py).
    return ChatAnthropic(
        model=model,
        api_key=api_key,
        **sampling_kwargs(),
    )

# EXEUNT — end of file.

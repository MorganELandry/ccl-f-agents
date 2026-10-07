"""
CCL-F LLM Backend Registry
============================
Selects and returns the configured LLM backend at runtime.

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
"""

from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)

# Registry of available backends (imported lazily to avoid hard deps)
_BACKENDS = ("openai", "anthropic", "azure", "bedrock")

_DEFAULT_BACKEND = os.environ.get("CCLF_LLM_BACKEND", "openai").lower()


def get_llm(backend: str | None = None):
    """
    Return a LangChain chat model for the specified backend.
    Falls back to CCLF_LLM_BACKEND env var, then 'openai'.
    """
    target = (backend or _DEFAULT_BACKEND).lower()

    if target not in _BACKENDS:
        raise ValueError(
            f"Unknown backend '{target}'. "
            f"Valid options: {', '.join(_BACKENDS)}"
        )

    if target == "openai":
        from .openai import get_llm as _get
    elif target == "anthropic":
        from .anthropic import get_llm as _get
    elif target == "azure":
        from .azure import get_llm as _get
    elif target == "bedrock":
        from .bedrock import get_llm as _get

    logger.debug(f"[cclf-backend] Using LLM backend: {target}")
    return _get()


def active_backend() -> str:
    return _DEFAULT_BACKEND


def is_hipaa_eligible(backend: str | None = None) -> bool:
    """
    Returns True only for backends routed to BAA-covered infrastructure.
    This is a configuration check, NOT a guarantee — a BAA must be
    executed with the relevant vendor before handling PHI.
    """
    target = (backend or _DEFAULT_BACKEND).lower()
    return target in ("azure", "bedrock")

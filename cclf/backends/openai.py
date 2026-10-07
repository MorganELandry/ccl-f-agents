"""
CCL-F Backend — OpenAI API
===========================
Uses GPT-4o-mini by default; set OPENAI_MODEL to override.

⚠️  COMPLIANCE: Not suitable for PHI or hospital production use without
an executed OpenAI BAA and architecture review. See COMPLIANCE.md.

Required env vars:
  OPENAI_API_KEY
  OPENAI_MODEL        (optional, default: gpt-4o-mini)
"""

from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)


def get_llm():
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError(
            "langchain-openai is required for the OpenAI backend. "
            "Run: pip install langchain-openai"
        )

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        logger.warning("[cclf-backend/openai] OPENAI_API_KEY not set.")

    return ChatOpenAI(
        model=model,
        temperature=0.1,
        api_key=api_key,
    )

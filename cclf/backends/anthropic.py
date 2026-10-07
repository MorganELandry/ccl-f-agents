"""
CCL-F Backend — Anthropic API (Claude)
========================================
Uses Claude 3.5 Sonnet by default; set ANTHROPIC_MODEL to override.

Claude's instruction-following on structured JSON output is stronger than
GPT-4o-mini, which benefits the acs_inference and aco_detection nodes
where the JSON schema must be precise.

⚠️  COMPLIANCE: Not suitable for PHI or hospital production use without
an executed Anthropic BAA and architecture review. See COMPLIANCE.md.
For HIPAA-eligible Claude deployment, use the 'bedrock' backend instead
(AWS Bedrock with Claude models, covered by AWS BAA).

Required env vars:
  ANTHROPIC_API_KEY
  ANTHROPIC_MODEL     (optional, default: claude-sonnet-4-6)
"""

from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)


def get_llm():
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        raise ImportError(
            "langchain-anthropic is required for the Anthropic backend. "
            "Run: pip install langchain-anthropic"
        )

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        logger.warning("[cclf-backend/anthropic] ANTHROPIC_API_KEY not set.")

    return ChatAnthropic(
        model=model,
        temperature=0.1,
        api_key=api_key,
    )

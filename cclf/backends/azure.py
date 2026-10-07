"""
CCL-F Backend — Azure OpenAI Service
======================================
Routes LLM calls to a tenant-isolated Azure OpenAI deployment.
Azure OpenAI is covered under Microsoft's HIPAA BAA as part of
the Azure Enterprise Agreement.

This is the recommended backend for hospital / clinical
production deployments.

Required env vars:
  AZURE_OPENAI_API_KEY
  AZURE_OPENAI_ENDPOINT            e.g. https://<resource>.openai.azure.com/
  AZURE_OPENAI_DEPLOYMENT_NAME     e.g. gpt-4o  (your deployment name, not model name)
  AZURE_OPENAI_API_VERSION         e.g. 2024-02-01

Compliance prerequisites (not enforced in code — must be verified operationally):
  1. Microsoft BAA executed as part of Azure Enterprise Agreement
  2. Azure OpenAI resource in a HIPAA-eligible region
  3. Network access restricted to hospital VNet or Private Endpoint
  4. Diagnostic logs forwarded to a BAA-covered log sink (Azure Monitor)
  5. Customer-managed keys (CMK) enabled for data at rest if required
  6. PHI scrubbed from evidence_buffer before agent invocation
     OR evidence_buffer contains only de-identified / coded content

See COMPLIANCE.md for the full gap analysis.
"""

from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)

_REQUIRED = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "AZURE_OPENAI_API_VERSION",
]


def get_llm():
    try:
        from langchain_openai import AzureChatOpenAI
    except ImportError:
        raise ImportError(
            "langchain-openai is required for the Azure backend. "
            "Run: pip install langchain-openai"
        )

    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(
            f"Azure OpenAI backend requires these env vars: {', '.join(missing)}\n"
            f"See COMPLIANCE.md → Azure OpenAI Setup."
        )

    return AzureChatOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        temperature=0.1,
    )

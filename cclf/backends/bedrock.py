"""
CCL-F Backend — AWS Bedrock (Claude on AWS)
============================================
Routes LLM calls to Claude models via AWS Bedrock.
AWS Bedrock is covered under the AWS BAA for HIPAA-eligible workloads.

This backend runs Claude models on AWS infrastructure — combining
Claude's structured JSON output quality with HIPAA-eligible routing.
Appropriate for hospital deployments already in the AWS ecosystem.

Required env vars:
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_DEFAULT_REGION               e.g. us-east-1
  BEDROCK_MODEL_ID                 e.g. anthropic.claude-3-5-sonnet-20241022-v2:0

Alternatively, use an IAM role (EC2 instance profile / ECS task role)
instead of access key env vars — boto3 will pick it up automatically.

Compliance prerequisites (not enforced in code — must be verified operationally):
  1. AWS BAA executed (available for accounts with Business/Enterprise Support)
  2. Bedrock used in a HIPAA-eligible region (us-east-1, us-west-2, etc.)
  3. VPC endpoint for Bedrock to avoid public internet egress
  4. CloudTrail logging enabled for Bedrock API calls
  5. IAM role with least-privilege Bedrock InvokeModel permissions
  6. PHI scrubbed from evidence_buffer before agent invocation
     OR evidence_buffer contains only de-identified / coded content

See COMPLIANCE.md for the full gap analysis.
"""

from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "anthropic.claude-3-5-sonnet-20241022-v2:0"


def get_llm():
    try:
        from langchain_aws import ChatBedrock
    except ImportError:
        raise ImportError(
            "langchain-aws is required for the Bedrock backend. "
            "Run: pip install langchain-aws boto3"
        )

    model_id = os.environ.get("BEDROCK_MODEL_ID", _DEFAULT_MODEL)
    region   = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    logger.info(
        f"[cclf-backend/bedrock] Using model {model_id} in {region}"
    )

    return ChatBedrock(
        model_id=model_id,
        region_name=region,
        model_kwargs={"temperature": 0.1},
    )

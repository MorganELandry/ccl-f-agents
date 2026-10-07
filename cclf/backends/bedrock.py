"""
THE BEDROCK UNDERSTUDY
A Play in One Scene
======================

PROLOGUE
--------
CCL-F Backend — AWS Bedrock (Claude on AWS).
Routes LLM calls to Claude models via AWS Bedrock.
AWS Bedrock is covered under the AWS BAA for HIPAA-eligible workloads.

This backend runs Claude models on AWS infrastructure — combining
Claude's structured JSON output quality with HIPAA-eligible routing.
Appropriate for hospital deployments already in the AWS ecosystem.
It is one of the four backends the registry in backends/__init__.py can
choose from (CCLF_LLM_BACKEND=bedrock). Like every backend, it offers
exactly one function, get_llm(), that returns a LangChain chat model.

Required env vars:
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_DEFAULT_REGION               e.g. us-east-1 (default if unset: us-east-1)
  BEDROCK_MODEL_ID                 e.g. anthropic.claude-3-5-sonnet-20241022-v2:0
                                   (default if unset: that same model)

Alternatively, use an IAM role (EC2 instance profile / ECS task role)
instead of access key env vars — boto3 will pick it up automatically.
(This file never reads the AWS keys itself; boto3, the AWS library
underneath LangChain, finds credentials on its own.)

Compliance prerequisites (not enforced in code — must be verified operationally):
  1. AWS BAA executed (available for accounts with Business/Enterprise Support)
  2. Bedrock used in a HIPAA-eligible region (us-east-1, us-west-2, etc.)
  3. VPC endpoint for Bedrock to avoid public internet egress
  4. CloudTrail logging enabled for Bedrock API calls
  5. IAM role with least-privilege Bedrock InvokeModel permissions
  6. PHI scrubbed from evidence_buffer before agent invocation
     OR evidence_buffer contains only de-identified / coded content

See COMPLIANCE.md for the full gap analysis.

THE PLAYBILL (what happens in this file)
    Scene 1  get_llm()   build a ChatBedrock model from environment settings

READER'S NOTE
    The LangChain package (langchain_aws) is imported inside get_llm(), not
    at the top of the file. That "lazy import" means the package is only
    needed if this backend is actually used. See the READER'S NOTE on lazy
    imports in backends/__init__.py.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# os        reads environment variables (os.environ).
# logging   used to record which model and region were chosen.
# ===========================================================================

from __future__ import annotations
import os
import logging


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# logger — this module's logger, named "cclf.backends.bedrock" after the
#   module, so its messages are easy to trace back to this file.
logger = logging.getLogger(__name__)

# _DEFAULT_MODEL — the Bedrock model ID used when BEDROCK_MODEL_ID is not
#   set. Bedrock model IDs are prefixed with the vendor ("anthropic.") and
#   end with a version suffix.
_DEFAULT_MODEL = "anthropic.claude-3-5-sonnet-20241022-v2:0"


# ===========================================================================
# SCENE 1 — THE AUDITION
# get_llm(): build a Claude-on-AWS chat model ready to answer the advisor
# ===========================================================================

def get_llm():
    """
    Build and return a LangChain ChatBedrock model.

    Enter:   (no arguments; settings come from environment variables)
    Exit:    a ChatBedrock for BEDROCK_MODEL_ID (default _DEFAULT_MODEL) in
             AWS_DEFAULT_REGION (default "us-east-1"), temperature 0.1
             raises ImportError if langchain-aws is not installed

    No credentials are checked here. If boto3 cannot find any, the error
    appears when the model is first used.
    """
    # PLAYERS IN THIS SCENE
    #   ChatBedrock   LangChain's Bedrock chat-model class (lazily imported)
    #   model_id      the Bedrock model ID to call
    #   region        the AWS region to call it in

    # --- Lazy import, with a helpful message if the package is missing -----
    try:
        from langchain_aws import ChatBedrock
    except ImportError:
        raise ImportError(
            "langchain-aws is required for the Bedrock backend. "
            "Run: pip install langchain-aws boto3"
        )

    # --- Read settings from the environment, with defaults --------------
    model_id = os.environ.get("BEDROCK_MODEL_ID", _DEFAULT_MODEL)
    region   = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    # --- Record the choice (useful when auditing where data was sent) -------
    logger.info(
        f"[cclf-backend/bedrock] Using model {model_id} in {region}"
    )

    # --- Build the model -----------------------------------------------------
    # Bedrock takes generation settings such as temperature inside
    # model_kwargs rather than as a top-level argument. A low temperature
    # (0.1) makes replies less random, which helps the advisor get JSON.
    return ChatBedrock(
        model_id=model_id,
        region_name=region,
        model_kwargs={"temperature": 0.1},
    )

# EXEUNT — end of file.

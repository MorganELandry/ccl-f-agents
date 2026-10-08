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
  BEDROCK_MODEL_ID                 default: global.anthropic.claude-sonnet-5-5
                                   (Claude Sonnet 5.5's global inference
                                   profile; on bedrock-runtime it has no
                                   in-region on-demand ID)
  CCLF_TEMPERATURE                 optional; see backends/__init__.py, Scene 4

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
  6. PHI scrubbed from the text sent to the model (for the advisor, the
     report text passed to Advisor.propose()) OR that text contains only
     de-identified / coded content

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
# sampling_kwargs   the temperature setting, only if CCLF_TEMPERATURE is set.
# ===========================================================================

from __future__ import annotations
import os
import logging

from . import sampling_kwargs


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# logger — this module's logger, named "cclf.backends.bedrock" after the
#   module, so its messages are easy to trace back to this file.
logger = logging.getLogger(__name__)

# _DEFAULT_MODEL — the Bedrock model ID used when BEDROCK_MODEL_ID is not
#   set: Claude Sonnet 5.5 through its global cross-Region inference
#   profile. AWS's model card (October 2026) lists no in-region on-demand
#   access for it on bedrock-runtime, only the profiles us., eu. and
#   global.; use us. or eu. instead to keep requests in one geography.
_DEFAULT_MODEL = "global.anthropic.claude-sonnet-5-5"


# ===========================================================================
# SCENE 1 — THE AUDITION
# get_llm(): build a Claude-on-AWS chat model ready to answer the advisor
# ===========================================================================

def get_llm():
    """
    Build and return a LangChain ChatBedrock model.

    Enter:   (no arguments; settings come from environment variables)
    Exit:    a ChatBedrock for BEDROCK_MODEL_ID (default _DEFAULT_MODEL) in
             AWS_DEFAULT_REGION (default "us-east-1"), and a temperature
             only if CCLF_TEMPERATURE is set
             raises ImportError if langchain-aws is not installed

    No credentials are checked here. If boto3 cannot find any, the error
    appears when the model is first used (botocore NoCredentialsError),
    and Advisor.propose() then falls back to its conservative proposal.
    Checked October 2026 with langchain-aws 1.8.1 and boto3 1.43.109.
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
    # model_kwargs rather than as a top-level argument. Empty unless
    # CCLF_TEMPERATURE is set (Scene 4 of backends/__init__.py).
    return ChatBedrock(
        model_id=model_id,
        region_name=region,
        model_kwargs=sampling_kwargs(),
    )

# EXEUNT — end of file.

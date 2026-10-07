# CCL-F Commitment Agent — Compliance & HIPAA Gap Analysis

**Status:** Research / demonstration system  
**PHI handling:** NOT approved for PHI without completing all items in this document  
**Target deployment context:** Hospital clinical decision support (e.g., a hospital health-system IT organization)

---

## Executive summary

The CCL-F commitment agent architecture is well-suited to clinical decision support: it enforces structured decision-making, maintains a tamper-evident audit trail, and requires human approval before irreversible state transitions. However, the default configuration sends data to shared third-party LLM infrastructure, which is incompatible with HIPAA requirements for PHI.

This document identifies each gap, its severity, and the specific remediation required before hospital production deployment.

---

## Data flow — what goes where

```
evidence_buffer
    │
    ├── evidence_intake     → LLM endpoint  (evidence content sent verbatim)
    ├── acs_inference       → LLM endpoint  (evidence summary sent)
    ├── aco_detection       → LLM endpoint  (evidence content sent)
    ├── transition_evaluation → LLM endpoint (evidence summary sent)
    │
    ├── transition_guard    → NO external call (pure logic — safe)
    ├── human_review        → NO external call (local stdin/webhook — safe)
    ├── apply_transition    → NO external call (safe)
    └── terminate           → NO external call (safe)
    │
    └── audit_log → local disk (JSON file)
                 → OTel trace backend (span attributes include last_message)
                 → OTel log backend (full audit entries forwarded)
```

**Any PHI in `evidence_buffer` exits the hospital network at the four LLM nodes.**

---

## HIPAA gap analysis

### Gap 1 — LLM data egress (CRITICAL)
**Rule:** 45 CFR § 164.312(e) — Transmission security  
**Severity:** Critical — blocks any PHI use  

| Backend | Data destination | BAA available | HIPAA-eligible |
|---|---|---|---|
| `openai` (default) | OpenAI shared infrastructure | Yes, but must be executed | ⚠️ BAA required |
| `anthropic` | Anthropic shared infrastructure | Yes, but must be executed | ⚠️ BAA required |
| `azure` | Tenant-isolated Azure OpenAI | Covered under Microsoft EA BAA | ✅ Eligible |
| `bedrock` | AWS-isolated Bedrock endpoint | Covered under AWS BAA | ✅ Eligible |

**Remediation:** Use `azure` or `bedrock` backend. Set `CCLF_LLM_BACKEND=azure` or `CCLF_LLM_BACKEND=bedrock`. Do not use `openai` or `anthropic` backends with PHI until BAAs are executed and the architecture is reviewed by your Privacy Officer.

---

### Gap 2 — OTel observability data egress (HIGH)
**Rule:** 45 CFR § 164.312(e) — Transmission security  
**Severity:** High  

Span attributes forwarded to Datadog/Dynatrace include:
- `cclf.last_message` — last 256 chars of node output (may contain PHI snippets)
- Evidence counts and commitment state labels (lower risk, but still metadata)

Audit log entries forwarded via OTel log bridge include full `payload` dicts, which may contain evidence content summaries.

**Remediation options:**
1. **Preferred:** Route OTel to a BAA-covered, on-premises collector (e.g., OpenTelemetry Collector running in the hospital's VNet, forwarding to Datadog's HIPAA-eligible configuration or Azure Monitor).
2. **Short-term:** Strip `cclf.last_message` from span attributes in `observability.py` before hospital deployment (one-line change in `_wrap_node`).
3. **Minimum:** Disable observability entirely with `CCLF_OBSERVABILITY_ENABLED=false` until a compliant OTel destination is configured.

Datadog HIPAA-eligible configuration requires: Business Associate Agreement with Datadog, HIPAA-compliant account type, and US data residency. Contact your Datadog account team.

---

### Gap 3 — Audit log access controls (MEDIUM)
**Rule:** 45 CFR § 164.312(b) — Audit controls; § 164.312(a) — Access controls  
**Severity:** Medium  

The audit log currently writes to a local JSON file (`<scenario>_audit.json`) with no access controls. The hash chain protects integrity but not confidentiality or access logging.

**Remediation:**
- Write audit log to a BAA-covered, access-controlled store (Azure Blob Storage with RBAC, AWS S3 with bucket policy, or a database with row-level security).
- Log all read/write access to the audit store.
- Restrict write access to the agent process; restrict read access to authorized reviewers.

---

### Gap 4 — API key management (MEDIUM)
**Rule:** 45 CFR § 164.312(a) — Access controls  
**Severity:** Medium  

API keys are currently read from environment variables with no rotation enforcement, no audit of key usage, and no revocation workflow.

**Remediation:**
- Store keys in Azure Key Vault, AWS Secrets Manager, or HashiCorp Vault.
- Rotate keys on a defined schedule (90 days maximum recommended).
- Audit key access via the secret manager's access log.
- Use managed identities (Azure) or IAM roles (AWS) where possible to eliminate static keys entirely.

---

### Gap 5 — PHI in evidence_buffer (ARCHITECTURAL)
**Rule:** 45 CFR § 164.502 — Minimum necessary  
**Severity:** Architectural — must be designed before data model is finalised  

The `Evidence` dataclass has a free-text `content` field with no PHI constraints. In a clinical deployment, this field could receive raw clinical notes, patient identifiers, or incident report content.

**Remediation options (choose based on use case):**

**Option A — De-identification pre-processor**  
Add a `phi_scrub()` step before `evidence_intake` that runs content through a de-identification pipeline (Microsoft Presidio, AWS Comprehend Medical de-identification, or a custom NER model). The agent never sees raw PHI.

**Option B — Coded evidence only**  
Constrain `Evidence.content` to coded or structured signals only (ICD-10 codes, structured decision logs, timestamped system events). Raw clinical text never enters the agent.

**Option C — On-premises LLM only**  
If raw clinical text must be processed, all four LLM nodes must call a model running entirely within the hospital's network (on-premises GPU cluster, Azure Private Endpoint for Azure OpenAI, or Bedrock VPC endpoint with no internet egress).

---

### Gap 6 — No BAA verification at runtime (LOW)
**Severity:** Low — process gap, not technical  

The code cannot verify whether a BAA has been executed. `is_hipaa_eligible()` in `backends/__init__.py` returns True for `azure` and `bedrock` backends, but this is a configuration check only.

**Remediation:** Operational process control. Before any hospital deployment:
- Obtain signed BAA from Microsoft (Azure OpenAI) or AWS (Bedrock).
- File BAA with your Privacy Officer.
- Record BAA execution date in your system's risk register.
- Add a deployment checklist item: "BAA confirmed executed — [date] — [vendor]."

---

## Recommended configuration for a healthcare deployment

```bash
# Backend — Azure OpenAI (HIPAA-eligible under Microsoft EA BAA)
export CCLF_LLM_BACKEND=azure
export AZURE_OPENAI_API_KEY=<from-Key-Vault>
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
export AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
export AZURE_OPENAI_API_VERSION=2024-02-01

# Observability — disable until compliant OTel destination is configured
export CCLF_OBSERVABILITY_ENABLED=false

# Audit log — write to a controlled path, then move to Azure Blob
export CCLF_AUDIT_OUTPUT=/var/log/cclf/audit_$(date +%Y%m%d_%H%M%S).json
```

Or for AWS-native infrastructure:

```bash
export CCLF_LLM_BACKEND=bedrock
export BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
export AWS_DEFAULT_REGION=us-east-1
# Use IAM role — no static keys
```

---

## Pre-deployment checklist

Before handling any PHI with this system:

- [ ] BAA executed with LLM vendor (Microsoft or AWS)
- [ ] BAA filed with Privacy Officer and recorded in risk register
- [ ] `CCLF_LLM_BACKEND` set to `azure` or `bedrock`
- [ ] Network path to LLM endpoint verified (VNet / Private Endpoint — no public internet)
- [ ] OTel destination is BAA-covered or observability is disabled
- [ ] Audit log write path is access-controlled and access-logged
- [ ] API keys / credentials managed via secret manager (not env vars in shell)
- [ ] PHI handling approach selected (Gap 5) and implemented
- [ ] Security review completed by hospital IS security team
- [ ] Privacy Officer sign-off obtained

---

## What this system does well (strengths to retain)

- **Hash-chained audit log** — tamper-evident record of every decision event, which supports HIPAA audit control requirements (§ 164.312(b)) and is stronger than most clinical decision support systems provide.
- **Human-in-the-loop interrupt** — no irreversible commitment transition occurs without human approval, which aligns with clinical governance requirements.
- **Structurally blocked transitions** — the `transition_guard` node enforces safety invariants deterministically, without LLM involvement, which is the right pattern for safety-critical clinical contexts.
- **Backend abstraction** — swapping to a HIPAA-eligible LLM endpoint requires only an environment variable change, with no code modifications.

---

## References

- 45 CFR Part 164 — HIPAA Security Rule
- Microsoft Azure HIPAA/HITECH implementation guidance: https://docs.microsoft.com/en-us/azure/compliance/offerings/offering-hipaa-us
- AWS HIPAA Eligible Services: https://aws.amazon.com/compliance/hipaa-eligible-services-reference/
- Datadog HIPAA compliance: https://www.datadoghq.com/security/
- Microsoft Presidio (PHI de-identification): https://microsoft.github.io/presidio/

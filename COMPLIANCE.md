# Compliance notes: data flow and HIPAA gaps

**Status:** research prototype. Not approved for protected health information (PHI). This document lists what would have to change before it could be.

The scenarios in this repository are historical and contain no PHI. These notes are for anyone considering the runtime for a clinical setting, for example to monitor how safety signals about a device or workflow are closed.

---

## Where data goes

```
event (plain dict)
   │
   ├── op == "report"  → interpret node → Advisor → LLM endpoint
   │                     (the report text is sent verbatim)
   │
   └── every other op  → Supervisor (local, deterministic; no external call)
                              │
                              ├── audit trail  → memory; run_demo.py also writes it to
                              │                  a JSON file (default <scenario>_audit.json)
                              └── telemetry    → OTLP endpoint, if enabled
                                                 (span attributes: scenario, op;
                                                  metrics: counts by closure type,
                                                  escalation condition, gate outcome;
                                                  coherence scores)
```

Only `report` events reach a language model. Signal registration, classification, closure, escalation, exits and execution gates are computed locally, and the model's output is only ever a proposal that the supervisor checks under the same rules as anyone else's.

The three bundled scenarios contain no `report` events, so replaying them makes no model calls. The eval (`evals/closure_pressure.py`) does call a model, with the case text in the prompt.

---

## Gaps

### 1. Model data egress (critical for PHI)
45 CFR § 164.312(e), transmission security.

Report text sent to the advisor leaves the host.

| Backend | Destination | HIPAA eligibility |
|---|---|---|
| `openai` (default) | OpenAI API | Needs an executed BAA |
| `anthropic` | Anthropic API | Needs an executed BAA |
| `azure` | Azure OpenAI in your tenant | Eligible under a Microsoft BAA |
| `bedrock` | Amazon Bedrock in your account | Eligible under an AWS BAA |

`is_hipaa_eligible()` in `cclf/backends/__init__.py` reports only which backends are routed to BAA-eligible hosting. It cannot tell whether a BAA has been signed.

**Remediation:** use `azure` or `bedrock` over a private endpoint, or keep PHI out of report text (gap 4). Alternatively, skip the advisor and register and classify signals directly; the runtime does not need a model.

### 2. Free text in the audit trail (high)
45 CFR § 164.312(b) audit controls and § 164.312(a) access controls.

The audit trail stores signal descriptions, reversal paths, rationales, credibility characterizations, Rule 8 model updates and evidence sources verbatim. Decision descriptions and evidence content are held in memory but not logged. `run_demo.py` always writes the trail to a local JSON file with no access control. The hash chain detects tampering but provides neither confidentiality nor access logging.

**Remediation:** write the trail to an access-controlled, access-logged store covered by a BAA; restrict writes to the runtime and reads to authorized reviewers.

### 3. Telemetry (medium)
Spans carry only the scenario name and the event's `op`. Metrics carry closure types, escalation conditions, gate outcomes and coherence scores. No free text is exported, but the telemetry destination still receives operational metadata.

**Remediation:** send OTLP to a collector inside your network, use a BAA-covered destination, or set `CCLF_OBSERVABILITY_ENABLED=false`.

### 4. PHI in free-text fields (architectural)
45 CFR § 164.502(b), minimum necessary.

`Signal.description`, `Evidence.content`, decision descriptions, reversal paths and every rationale are free text.

**Options:**
- De-identify text (for example with Microsoft Presidio) before it becomes an event.
- Use coded or structured content only: device and event identifiers, references to records held elsewhere.
- If raw clinical text must reach a model, use a model reachable only inside your network.

### 5. Credentials (medium)
API keys come from environment variables. Use a secret manager or managed identity (Azure) or IAM role (AWS), and rotate keys on a schedule.

### 6. Identity (medium)
The runtime requires an actor name on every state-changing operation and logs it, but it does not authenticate that name. A deployment would bind the actor to an authenticated identity before the call reaches the supervisor, especially for overrides and Rule 4 acceptance.

---

## What helps here

- **Deterministic rules.** The model only proposes. Closure typing, escalation and gates are code, and a model cannot override them.
- **Tamper-evident audit.** Every state change, escalation, acceptance and override is hash-chained with actor, rationale and logical time. Overrides are logged permanently and cannot override Rule 4 acceptance.
- **No model required.** The runtime works with no model at all; the advisor is optional.

## Pre-deployment checklist

- [ ] PHI approach chosen (gap 4) and implemented
- [ ] Advisor disabled, or backend `azure`/`bedrock` behind a private endpoint with an executed BAA
- [ ] Audit trail written to an access-controlled, access-logged store
- [ ] Telemetry kept in-network, BAA-covered, or disabled
- [ ] Actor names bound to authenticated identities
- [ ] Credentials in a secret manager
- [ ] Security review and Privacy Officer sign-off

## References

- 45 CFR Part 164 (HIPAA Security and Privacy Rules)
- AWS HIPAA Eligible Services Reference: https://aws.amazon.com/compliance/hipaa-eligible-services-reference/
- Microsoft Presidio: https://microsoft.github.io/presidio/

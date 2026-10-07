# CCL-F Observability Setup

The CCL-F agent emits OpenTelemetry traces, metrics, and logs.
Both Datadog and Dynatrace ingest OTLP natively — no SDK lock-in.

---

## What gets instrumented

### Traces

A root `cclf.session` span wraps each full run. Inside it, every LangGraph
node produces a child span:

```
cclf.session  [scenario=therac25, thread_id=...]
  └── cclf.node.evidence_intake      [evidence_count, commitment_state]
  └── cclf.node.acs_inference        [acs.p_open, acs.p_trajectory, ...]
  └── cclf.node.aco_detection        [aco_detected]
  └── cclf.node.transition_evaluation
  └── cclf.node.transition_guard     [proposed_transition]
  └── cclf.node.human_review         [human_approval]
  └── cclf.node.apply_transition     [commitment_state_after]
  └── cclf.node.terminate
```

`transition_guard` is always the fastest span — it's LLM-free.
LLM nodes (`acs_inference`, `aco_detection`, `transition_evaluation`) carry
the highest latency and token cost.

### Metrics

| Metric | Type | Tags |
|---|---|---|
| `cclf.node.duration_ms` | Histogram | `node`, `commitment_state`, `aco_detected` |
| `cclf.acs.snapshot` | Histogram | `acs.state` |
| `cclf.transitions.total` | Counter | `outcome`, `from_state`, `to_state` |
| `cclf.aco.detections` | Counter | `conditions` |
| `cclf.evidence.admissible_ratio_obs` | Histogram | `evidence.total` |

### Logs

Audit chain entries are forwarded via the OTel log bridge. Each entry
carries `seq`, `event`, `from_state`, `to_state`, `entry_hash`, `prev_hash`.
The hash chain is verifiable independently of the log backend.

---

## Datadog

### Option A — Datadog Agent (recommended for production)

The Datadog Agent accepts OTLP on port 4317 (gRPC) or 4318 (HTTP).

**1. Enable OTLP in the Agent** (`datadog.yaml`):
```yaml
otlp_config:
  receiver:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
```

**2. Set environment variables**:
```bash
export OTEL_SERVICE_NAME=cclf-agents
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export DD_ENV=production
export DD_VERSION=0.2.0
```

**3. Run**:
```bash
python run_demo.py therac25
```

Traces appear in APM → Services → `cclf-agents`.
Metrics appear under Metrics Explorer with `cclf.*` prefix.

### Option B — Datadog LLM Observability (for LLM-specific dashboards)

Datadog has a dedicated LLM Observability product that captures prompt/response
pairs, token costs, and latency per model call. To enable it alongside OTLP:

```bash
pip install ddtrace
export DD_LLMOBS_ENABLED=1
export DD_LLMOBS_ML_APP=cclf-agents
export DD_LLMOBS_AGENTLESS_ENABLED=1   # if no local Agent
export DD_API_KEY=<your-api-key>
export DD_TRACE_OTEL_ENABLED=1         # bridge OTel → ddtrace
```

Then run via ddtrace:
```bash
ddtrace-run python run_demo.py therac25
```

LLM spans (`acs_inference`, `aco_detection`, `transition_evaluation`) will
appear in LLM Observability with model, tokens, and latency breakdowns.

### Suggested Datadog monitors

```
# ACO detection alert
metric: sum:cclf.aco.detections{*}.as_count()
condition: > 0
message: "CCL-F agent detected Adversarial Commitment Opacity. Review audit log."

# ACS divergence alert
metric: avg:cclf.acs.snapshot{cclf.acs.state:trajectory}
condition: > 0.7
message: "ACS trajectory probability > 70% — formal state may be diverging."

# Transition blocked alert
metric: sum:cclf.transitions.total{cclf.transition.outcome:blocked}.as_count()
condition: > 0
message: "Structurally blocked transition attempted — check audit chain."
```

---

## Dynatrace

Dynatrace ingests OTLP directly via its API endpoint.

**1. Get your ingest URL**:
```
https://<YOUR_ENV_ID>.live.dynatrace.com/api/v2/otlp
```

**2. Create an API token** with scopes:
- `metrics.ingest`
- `logs.ingest`
- `openTelemetryTrace.ingest`

**3. Set environment variables**:
```bash
export OTEL_SERVICE_NAME=cclf-agents
export OTEL_EXPORTER_OTLP_ENDPOINT=https://<YOUR_ENV_ID>.live.dynatrace.com/api/v2/otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Api-Token <YOUR_DT_API_TOKEN>"
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf   # Dynatrace prefers HTTP
```

**4. Install the HTTP exporter** (Dynatrace uses HTTP/protobuf, not gRPC):
```bash
pip install opentelemetry-exporter-otlp-proto-http
```

Update `observability.py` to use the HTTP exporter:
```python
# In CCLFInstrumentor.setup(), replace:
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
# with:
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
```

**5. Run**:
```bash
python run_demo.py therac25
```

Traces appear in Dynatrace → Distributed Traces → filter by `cclf-agents`.
Metrics appear in Metrics Browser under `cclf.*`.
Davis AI anomaly detection will flag unusual node latency spikes automatically.

### Suggested Dynatrace metric events

In Settings → Anomaly Detection → Custom events for alerting:
```
cclf.aco.detections  threshold > 0   severity: ERROR
cclf.node.duration_ms{node=acs_inference}  threshold > 5000ms  severity: WARNING
```

---

## Disabling observability

```bash
python run_demo.py therac25 --no-obs
# or
export CCLF_OBSERVABILITY_ENABLED=false
```

All instrumentation is no-op when disabled. The graph runs identically.

---

## Install

```bash
# Core OTel SDK + gRPC exporter (Datadog Agent / gRPC endpoint)
pip install \
  opentelemetry-sdk \
  opentelemetry-exporter-otlp-proto-grpc

# HTTP exporter (Dynatrace)
pip install opentelemetry-exporter-otlp-proto-http

# Datadog ddtrace bridge (Option B only)
pip install ddtrace
```

Or install everything:
```bash
pip install -r requirements-obs.txt
```

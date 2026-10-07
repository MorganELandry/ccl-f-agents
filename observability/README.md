# Observability

The runtime can emit OpenTelemetry traces and metrics over OTLP, which Datadog and Dynatrace both ingest. Observability is optional: without the packages in `requirements-obs.txt`, or with it switched off, every call is a no-op and the replay runs the same.

The authoritative record is the hash-chained audit trail (`--audit file.json` on `run_demo.py`), not the telemetry. Telemetry is for dashboards and alerts; the audit trail is what you verify.

## What is emitted

### Traces

One root span per replay, with one child span per graph node per event:

```
cclf.replay                 [scenario]
  └── cclf.node.interpret   [op]
  └── cclf.node.apply       [op]
  └── cclf.node.assess      [op]
  ... (three node spans per event)
```

`interpret` only calls the model for `report` events; every other node is deterministic.

### Metrics

Derived from audit entries by `Instrumentor.record_audit_entry`. `run_demo.py` forwards each event's new entries after the event; a program calling `replay()` directly must do the same (see `on_event`) to get metrics.

| Metric | Type | Tag | Counted when |
|---|---|---|---|
| `cclf.closures` | Counter | `type` (evidence, authority, role_switch, lock_in) | a transition carries a closure type |
| `cclf.escalations` | Counter | `condition` (one of the nine Layer 2 escalation conditions) | an escalation opens a structural review |
| `cclf.gate.outcomes` | Counter | `outcome` (EXECUTION_PERMITTED, EXECUTION_BLOCKED, GATE_OVERRIDE, EXECUTION_REFUSED) | an execution request is decided |
| `cclf.coherence` | Histogram | | an execution request reports a coherence score |

Audit entries are not forwarded as OTel logs.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `CCLF_OBSERVABILITY_ENABLED` | `true` | `false` turns everything off (same as `--no-obs`) |
| `OTEL_SERVICE_NAME` | `ccl-f-agents` | service name on every span and metric |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint |

The exporters are the OTLP **gRPC** ones.

### Datadog

Enable OTLP ingest on the Datadog Agent (`otlp_config.receiver.protocols.grpc.endpoint: 0.0.0.0:4317` in `datadog.yaml`), then:

```bash
pip install -r requirements-obs.txt
export OTEL_SERVICE_NAME=ccl-f-agents
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
python run_demo.py challenger
```

Traces appear under APM → Services; metrics under the `cclf.` prefix.

### Dynatrace

Dynatrace's OTLP API takes HTTP/protobuf, not gRPC. Point an OpenTelemetry Collector at Dynatrace and send this runtime's gRPC output to the Collector, or swap the two `...proto.grpc...` exporter imports in `cclf/observability.py` for their `...proto.http...` equivalents (the HTTP exporter is listed in `requirements-obs.txt`).

## Suggested alerts

```
# Any override of a failing gate
sum:cclf.gate.outcomes{outcome:GATE_OVERRIDE}.as_count()  > 0

# Escalations that indicate the loop is not closing
sum:cclf.escalations{condition:recurrence_threshold}.as_count()              > 0
sum:cclf.escalations{condition:authority_closure_count}.as_count()           > 0
sum:cclf.escalations{condition:lock_in_with_open_constraints}.as_count()     > 0
sum:cclf.escalations{condition:suppressed_before_execution}.as_count()       > 0

# Authority closures outpacing evidence closures
sum:cclf.closures{type:authority}.as_count() > sum:cclf.closures{type:evidence}.as_count()
```

Tag values are the enum values from `cclf/types.py` (`EscalationCondition`, `ClosureType`).

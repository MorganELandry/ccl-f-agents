"""
CCL-F Observability — OpenTelemetry Instrumentation
=====================================================
Platform-agnostic OTel instrumentation for the CCL-F commitment agent.
Works with any OTel-compatible backend:

  Datadog:   export via OTLP exporter → Datadog Agent (port 4317)
             OR use ddtrace with DD_TRACE_OTEL_ENABLED=1
  Dynatrace: export via OTLP exporter → Dynatrace OTLP ingest endpoint

Configuration is entirely via environment variables (12-factor):

  OTEL_SERVICE_NAME          cclf-commitment-agent
  OTEL_EXPORTER_OTLP_ENDPOINT  http://localhost:4317   (Datadog Agent)
                                https://<env>.live.dynatrace.com/api/v2/otlp  (Dynatrace)
  OTEL_EXPORTER_OTLP_HEADERS   Authorization=Api-Token <token>  (Dynatrace)
                                DD-API-KEY=<key>                (Datadog direct ingest)
  OTEL_TRACES_EXPORTER       otlp        (default)
  OTEL_METRICS_EXPORTER      otlp        (default)
  OTEL_LOGS_EXPORTER         otlp        (default)
  CCLF_OBSERVABILITY_ENABLED true        (set false to disable all instrumentation)

Datadog-specific:
  DD_LLMOBS_ENABLED=1        Enables Datadog LLM Observability product
  DD_LLMOBS_ML_APP=cclf-agent

Dynatrace-specific:
  DT_API_TOKEN               Required for direct OTLP ingest
  DT_ENVIRONMENT_ID          Your Dynatrace environment ID

Usage
-----
  from cclf.observability import get_instrumentor, instrument_nodes

  # At startup
  instrumentor = get_instrumentor()
  instrumentor.setup()

  # Wrap nodes before graph compilation
  from cclf import nodes
  instrument_nodes(nodes, instrumentor)
"""

from __future__ import annotations

import functools
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Optional OTel imports — graceful degradation if not installed
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

# Optional: structured log bridge
try:
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry._logs import set_logger_provider
    _LOG_BRIDGE_AVAILABLE = True
except ImportError:
    _LOG_BRIDGE_AVAILABLE = False

logger = logging.getLogger(__name__)

_ENABLED = os.environ.get("CCLF_OBSERVABILITY_ENABLED", "true").lower() == "true"
_SERVICE  = os.environ.get("OTEL_SERVICE_NAME", "cclf-commitment-agent")
_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


# ---------------------------------------------------------------------------
# Instrumentor
# ---------------------------------------------------------------------------

class CCLFInstrumentor:
    """
    OTel instrumentation for the CCL-F commitment agent.

    Provides:
      - Tracer for span creation (node-level and sub-operation spans)
      - Meter for custom metrics (ACS distribution, ACO counts, transitions)
      - Audit log forwarding via OTel log bridge
    """

    def __init__(self):
        self._tracer: Optional[Any]  = None
        self._meter:  Optional[Any]  = None
        self._ready:  bool           = False

        # Metric instruments (created after setup())
        self._acs_gauges:              dict = {}
        self._evidence_admissible_ratio: Any = None
        self._transition_counter:        Any = None
        self._aco_counter:               Any = None
        self._node_duration_histogram:   Any = None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """
        Initialise OTel SDK with OTLP exporters.
        Safe to call multiple times (idempotent).
        Falls back to no-op if OTel packages not installed.
        """
        if self._ready:
            return

        if not _ENABLED:
            logger.info("[cclf-obs] Observability disabled (CCLF_OBSERVABILITY_ENABLED=false)")
            return

        if not _OTEL_AVAILABLE:
            logger.warning(
                "[cclf-obs] opentelemetry packages not installed. "
                "Run: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc"
            )
            return

        try:
            resource = Resource(attributes={SERVICE_NAME: _SERVICE})

            # Traces
            trace_provider = TracerProvider(resource=resource)
            trace_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=_ENDPOINT))
            )
            trace.set_tracer_provider(trace_provider)
            self._tracer = trace.get_tracer("cclf.agent")

            # Metrics
            metric_reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=_ENDPOINT),
                export_interval_millis=int(
                    os.environ.get("OTEL_METRIC_EXPORT_INTERVAL_MS", "10000")
                ),
            )
            meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(meter_provider)
            self._meter = metrics.get_meter("cclf.agent")

            # Log bridge (optional)
            if _LOG_BRIDGE_AVAILABLE:
                log_provider = LoggerProvider(resource=resource)
                log_provider.add_log_record_processor(
                    BatchLogRecordProcessor(OTLPLogExporter(endpoint=_ENDPOINT))
                )
                set_logger_provider(log_provider)

            self._init_metrics()
            self._ready = True
            logger.info(f"[cclf-obs] OTel instrumentation active → {_ENDPOINT}")

        except Exception as exc:
            logger.warning(
                f"[cclf-obs] OTel setup failed ({exc}); running without observability."
            )
            self._tracer = None
            self._meter  = None
            self._ready  = False

    def _init_metrics(self) -> None:
        """Create all metric instruments."""
        m = self._meter

        # ACS probability gauges (one per state)
        for state_name in ("open", "trajectory", "authority", "execution"):
            self._acs_gauges[state_name] = m.create_observable_gauge(
                name=f"cclf.acs.p_{state_name}",
                description=f"ACS inferred probability of {state_name.upper()} state",
                unit="1",
            )

        self._acs_confidence = m.create_observable_gauge(
            name="cclf.acs.confidence",
            description="ACS inference confidence",
            unit="1",
        )

        self._evidence_admissible_ratio = m.create_observable_gauge(
            name="cclf.evidence.admissible_ratio",
            description="Fraction of evidence items that passed novelty+independence guards",
            unit="1",
        )

        self._transition_counter = m.create_counter(
            name="cclf.transitions.total",
            description="Commitment state transitions, tagged by outcome",
            unit="1",
        )

        self._aco_counter = m.create_counter(
            name="cclf.aco.detections",
            description="Number of ACO detection events",
            unit="1",
        )

        self._node_duration_histogram = m.create_histogram(
            name="cclf.node.duration_ms",
            description="Node execution duration in milliseconds",
            unit="ms",
        )

    # ------------------------------------------------------------------
    # Span helpers
    # ------------------------------------------------------------------

    @contextmanager
    def span(self, name: str, attributes: dict | None = None):
        """
        Context manager for a traced span.
        No-op if OTel not available or disabled.
        """
        if not self._ready or self._tracer is None:
            yield None
            return

        with self._tracer.start_as_current_span(name) as s:
            if attributes:
                for k, v in attributes.items():
                    s.set_attribute(k, str(v))
            yield s

    def record_node_duration(self, node_name: str, duration_ms: float,
                              state_name: str, aco_detected: bool) -> None:
        if not self._ready or self._node_duration_histogram is None:
            return
        self._node_duration_histogram.record(duration_ms, {
            "cclf.node":             node_name,
            "cclf.commitment_state": state_name,
            "cclf.aco_detected":     str(aco_detected).lower(),
        })

    def record_transition(self, outcome: str, from_state: str,
                           to_state: str | None = None) -> None:
        """outcome: 'proposed' | 'blocked' | 'applied' | 'rejected_human'"""
        if not self._ready or self._transition_counter is None:
            return
        self._transition_counter.add(1, {
            "cclf.transition.outcome":    outcome,
            "cclf.transition.from_state": from_state,
            "cclf.transition.to_state":   to_state or "none",
        })

    def record_aco_detection(self, conditions: list[str]) -> None:
        if not self._ready or self._aco_counter is None:
            return
        self._aco_counter.add(1, {
            "cclf.aco.conditions": ",".join(conditions),
        })

    def record_acs_snapshot(self, p_open: float, p_trajectory: float,
                             p_authority: float, p_execution: float,
                             confidence: float) -> None:
        """
        Forward ACS probabilities as gauge observations.
        In production: wire these to observable callbacks for pull-based metrics.
        Here we use a histogram as a push-compatible alternative.
        """
        if not self._ready or self._meter is None:
            return
        hist = self._meter.create_histogram(
            "cclf.acs.snapshot",
            description="ACS probability snapshot (push-mode fallback)",
            unit="1",
        )
        for state_name, val in [
            ("open", p_open), ("trajectory", p_trajectory),
            ("authority", p_authority), ("execution", p_execution),
        ]:
            hist.record(val, {"cclf.acs.state": state_name})

    def record_evidence_ratio(self, admissible: int, total: int) -> None:
        if not self._ready or self._meter is None:
            return
        ratio = admissible / total if total > 0 else 0.0
        h = self._meter.create_histogram(
            "cclf.evidence.admissible_ratio_obs",
            description="Evidence admissible ratio observation",
            unit="1",
        )
        h.record(ratio, {"cclf.evidence.total": str(total)})

    def forward_audit_entry(self, entry) -> None:
        """
        Forward an AuditEntry to OTel logs.
        The hash-chained audit log is the CCL-F source of truth;
        this is a secondary observability copy for dashboards.
        """
        if not _LOG_BRIDGE_AVAILABLE or not self._ready:
            return
        import json
        otel_logger = logging.getLogger("cclf.audit")
        otel_logger.info(
            json.dumps({
                "seq":        entry.sequence,
                "event":      entry.event_type,
                "from_state": str(entry.from_state),
                "to_state":   str(entry.to_state),
                "entry_hash": entry.entry_hash,
                "prev_hash":  entry.prev_hash,
                "payload":    entry.payload,
            })
        )


# ---------------------------------------------------------------------------
# Node wrapper decorator
# ---------------------------------------------------------------------------

def _wrap_node(fn: Callable, node_name: str, instrumentor: CCLFInstrumentor) -> Callable:
    """
    Wraps a LangGraph node function with:
      - A trace span named 'cclf.node.<node_name>'
      - Duration histogram recording
      - State-derived span attributes
      - Audit entry forwarding for the entries added during this node
    """
    @functools.wraps(fn)
    def wrapped(state):
        attrs = {
            "cclf.node":             node_name,
            "cclf.commitment_state": str(state.commitment_state),
            "cclf.aco_detected":     str(state.aco_detected).lower(),
            "cclf.evidence_count":   len(state.evidence_buffer),
            "cclf.audit_seq":        len(state.audit_log),
        }

        audit_len_before = len(state.audit_log)
        t0 = time.perf_counter()

        with instrumentor.span(f"cclf.node.{node_name}", attrs) as span:
            result = fn(state)
            duration_ms = (time.perf_counter() - t0) * 1000

            # Post-node attributes
            if span is not None:
                span.set_attribute("cclf.commitment_state_after",
                                   str(result.commitment_state))
                span.set_attribute("cclf.aco_detected_after",
                                   str(result.aco_detected).lower())
                if result.proposed_transition:
                    span.set_attribute("cclf.proposed_transition",
                                       str(result.proposed_transition))
                if result.messages:
                    span.set_attribute("cclf.last_message", result.messages[-1][:256])

            # Metrics
            instrumentor.record_node_duration(
                node_name, duration_ms,
                str(result.commitment_state), result.aco_detected
            )

            # Forward any new audit entries
            new_entries = result.audit_log[audit_len_before:]
            for entry in new_entries:
                instrumentor.forward_audit_entry(entry)

            # Node-specific metric recording
            if node_name == "acs_inference":
                a = result.acs_estimate
                instrumentor.record_acs_snapshot(
                    a.p_open, a.p_trajectory, a.p_authority, a.p_execution, a.confidence
                )

            if node_name == "evidence_intake":
                admissible = sum(1 for e in result.evidence_buffer if e.is_admissible())
                instrumentor.record_evidence_ratio(admissible, len(result.evidence_buffer))

            if node_name == "aco_detection" and result.aco_detected:
                # Extract conditions from the most recent ACO audit entry if present
                aco_entries = [e for e in new_entries if e.event_type == "ACO_DETECTED"]
                conditions = []
                if aco_entries:
                    conditions = aco_entries[-1].payload.get("conditions_met", [])
                instrumentor.record_aco_detection(conditions)

            if node_name == "apply_transition":
                applied = [e for e in new_entries if e.event_type == "TRANSITION_APPLIED"]
                blocked = [e for e in new_entries if e.event_type == "TRANSITION_BLOCKED"]
                for e in applied:
                    instrumentor.record_transition(
                        "applied",
                        e.payload.get("from", "unknown"),
                        e.payload.get("to", "unknown"),
                    )
                for e in blocked:
                    instrumentor.record_transition(
                        "blocked",
                        e.payload.get("from", "unknown"),
                    )

        return result
    return wrapped


def instrument_nodes(nodes_module, instrumentor: CCLFInstrumentor) -> None:
    """
    Monkey-patch all node functions in the nodes module with OTel wrappers.
    Call this before build_graph() so the graph compiles with instrumented nodes.

    Usage:
        from cclf import nodes, observability
        obs = observability.get_instrumentor()
        obs.setup()
        observability.instrument_nodes(nodes, obs)
        graph = build_graph()
    """
    node_names = [
        "evidence_intake",
        "acs_inference",
        "aco_detection",
        "transition_evaluation",
        "transition_guard",
        "human_review",
        "apply_transition",
        "terminate",
    ]
    for name in node_names:
        original = getattr(nodes_module, name, None)
        if original is not None:
            setattr(nodes_module, name, _wrap_node(original, name, instrumentor))
            logger.debug(f"[cclf-obs] Instrumented node: {name}")


# ---------------------------------------------------------------------------
# Session span context manager
# ---------------------------------------------------------------------------

@contextmanager
def session_span(instrumentor: CCLFInstrumentor, scenario: str, thread_id: str):
    """
    Root span for a full CCL-F agent session.
    Wrap your main run loop with this to get end-to-end trace correlation.

    Usage:
        with session_span(instrumentor, scenario="therac25", thread_id=tid):
            for batch in evidence_batches:
                state = run_batch(graph, state, config, batch, label)
    """
    attrs = {
        "cclf.scenario":  scenario,
        "cclf.thread_id": thread_id,
    }
    with instrumentor.span("cclf.session", attrs) as span:
        yield span


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_instrumentor: Optional[CCLFInstrumentor] = None

def get_instrumentor() -> CCLFInstrumentor:
    """Return the process-level CCLFInstrumentor singleton."""
    global _instrumentor
    if _instrumentor is None:
        _instrumentor = CCLFInstrumentor()
    return _instrumentor

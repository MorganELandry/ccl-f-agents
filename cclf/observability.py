"""
OpenTelemetry tracing and metrics for the event pipeline.

One span per pipeline node, inside one root span per replay session, plus
counters for the things CCL-F v0.2 says should be visible: closures by type,
escalations by condition, and execution-gate outcomes, and a histogram of
coherence scores. Everything degrades to a no-op if the OpenTelemetry
packages are missing, if CCLF_OBSERVABILITY_ENABLED is "false" when setup()
runs, or if setup fails.

Export goes to an OTLP endpoint (OTEL_EXPORTER_OTLP_ENDPOINT), which Datadog,
Dynatrace and most collectors accept; see observability/README.md.
"""

from __future__ import annotations

import functools
import logging
import os
from contextlib import contextmanager
from typing import Callable, Optional

logger = logging.getLogger("cclf.observability")

SERVICE_NAME_DEFAULT = "ccl-f-agents"
ENDPOINT_DEFAULT = "http://localhost:4317"

try:  # optional dependency: requirements-obs.txt
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


class Instrumentor:
    """Holds the tracer and instruments; every method is safe when inactive."""

    def __init__(self) -> None:
        self.active = False
        self._tracer = None
        self._closures = self._escalations = self._gates = self._coherence = None

    def setup(self) -> bool:
        if os.environ.get("CCLF_OBSERVABILITY_ENABLED", "true").lower() != "true":
            logger.info("[cclf-obs] observability disabled")
            return False
        if not OTEL_AVAILABLE:
            logger.info("[cclf-obs] opentelemetry not installed: pip install -r "
                        "requirements-obs.txt")
            return False
        try:
            service = os.environ.get("OTEL_SERVICE_NAME", SERVICE_NAME_DEFAULT)
            endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ENDPOINT_DEFAULT)
            resource = Resource(attributes={SERVICE_NAME: service})
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
            trace.set_tracer_provider(tracer_provider)
            meter_provider = MeterProvider(resource=resource, metric_readers=[
                PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint))])
            metrics.set_meter_provider(meter_provider)
            self._tracer = trace.get_tracer("cclf")
            meter = metrics.get_meter("cclf")
            self._closures = meter.create_counter("cclf.closures", description="closures by type")
            self._escalations = meter.create_counter("cclf.escalations",
                                                     description="escalations by condition")
            self._gates = meter.create_counter("cclf.gate.outcomes",
                                               description="execution gate outcomes")
            self._coherence = meter.create_histogram("cclf.coherence",
                                                     description="coherence score")
            self.active = True
        except Exception as exc:  # never let telemetry break a run
            logger.warning(f"[cclf-obs] setup failed, continuing without: {exc}")
            self.active = False
        return self.active

    @contextmanager
    def span(self, name: str, **attributes):
        if not self.active:
            yield None
            return
        with self._tracer.start_as_current_span(name) as s:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
            yield s

    def wrap(self, name: str, fn: Callable) -> Callable:
        """Node wrapper for graph.build_graph(wrap=...): one span per node call."""
        @functools.wraps(fn)
        def wrapped(state):
            with self.span(f"cclf.node.{name}", op=state.get("event", {}).get("op", "")):
                return fn(state)
        return wrapped

    def record_audit_entry(self, event: str, payload: dict) -> None:
        """Turn audit events into metrics (called by the demo after each event)."""
        if not self.active:
            return
        if event == "TRANSITION" and payload.get("closure_type"):
            self._closures.add(1, {"type": str(payload["closure_type"])})
        elif event == "ESCALATION":
            self._escalations.add(1, {"condition": str(payload.get("condition"))})
        elif event in ("EXECUTION_PERMITTED", "EXECUTION_BLOCKED", "GATE_OVERRIDE",
                       "EXECUTION_REFUSED"):
            self._gates.add(1, {"outcome": event})
            if "coherence" in payload:
                self._coherence.record(float(payload["coherence"]))


_instrumentor: Optional[Instrumentor] = None


def get_instrumentor() -> Instrumentor:
    global _instrumentor
    if _instrumentor is None:
        _instrumentor = Instrumentor()
    return _instrumentor

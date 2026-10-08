"""
THE WATCHERS IN THE WINGS
A Play in One Act and Six Scenes
================================

PROLOGUE
--------
OpenTelemetry tracing and metrics for the event pipeline.

One span per pipeline node, inside one root span per replay session, plus
counters for the things CCL-F v0.2 says should be visible: closures by type,
escalations by condition, and execution-gate outcomes, and a histogram of
coherence scores. Everything degrades to a no-op if the OpenTelemetry
packages are missing, if CCLF_OBSERVABILITY_ENABLED is "false" when setup()
runs, or if setup fails.

Export goes to an OTLP endpoint (OTEL_EXPORTER_OTLP_ENDPOINT), which Datadog,
Dynatrace and most collectors accept; see observability/README.md.

Where this fits: the supervisor's audit trail is the permanent record;
telemetry is an optional live window onto the same activity. run_demo.py
calls get_instrumentor().setup(), passes Instrumentor.wrap to
graph.replay() so each node gets a span, and feeds each new audit entry to
record_audit_entry(). Nothing in the supervisor depends on this file, and a
failure here must never change or stop a run.

THE PLAYBILL (what happens in this file)
    ACT I    Instrumentor              holds the tracer and the metric instruments
      Scene 1  __init__()              start inactive, with nothing set up
      Scene 2  setup()                 connect to OpenTelemetry, or stay a no-op
      Scene 3  span()                  a context manager that opens one span
      Scene 4  wrap()                  wrap a graph node so each call gets a span
      Scene 5  record_audit_entry()    turn audit events into metric updates
    Scene 6  get_instrumentor()        the one shared Instrumentor (lazy singleton)

READER'S NOTE — OpenTelemetry in a nutshell
    OpenTelemetry ("OTel") is a vendor-neutral standard for sending
    telemetry from a program to a monitoring backend.
      Span        one timed piece of work with a name and attributes
                  (key/value tags). Spans opened inside other spans become
                  their children, so a trace shows a tree: here, the
                  "cclf.replay" span (opened in run_demo.py) holds one
                  "cclf.node.<name>" span per node call.
      Counter     a metric that only goes up; .add(1, {tags}) counts one
                  occurrence, tagged so a dashboard can group by tag.
      Histogram   a metric that records a distribution of values;
                  .record(x) adds one observation (here, coherence scores).
      Provider    the SDK object that owns tracers or meters and decides
                  where their data goes. TracerProvider + BatchSpanProcessor
                  batch spans up; MeterProvider + PeriodicExportingMetricReader
                  send metrics on a timer.
      OTLP        the OpenTelemetry Protocol, the wire format the exporters
                  speak (over gRPC here) to a collector or vendor endpoint.

READER'S NOTE — the no-op fallback
    The OpenTelemetry packages are optional (requirements-obs.txt). The
    import block below is wrapped in try/except ImportError and records the
    result in OTEL_AVAILABLE. An Instrumentor starts with active=False, and
    every method checks `active` first and does nothing when it is False.
    So callers never need to ask "is telemetry on?"; they just call the
    methods, and the calls are harmless when it is off.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# __future__.annotations   type hints are stored as text, not evaluated.
# functools                functools.wraps, used in wrap() (see Scene 4).
# logging                  info / warning messages about setup.
# os                       reads environment variables.
# contextlib.contextmanager   turns the generator span() into a "with"-able
#                          context manager (see Scene 3).
# typing                   Callable, Optional for type hints.
# opentelemetry.*          (optional) the API (metrics, trace), the OTLP gRPC
#                          exporters, and the SDK providers, readers, span
#                          processor and Resource. Imported inside try/except
#                          so the module still loads without them.
# ===========================================================================

from __future__ import annotations

import functools
import logging
import os
from contextlib import contextmanager
from typing import Callable, Optional

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


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# OTEL_AVAILABLE — True if every OpenTelemetry import above succeeded, False
#   if any was missing. It is set inside the import block just above (not
#   here) because its value IS the outcome of those imports. setup() reads
#   it; tests patch it to False to simulate a missing package.

# logger — this module's logger, named "cclf.observability", for the
#   "disabled", "not installed" and "setup failed" messages.
logger = logging.getLogger("cclf.observability")

# SERVICE_NAME_DEFAULT — the service name shown in the monitoring backend
#   when OTEL_SERVICE_NAME is not set.
SERVICE_NAME_DEFAULT = "ccl-f-agents"

# ENDPOINT_DEFAULT — where to send OTLP data when OTEL_EXPORTER_OTLP_ENDPOINT
#   is not set: a collector on this machine, on the standard OTLP gRPC port.
ENDPOINT_DEFAULT = "http://localhost:4317"

# _instrumentor — the single shared Instrumentor, created on first use by
#   get_instrumentor() (Scene 6). None until then. It can sit up here even
#   though its type is the class defined below, because its value is None
#   and, with `from __future__ import annotations`, the annotation is not
#   evaluated when this line runs.
_instrumentor: Optional[Instrumentor] = None


# ===========================================================================
# ACT I — THE INSTRUMENTOR
# One object that owns the tracer and the four metric instruments
# ===========================================================================

class Instrumentor:
    """
    Holds the tracer and instruments; every method is safe when inactive.

    Attributes:
      active         True only after setup() fully succeeded
      _tracer        the OpenTelemetry tracer, or None
      _closures      counter "cclf.closures", tagged by closure type
      _escalations   counter "cclf.escalations", tagged by condition
      _gates         counter "cclf.gate.outcomes", tagged by gate outcome
      _coherence     histogram "cclf.coherence" of coherence scores
    """

    # =======================================================================
    # ACT I, SCENE 1 — CURTAIN DOWN
    # __init__(): start inactive, with no tracer and no instruments
    # =======================================================================

    def __init__(self) -> None:
        """
        Create an inactive Instrumentor.

        Enter:   (nothing)
        Exit:    active=False; tracer and instruments all None
        """
        self.active = False
        self._tracer = None
        # Chained assignment: all four names are set to None at once.
        self._closures = self._escalations = self._gates = self._coherence = None

    # =======================================================================
    # ACT I, SCENE 2 — RAISING THE CURTAIN
    # setup(): connect to OpenTelemetry if enabled and installed
    # =======================================================================

    def setup(self) -> bool:
        """
        Configure tracing and metrics export, or stay a no-op.

        Enter:   (nothing; reads CCLF_OBSERVABILITY_ENABLED, OTEL_SERVICE_NAME
                 and OTEL_EXPORTER_OTLP_ENDPOINT from the environment)
        Exit:    True if telemetry is now active, False otherwise
                 side effect: on success, installs global tracer and meter
                 providers and creates this object's instruments

        Returns False (and leaves active False) when the environment variable
        is anything other than "true" (case-insensitive; unset counts as
        "true"), or when OpenTelemetry is not installed. Any exception during
        setup is logged as a warning and also returns False.
        """
        # PLAYERS IN THIS SCENE
        #   service           the service name to report
        #   endpoint          the OTLP endpoint URL
        #   resource          OTel Resource: attributes describing this service
        #   tracer_provider   the SDK tracer provider, exporting spans in batches
        #   meter_provider    the SDK meter provider, exporting metrics periodically
        #   meter             the meter that creates the instruments
        #   exc               (on failure) the exception raised during setup

        # --- Gate 1: switched off by the environment ------------------------
        if os.environ.get("CCLF_OBSERVABILITY_ENABLED", "true").lower() != "true":
            logger.info("[cclf-obs] observability disabled")
            return False
        # --- Gate 2: packages not installed --------------------------------
        if not OTEL_AVAILABLE:
            logger.info("[cclf-obs] opentelemetry not installed: pip install -r "
                        "requirements-obs.txt")
            return False
        try:
            # --- Where to send data, and under what name ---------------------
            service = os.environ.get("OTEL_SERVICE_NAME", SERVICE_NAME_DEFAULT)
            endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ENDPOINT_DEFAULT)
            resource = Resource(attributes={SERVICE_NAME: service})
            # --- Tracing: provider -> batch processor -> OTLP exporter -------
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
            trace.set_tracer_provider(tracer_provider)
            # --- Metrics: provider with a periodic reader -> OTLP exporter ---
            meter_provider = MeterProvider(resource=resource, metric_readers=[
                PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint))])
            metrics.set_meter_provider(meter_provider)
            # --- The tracer and the four instruments -------------------------
            self._tracer = trace.get_tracer("cclf")
            meter = metrics.get_meter("cclf")
            self._closures = meter.create_counter("cclf.closures", description="closures by type")
            self._escalations = meter.create_counter("cclf.escalations",
                                                     description="escalations by condition")
            self._gates = meter.create_counter("cclf.gate.outcomes",
                                               description="execution gate outcomes")
            self._coherence = meter.create_histogram("cclf.coherence",
                                                     description="coherence score")
            # Only now, with everything built, is the instrumentor active.
            self.active = True
        except Exception as exc:  # never let telemetry break a run
            logger.warning(f"[cclf-obs] setup failed, continuing without: {exc}")
            self.active = False
        return self.active

    # =======================================================================
    # ACT I, SCENE 3 — A SPOTLIGHT
    # span(): open one tracing span for the body of a "with" block
    # =======================================================================

    @contextmanager
    def span(self, name: str, **attributes):
        """
        Context manager: run the body of a `with` block inside one span.

        Enter:   name          the span's name, e.g. "cclf.replay"
                 **attributes  extra tags; every value is stored as a string
        Exit:    yields the span object to the `with` block, or None when
                 inactive (then no span is created at all)

        Usage:   with obs.span("cclf.replay", scenario="mcas"):
                     ...work...

        READER'S NOTE — @contextmanager
            This is a generator function (it contains `yield`). The
            @contextmanager decorator turns it into something usable with
            `with`: code before `yield` runs on entering the block, the
            yielded value is what `as x` receives, and code after `yield`
            runs on leaving. Here the inner `with start_as_current_span`
            stays open across the yield, so the span covers exactly the
            caller's block. A context manager generator must yield exactly
            once, which is why the inactive branch yields None and then
            returns.
        """
        # PLAYERS IN THIS SCENE
        #   s      the live OpenTelemetry span
        #   k, v   each attribute name and value
        if not self.active:
            yield None
            return
        # start_as_current_span also makes this the "current" span, so spans
        # opened inside it (the node spans) become its children.
        with self._tracer.start_as_current_span(name) as s:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
            yield s

    # =======================================================================
    # ACT I, SCENE 4 — THE UNDERSTUDY'S COSTUME
    # wrap(): give each graph node call its own span
    # =======================================================================

    def wrap(self, name: str, fn: Callable) -> Callable:
        """
        Node wrapper for graph.build_graph(wrap=...): one span per node call.

        Enter:   name   the node's name ("interpret", "apply", "assess")
                 fn     the node function to wrap
        Exit:    a new function that opens span "cclf.node.<name>" (tagged
                 with the event's op) and returns exactly what fn returns

        READER'S NOTE — functools.wraps
            A wrapper function would normally have its own name ("wrapped")
            and no docstring. @functools.wraps(fn) copies fn's __name__,
            __doc__ and similar metadata onto the wrapper, so tools and
            error messages still show the original node's name.
        """
        # PLAYERS IN THIS SCENE
        #   wrapped   the replacement node function (a closure over name, fn)

        @functools.wraps(fn)
        def wrapped(state):
            # The chained .get(..., {}) calls avoid a KeyError if the state
            # has no "event" or the event has no "op".
            with self.span(f"cclf.node.{name}", op=state.get("event", {}).get("op", "")):
                return fn(state)
        return wrapped

    # =======================================================================
    # ACT I, SCENE 5 — KEEPING SCORE
    # record_audit_entry(): turn one audit entry into metric updates
    # =======================================================================

    def record_audit_entry(self, event: str, payload: dict) -> None:
        """
        Turn audit events into metrics (called by the demo after each event).

        Enter:   event     the audit entry's event name, e.g. "TRANSITION"
                 payload   the audit entry's payload dict
        Exit:    None; updates counters / histogram when active

        Mapping:
          TRANSITION with a closure_type      -> cclf.closures   +1 {type}
          ESCALATION                          -> cclf.escalations +1 {condition}
          EXECUTION_PERMITTED / _BLOCKED /
          GATE_OVERRIDE / EXECUTION_REFUSED /
          EMERGENCY_JUSTIFICATION /
          EMERGENCY_REFUSED                   -> cclf.gate.outcomes +1 {outcome}
                                                 and, if the payload has a
                                                 coherence value, cclf.coherence
        Every other event is ignored.
        """
        if not self.active:
            return
        if event == "TRANSITION" and payload.get("closure_type"):
            self._closures.add(1, {"type": str(payload["closure_type"])})
        elif event == "ESCALATION":
            self._escalations.add(1, {"condition": str(payload.get("condition"))})
        elif event in ("EXECUTION_PERMITTED", "EXECUTION_BLOCKED", "GATE_OVERRIDE",
                       "EXECUTION_REFUSED", "EMERGENCY_JUSTIFICATION", "EMERGENCY_REFUSED"):
            self._gates.add(1, {"outcome": event})
            if "coherence" in payload:
                self._coherence.record(float(payload["coherence"]))


# ===========================================================================
# SCENE 6 — THE ONE AND ONLY
# get_instrumentor(): return the shared Instrumentor, creating it once
# ===========================================================================

def get_instrumentor() -> Instrumentor:
    """
    Return the module's single Instrumentor, creating it on first call.

    Enter:   (nothing)
    Exit:    the same Instrumentor object on every call (a "singleton")

    `global _instrumentor` is needed because the function assigns to the
    module-level name; without it, Python would treat _instrumentor as a
    new local variable. The object is created inactive; the caller decides
    when to call setup().
    """
    global _instrumentor
    if _instrumentor is None:
        _instrumentor = Instrumentor()
    return _instrumentor

# EXEUNT — end of file.

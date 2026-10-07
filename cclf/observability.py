"""
THE WATCHERS IN THE WINGS
A Play in Three Acts and Eleven Scenes
======================================

PROLOGUE
--------
The CCL-F agent (graph.py, nodes.py, guards.py) does the real work: it reads
evidence, infers a commitment state, and decides whether a transition may
happen. This file does none of that. It is the backstage crew that *watches*
the performance and reports on it to a monitoring system, so that an operator
can open a dashboard (Datadog, Dynatrace, or any other tool that speaks
OpenTelemetry) and see what the agent did, how long each step took, and how
often it detected Adversarial Commitment Opacity (ACO).

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

  This file itself reads only OTEL_SERVICE_NAME, OTEL_EXPORTER_OTLP_ENDPOINT,
  OTEL_METRIC_EXPORT_INTERVAL_MS and CCLF_OBSERVABILITY_ENABLED. The other
  variables above are read (if at all) by the OpenTelemetry or vendor
  libraries themselves, not by code in this file.

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

THE PLAYBILL (what happens in this file)
    ACT I    CCLFInstrumentor           the stage manager who owns the OTel tools
      Scene 1  __init__()               start with every tool empty
      Scene 2  setup()                  connect to OpenTelemetry (or quietly don't)
      Scene 3  _init_metrics()          create the named counters and histograms
      Scene 4  span()                   open one timed span (or a no-op stand-in)
      Scene 5  record_node_duration()   note how long one node took
      Scene 6  record_transition()      count a proposed/blocked/applied move
      Scene 7  record_aco_detection()   count one ACO detection
      Scene 8  record_acs_snapshot()    record the four ACS probabilities
      Scene 9  record_evidence_ratio()  record what share of evidence was admissible
      Scene 10 forward_audit_entry()    copy one audit entry out as a log line
    ACT II   The Understudies
      Scene 1  _wrap_node()             wrap one node function in a span + metrics
      Scene 2  instrument_nodes()       swap every node in nodes.py for its wrapper
    ACT III  The Curtain Calls
      Scene 1  session_span()           one outer span around a whole run
      Scene 2  get_instrumentor()       hand out the single shared instrumentor

READER'S NOTE — OpenTelemetry in five ideas
    OpenTelemetry ("OTel") is an open standard and a set of libraries for
    sending three kinds of telemetry out of a program:
      * TRACES  A trace is the story of one piece of work from start to
                finish, e.g. "one whole demo run".
      * SPANS   A trace is made of spans. A span is one timed step with a
                name, a start time and an end time, e.g. "the acs_inference
                node ran for 812 ms". Spans nest: a span opened while another
                is open becomes its child, so a dashboard can draw a tree.
                Here the root span is "cclf.session" and each node would be a
                child span named "cclf.node.<name>".
      * ATTRIBUTES  Key/value labels stuck onto a span (or a metric reading),
                e.g. cclf.commitment_state = "OPEN". They are what you filter
                and group by on the dashboard. This file turns every value
                into a string before attaching it.
      * METRICS Numbers recorded over time: a COUNTER only goes up ("how many
                ACO detections"), a HISTOGRAM records a spread of values ("how
                long nodes take"), a GAUGE is a current reading.
      * EXPORTERS and OTLP  The program does not draw dashboards itself. An
                EXPORTER packs up finished spans/metrics/logs and ships them
                somewhere. OTLP ("OpenTelemetry Protocol") is the standard
                wire format for that shipping; here it is sent over gRPC to
                OTEL_EXPORTER_OTLP_ENDPOINT (by default a local collector or
                Datadog Agent on port 4317). Dynatrace and Datadog both accept
                OTLP, so the same code works for either.
    A few more names you will meet below: a PROVIDER (TracerProvider,
    MeterProvider, LoggerProvider) is the factory that is configured once at
    startup; a TRACER makes spans and a METER makes metric instruments; a
    PROCESSOR / READER (BatchSpanProcessor, PeriodicExportingMetricReader)
    collects data in the background and hands it to the exporter in batches,
    so the agent is not slowed down by network calls; a RESOURCE describes
    who is sending the data (here, just the service name).

READER'S NOTE — the no-op fallback (why nothing breaks without OTel)
    The OTel packages are optional (see requirements-obs.txt). If they are
    not installed, the import block below catches the ImportError and sets
    _OTEL_AVAILABLE = False. If CCLF_OBSERVABILITY_ENABLED is not "true",
    _ENABLED is False. In either case setup() returns early and leaves
    self._ready = False. Every other method begins with a check like
    `if not self._ready ...: return`, and span() yields None instead of a
    real span. So the agent runs exactly the same, it just reports nothing.
    The same thing happens if setup() itself raises any exception: it logs a
    warning and resets to the not-ready state.
    Note that _ENABLED is read once, when this module is first imported.
    Changing the environment variable after that does not change it.

READER'S NOTE — decorators, closures and functools.wraps
    _wrap_node() defines a function `wrapped` inside itself and returns it.
    The inner function still "remembers" fn, node_name and instrumentor from
    the call that created it, even after _wrap_node() has returned. That is
    a CLOSURE. A function that takes a function and returns an improved
    version of it is the idea behind a DECORATOR. @functools.wraps(fn) copies
    fn's name, docstring and module onto `wrapped`, and stores the original
    as wrapped.__wrapped__, so the wrapper still looks like the original
    node to anything that inspects it.

READER'S NOTE — @contextmanager and `yield`
    span() and session_span() are written as generator functions decorated
    with @contextmanager. That lets callers write `with obs.span(...) as s:`.
    Code before the `yield` runs when the `with` block is entered, the
    yielded value becomes `s`, and code after the `yield` (or the end of an
    inner `with`) runs when the block exits. Here, exiting the inner
    `with self._tracer.start_as_current_span(...)` is what ends the span and
    stamps its end time.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# `from __future__ import annotations` stores type hints as plain strings
#   instead of evaluating them. That is why the DRAMATIS PERSONAE below can
#   say `Optional[CCLFInstrumentor]` before that class has been defined.
# functools        provides functools.wraps for the node wrapper (Act II)
# logging          ordinary Python logging for "[cclf-obs]" status messages
# os               reads the environment variables that configure OTel
# time             time.perf_counter(), a precise stopwatch for node duration
# contextmanager   turns a generator into a `with`-statement helper
# ===========================================================================

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
# These two try/except blocks are the heart of the no-op fallback. If every
# import succeeds, the flag is set to True. If any one is missing, Python
# raises ImportError, the except branch runs, and the flag is set to False.
# The flags _OTEL_AVAILABLE and _LOG_BRIDGE_AVAILABLE are module-level
# variables, but they stay here (not in DRAMATIS PERSONAE) because their value
# *is* the result of these imports; they cannot be set before the imports run.
#
#   trace, metrics                      OTel's global "which provider is active" API
#   TracerProvider / BatchSpanProcessor builds spans; batches them for export
#   MeterProvider / PeriodicExporting.. builds metrics; exports every N ms
#   Resource, SERVICE_NAME              labels all data with our service name
#   OTLPSpanExporter / OTLPMetricExporter  ship spans/metrics over OTLP (gRPC)

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
# The OTel logs API is newer (note the leading underscore in `_logs`: the
# library still marks it as not fully stable), so it gets its own flag. If it
# is missing, traces and metrics still work; only log export is skipped.
try:
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry._logs import set_logger_provider
    _LOG_BRIDGE_AVAILABLE = True
except ImportError:
    _LOG_BRIDGE_AVAILABLE = False


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# (_OTEL_AVAILABLE and _LOG_BRIDGE_AVAILABLE are also module-level; they are
# set by the import blocks just above, for the reason given there.)
# ===========================================================================

# logger — this module's ordinary Python logger, named "cclf.observability".
#   Used for the "[cclf-obs] ..." status messages (enabled, disabled, failed).
logger = logging.getLogger(__name__)

# _ENABLED — the master on/off switch, True unless CCLF_OBSERVABILITY_ENABLED
#   is set to something other than "true" (case is ignored by .lower()).
#   Read ONCE, at import time. Setting the variable later has no effect.
_ENABLED = os.environ.get("CCLF_OBSERVABILITY_ENABLED", "true").lower() == "true"

# _SERVICE — the service name stamped on every span, metric and log.
#   This is how you find this agent's data among everything else on the
#   dashboard. Defaults to "cclf-commitment-agent".
_SERVICE  = os.environ.get("OTEL_SERVICE_NAME", "cclf-commitment-agent")

# _ENDPOINT — where the OTLP exporters send data (host and port of a
#   collector, a Datadog Agent, or a Dynatrace OTLP endpoint).
#   Defaults to http://localhost:4317, the standard OTLP/gRPC port.
_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

# _instrumentor — the one shared CCLFInstrumentor for the whole process.
#   Starts as None and is created on first use by get_instrumentor() (Act III,
#   Scene 2). Keeping a single instance means setup() configures OTel once and
#   every caller shares the same tracer and meter. (This is called a
#   "singleton".) Its type hint names a class defined later; that is fine
#   because the future import above keeps hints as unevaluated strings.
_instrumentor: Optional[CCLFInstrumentor] = None


# ===========================================================================
# ACT I — THE STAGE MANAGER
# CCLFInstrumentor: holds the tracer, the meter and every metric instrument,
# and offers small "record this" methods that silently do nothing when OTel
# is unavailable or disabled.
# ===========================================================================

class CCLFInstrumentor:
    """
    OTel instrumentation for the CCL-F commitment agent.

    Provides:
      - Tracer for span creation (node-level and sub-operation spans)
      - Meter for custom metrics (ACS distribution, ACO counts, transitions)
      - Audit log forwarding via OTel log bridge

    Attributes (all start empty; setup() fills them in):
      _tracer   the OTel Tracer that makes spans, or None
      _meter    the OTel Meter that makes metric instruments, or None
      _ready    True only after setup() succeeded; every method checks it
      _acs_gauges, _acs_confidence, _evidence_admissible_ratio
                observable gauges created in _init_metrics(). Nothing in this
                file registers a callback for them or records to them, so
                they currently report no values; record_acs_snapshot() and
                record_evidence_ratio() use histograms instead.
      _transition_counter, _aco_counter, _node_duration_histogram
                the instruments the record_* methods actually write to
    """

    # =======================================================================
    # ACT I, SCENE 1 — THE EMPTY STAGE
    # __init__(): create the object with no OTel tools attached yet.
    # =======================================================================

    def __init__(self):
        """
        Create an instrumentor that is not ready yet.

        Enter:   (nothing)
        Exit:    a new CCLFInstrumentor with _ready = False. Call setup()
                 to connect it to OpenTelemetry.
        """
        self._tracer: Optional[Any]  = None
        self._meter:  Optional[Any]  = None
        self._ready:  bool           = False

        # Metric instruments (created after setup())
        self._acs_gauges:              dict = {}
        self._evidence_admissible_ratio: Any = None
        self._transition_counter:        Any = None
        self._aco_counter:               Any = None
        self._node_duration_histogram:   Any = None

    # =======================================================================
    # ACT I, SCENE 2 — RAISING THE CURTAIN
    # setup(): wire up traces, metrics and (optionally) logs to OTLP exporters.
    # =======================================================================

    def setup(self) -> None:
        """
        Initialise OTel SDK with OTLP exporters.
        Safe to call multiple times (idempotent).
        Falls back to no-op if OTel packages not installed.

        Enter:   (nothing; configuration comes from the module-level
                 _ENABLED, _SERVICE and _ENDPOINT, plus the environment
                 variable OTEL_METRIC_EXPORT_INTERVAL_MS)
        Exit:    None. Side effects on success: installs global OTel tracer,
                 meter and (if available) logger providers, fills in
                 self._tracer / self._meter / the metric instruments, and
                 sets self._ready = True.

        "Idempotent" means calling it twice has the same effect as calling
        it once: the first check returns immediately if we are already ready.
        It returns early, leaving _ready False (the no-op mode), when
        observability is disabled, when the OTel packages are missing, or
        when anything inside the try block raises.
        """
        # PLAYERS IN THIS SCENE
        #   resource        OTel Resource saying "this data is from <_SERVICE>"
        #   trace_provider  the TracerProvider that creates and exports spans
        #   metric_reader   collects metric values and exports them on a timer
        #   meter_provider  the MeterProvider that creates metric instruments
        #   log_provider    the LoggerProvider for OTel logs (only if available)
        #   exc             the exception, if setup fails part-way

        # --- Already set up? Nothing to do -------------------------------
        if self._ready:
            return

        # --- Switched off by the environment ------------------------------
        if not _ENABLED:
            logger.info("[cclf-obs] Observability disabled (CCLF_OBSERVABILITY_ENABLED=false)")
            return

        # --- Packages not installed: tell the user how to get them --------
        if not _OTEL_AVAILABLE:
            logger.warning(
                "[cclf-obs] opentelemetry packages not installed. "
                "Run: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc"
            )
            return

        # Everything below talks to third-party code, so any failure is
        # caught and turned into a warning: observability must never crash
        # the agent it is watching.
        try:
            resource = Resource(attributes={SERVICE_NAME: _SERVICE})

            # Traces
            # --- Traces: provider → batch processor → OTLP span exporter --
            # BatchSpanProcessor queues finished spans and sends them in the
            # background. set_tracer_provider() makes this provider the
            # process-wide default; get_tracer("cclf.agent") then hands us a
            # tracer whose spans are tagged as coming from "cclf.agent".
            trace_provider = TracerProvider(resource=resource)
            trace_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=_ENDPOINT))
            )
            trace.set_tracer_provider(trace_provider)
            self._tracer = trace.get_tracer("cclf.agent")

            # Metrics
            # --- Metrics: reader exports on a timer (default every 10 s) --
            # The interval comes from OTEL_METRIC_EXPORT_INTERVAL_MS, read
            # here as a string and turned into an int.
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
            # --- Logs: only if the newer logs API imported successfully ---
            # This installs an OTel LoggerProvider with an OTLP log exporter.
            # Note: nothing in this file attaches an OTel logging handler to
            # Python's `logging` module, so ordinary logger.info(...) calls
            # (including forward_audit_entry's) are not routed into it here.
            if _LOG_BRIDGE_AVAILABLE:
                log_provider = LoggerProvider(resource=resource)
                log_provider.add_log_record_processor(
                    BatchLogRecordProcessor(OTLPLogExporter(endpoint=_ENDPOINT))
                )
                set_logger_provider(log_provider)

            # --- Create the named metric instruments, then go live --------
            self._init_metrics()
            self._ready = True
            logger.info(f"[cclf-obs] OTel instrumentation active → {_ENDPOINT}")

        except Exception as exc:
            # --- Something failed: fall back to the no-op mode ------------
            logger.warning(
                f"[cclf-obs] OTel setup failed ({exc}); running without observability."
            )
            self._tracer = None
            self._meter  = None
            self._ready  = False

    # =======================================================================
    # ACT I, SCENE 3 — SETTING OUT THE PROPS
    # _init_metrics(): create every named metric instrument from the meter.
    # =======================================================================

    def _init_metrics(self) -> None:
        """
        Create all metric instruments.

        Enter:   (nothing; uses self._meter, which setup() has just set)
        Exit:    None. Fills in self._acs_gauges, self._acs_confidence,
                 self._evidence_admissible_ratio, self._transition_counter,
                 self._aco_counter and self._node_duration_histogram.

        Each instrument has a dotted name (how it appears on dashboards), a
        description, and a unit ("1" means a plain number with no unit).
        """
        # PLAYERS IN THIS SCENE
        #   m           short name for self._meter, the factory for instruments
        #   state_name  one of "open", "trajectory", "authority", "execution"

        m = self._meter

        # ACS probability gauges (one per state)
        # --- One observable gauge per commitment state ---------------------
        # An "observable" gauge expects a callback that reports its value on
        # each export; none is registered in this file (see class docstring).
        for state_name in ("open", "trajectory", "authority", "execution"):
            self._acs_gauges[state_name] = m.create_observable_gauge(
                name=f"cclf.acs.p_{state_name}",
                description=f"ACS inferred probability of {state_name.upper()} state",
                unit="1",
            )

        # --- More gauges (also without callbacks here) ----------------------
        # _acs_confidence is first created here, not in __init__.
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

        # --- Counters: numbers that only go up -----------------------------
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

        # --- Histogram: a spread of values (node run times) ----------------
        self._node_duration_histogram = m.create_histogram(
            name="cclf.node.duration_ms",
            description="Node execution duration in milliseconds",
            unit="ms",
        )

    # =======================================================================
    # ACT I, SCENE 4 — ONE TIMED STEP
    # span(): open a span for the length of a `with` block (or pretend to).
    # =======================================================================

    @contextmanager
    def span(self, name: str, attributes: dict | None = None):
        """
        Context manager for a traced span.
        No-op if OTel not available or disabled.

        Enter:   name        the span's name, e.g. "cclf.node.acs_inference"
                 attributes  optional dict of labels to attach at the start
        Exit:    yields the live OTel span (so callers can add more
                 attributes later), or None in no-op mode. The span ends
                 when the caller's `with` block ends.

        Use it as:  with obs.span("name", {"k": v}) as s: ...
        Callers must check `if s is not None` before using s.
        """
        # PLAYERS IN THIS SCENE
        #   s     the live span created by the tracer
        #   k, v  one attribute key and value from `attributes`

        # --- No-op path: hand back None and stop ---------------------------
        # The bare `return` after `yield` ends the generator, which is how a
        # @contextmanager says "nothing to clean up".
        if not self._ready or self._tracer is None:
            yield None
            return

        # --- Real path: start a span and make it the "current" one ---------
        # "as current" means any span opened inside this block (for example
        # a node span inside the session span) becomes its child.
        with self._tracer.start_as_current_span(name) as s:
            if attributes:
                # Every value is converted with str() before being attached.
                for k, v in attributes.items():
                    s.set_attribute(k, str(v))
            yield s

    # =======================================================================
    # ACT I, SCENE 5 — THE STOPWATCH
    # record_node_duration(): add one node's run time to the histogram.
    # =======================================================================

    def record_node_duration(self, node_name: str, duration_ms: float,
                              state_name: str, aco_detected: bool) -> None:
        """
        Record how long one node took, labelled with context.

        Enter:   node_name     which node ran, e.g. "aco_detection"
                 duration_ms   how long it took, in milliseconds
                 state_name    the commitment state after the node ran
                 aco_detected  whether ACO was flagged after the node ran
        Exit:    None. Adds one value to cclf.node.duration_ms (no-op if
                 not ready).
        """
        if not self._ready or self._node_duration_histogram is None:
            return
        # The dict is the set of attributes for this one measurement.
        self._node_duration_histogram.record(duration_ms, {
            "cclf.node":             node_name,
            "cclf.commitment_state": state_name,
            "cclf.aco_detected":     str(aco_detected).lower(),
        })

    # =======================================================================
    # ACT I, SCENE 6 — THE TALLY OF MOVES
    # record_transition(): count one transition event by its outcome.
    # =======================================================================

    def record_transition(self, outcome: str, from_state: str,
                           to_state: str | None = None) -> None:
        """
        outcome: 'proposed' | 'blocked' | 'applied' | 'rejected_human'

        Add 1 to the transition counter, labelled by what happened.

        Enter:   outcome     what happened to the proposed move (see above;
                             this file itself only ever passes "applied" or
                             "blocked", from _wrap_node)
                 from_state  the state before the move
                 to_state    the state it moved (or tried to move) to; None
                             is recorded as the text "none"
        Exit:    None. Increments cclf.transitions.total (no-op if not ready).
        """
        if not self._ready or self._transition_counter is None:
            return
        # `to_state or "none"` uses "none" whenever to_state is None or "".
        self._transition_counter.add(1, {
            "cclf.transition.outcome":    outcome,
            "cclf.transition.from_state": from_state,
            "cclf.transition.to_state":   to_state or "none",
        })

    # =======================================================================
    # ACT I, SCENE 7 — THE ALARM BELL
    # record_aco_detection(): count one ACO detection and which conditions fired.
    # =======================================================================

    def record_aco_detection(self, conditions: list[str]) -> None:
        """
        Add 1 to the ACO detection counter.

        Enter:   conditions  names of the ACO conditions that were met
                             (e.g. ["C1", "C2"]); joined with commas into
                             one attribute value
        Exit:    None. Increments cclf.aco.detections (no-op if not ready).
        """
        if not self._ready or self._aco_counter is None:
            return
        self._aco_counter.add(1, {
            "cclf.aco.conditions": ",".join(conditions),
        })

    # =======================================================================
    # ACT I, SCENE 8 — THE BELIEF SNAPSHOT
    # record_acs_snapshot(): record the four ACS state probabilities.
    # =======================================================================

    def record_acs_snapshot(self, p_open: float, p_trajectory: float,
                             p_authority: float, p_execution: float,
                             confidence: float) -> None:
        """
        Forward ACS probabilities as gauge observations.
        In production: wire these to observable callbacks for pull-based metrics.
        Here we use a histogram as a push-compatible alternative.

        Enter:   p_open, p_trajectory, p_authority, p_execution
                             the inferred probability of each commitment state
                 confidence  the inference confidence (accepted, but not
                             recorded by this method)
        Exit:    None. Records four values into the cclf.acs.snapshot
                 histogram, one per state, each labelled cclf.acs.state.

        "Push" means we send the value when we have it; "pull" (observable
        gauges) means OTel asks for the value on its own schedule.
        """
        # PLAYERS IN THIS SCENE
        #   hist        the cclf.acs.snapshot histogram
        #   state_name  label for the current probability
        #   val         the probability for that state

        if not self._ready or self._meter is None:
            return
        # Note: this histogram is requested from the meter on every call,
        # rather than created once in _init_metrics().
        hist = self._meter.create_histogram(
            "cclf.acs.snapshot",
            description="ACS probability snapshot (push-mode fallback)",
            unit="1",
        )
        # --- One histogram value per state, told apart by an attribute -----
        for state_name, val in [
            ("open", p_open), ("trajectory", p_trajectory),
            ("authority", p_authority), ("execution", p_execution),
        ]:
            hist.record(val, {"cclf.acs.state": state_name})

    # =======================================================================
    # ACT I, SCENE 9 — THE EVIDENCE SCORECARD
    # record_evidence_ratio(): what fraction of evidence was admissible?
    # =======================================================================

    def record_evidence_ratio(self, admissible: int, total: int) -> None:
        """
        Record the share of evidence that passed the admissibility guards.

        Enter:   admissible  how many evidence items are admissible
                 total       how many evidence items there are in all
        Exit:    None. Records admissible/total (or 0.0 when total is 0, to
                 avoid dividing by zero) into the
                 cclf.evidence.admissible_ratio_obs histogram.
        """
        # PLAYERS IN THIS SCENE
        #   ratio  admissible / total, between 0.0 and 1.0
        #   h      the histogram the ratio is recorded into

        if not self._ready or self._meter is None:
            return
        # A "conditional expression": value_if_true if condition else value_if_false.
        ratio = admissible / total if total > 0 else 0.0
        h = self._meter.create_histogram(
            "cclf.evidence.admissible_ratio_obs",
            description="Evidence admissible ratio observation",
            unit="1",
        )
        h.record(ratio, {"cclf.evidence.total": str(total)})

    # =======================================================================
    # ACT I, SCENE 10 — THE COURT REPORTER'S COPY
    # forward_audit_entry(): write one audit entry as a JSON log line.
    # =======================================================================

    def forward_audit_entry(self, entry) -> None:
        """
        Forward an AuditEntry to OTel logs.
        The hash-chained audit log is the CCL-F source of truth;
        this is a secondary observability copy for dashboards.

        Enter:   entry  one AuditEntry from state.audit_log (see types.py)
        Exit:    None. Writes one JSON line through the Python logger named
                 "cclf.audit". Does nothing unless setup() succeeded and the
                 OTel logs API was importable.

        What happens to that line next depends on how Python logging is
        configured; this file does not attach an OTel handler to the
        "cclf.audit" logger itself.
        """
        # PLAYERS IN THIS SCENE
        #   otel_logger  the Python logger named "cclf.audit"

        if not _LOG_BRIDGE_AVAILABLE or not self._ready:
            return
        # `json` is imported here, inside the function, so it is only loaded
        # when this method actually runs. It is part of the standard library.
        import json
        otel_logger = logging.getLogger("cclf.audit")
        # --- One JSON object per entry, including both chain hashes --------
        # str(...) turns the CommitmentState enums (or None) into text.
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


# ===========================================================================
# ACT II, SCENE 1 — THE UNDERSTUDY
# _wrap_node(): build a stand-in for one node that runs the real node inside
# a span and records metrics about what it did.
# ===========================================================================

# Node wrapper decorator
def _wrap_node(fn: Callable, node_name: str, instrumentor: CCLFInstrumentor) -> Callable:
    """
    Wraps a LangGraph node function with:
      - A trace span named 'cclf.node.<node_name>'
      - Duration histogram recording
      - State-derived span attributes
      - Audit entry forwarding for the entries added during this node

    Enter:   fn            the original node function, state -> state
                           (one of the functions in nodes.py)
             node_name     its name, used in the span name and metric labels
             instrumentor  the CCLFInstrumentor to report through
    Exit:    a new function `wrapped(state)` that behaves exactly like fn
             (same argument, same return value) but also emits telemetry.

    `wrapped` is a closure (see READER'S NOTE at the top): it keeps using
    fn, node_name and instrumentor after _wrap_node() has returned. If fn
    raises, the exception passes straight through; telemetry is never
    allowed to swallow an error.
    """

    @functools.wraps(fn)
    def wrapped(state):
        """
        Run the original node inside a span and record what it did.

        Enter:   state  the CCLFAgentState LangGraph hands to the node
        Exit:    whatever fn(state) returned, unchanged
        """
        # PLAYERS IN THIS SCENE
        #   attrs             span attributes describing the state *before* the node
        #   audit_len_before  audit-log length before the node, so we can find new entries
        #   t0                stopwatch start time (seconds, from perf_counter)
        #   span              the live span, or None in no-op mode
        #   result            the state the original node returned
        #   duration_ms       how long fn(state) took, in milliseconds
        #   new_entries       audit entries the node added during this call
        #   a                 the ACS estimate (acs_inference only)
        #   admissible        count of admissible evidence (evidence_intake only)
        #   aco_entries       new ACO_DETECTED audit entries (aco_detection only)
        #   conditions        ACO conditions taken from the latest such entry
        #   applied, blocked  new TRANSITION_APPLIED / TRANSITION_BLOCKED entries
        #   entry, e          loop variables over audit entries

        # --- Before the node: describe the incoming state ------------------
        attrs = {
            "cclf.node":             node_name,
            "cclf.commitment_state": str(state.commitment_state),
            "cclf.aco_detected":     str(state.aco_detected).lower(),
            "cclf.evidence_count":   len(state.evidence_buffer),
            "cclf.audit_seq":        len(state.audit_log),
        }

        # Remember where the audit log ends now; anything after this index
        # once the node returns was written by this node.
        audit_len_before = len(state.audit_log)
        # perf_counter() is a high-resolution clock meant for measuring
        # short durations; only the difference between two readings matters.
        t0 = time.perf_counter()

        # --- The action: run the real node inside its span ------------------
        with instrumentor.span(f"cclf.node.{node_name}", attrs) as span:
            result = fn(state)
            duration_ms = (time.perf_counter() - t0) * 1000

            # Post-node attributes
            # --- After the node: describe the outgoing state ----------------
            # Only possible with a real span; in no-op mode span is None.
            # The last message is cut to 256 characters with [:256] so one
            # long LLM reply cannot bloat the trace.
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
            # --- Every node: record its duration ---------------------------
            instrumentor.record_node_duration(
                node_name, duration_ms,
                str(result.commitment_state), result.aco_detected
            )

            # Forward any new audit entries
            # --- Every node: copy out the audit entries it just wrote -------
            # Slicing from audit_len_before to the end gives only the new ones.
            new_entries = result.audit_log[audit_len_before:]
            for entry in new_entries:
                instrumentor.forward_audit_entry(entry)

            # Node-specific metric recording
            # --- acs_inference: record the four state probabilities --------
            if node_name == "acs_inference":
                a = result.acs_estimate
                instrumentor.record_acs_snapshot(
                    a.p_open, a.p_trajectory, a.p_authority, a.p_execution, a.confidence
                )

            # --- evidence_intake: record the admissible share --------------
            # `sum(1 for e in ... if ...)` counts the items that pass the test.
            if node_name == "evidence_intake":
                admissible = sum(1 for e in result.evidence_buffer if e.is_admissible())
                instrumentor.record_evidence_ratio(admissible, len(result.evidence_buffer))

            # --- aco_detection: count a detection, with its conditions -----
            if node_name == "aco_detection" and result.aco_detected:
                # Extract conditions from the most recent ACO audit entry if present
                aco_entries = [e for e in new_entries if e.event_type == "ACO_DETECTED"]
                conditions = []
                if aco_entries:
                    conditions = aco_entries[-1].payload.get("conditions_met", [])
                instrumentor.record_aco_detection(conditions)

            # --- apply_transition: count applied and blocked moves ---------
            # .get(key, "unknown") returns "unknown" if the payload lacks the key.
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

        # The span has now closed (its end time is stamped). Hand the node's
        # result back unchanged, so the graph cannot tell a wrapper was there.
        return result
    return wrapped


# ===========================================================================
# ACT II, SCENE 2 — THE CAST CHANGE
# instrument_nodes(): replace each node function in nodes.py with its wrapper.
# ===========================================================================

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

    Enter:   nodes_module  the module object holding the node functions
                           (normally `cclf.nodes`)
             instrumentor  the CCLFInstrumentor the wrappers report through
    Exit:    None. Side effect: for each name below that exists in
             nodes_module, the module attribute is replaced by
             _wrap_node(original, name, instrumentor). Missing names are
             skipped.

    "Monkey-patching" means replacing an attribute of a module or object at
    run time. It changes what `nodes_module.<name>` refers to from now on.
    It does NOT change references that other modules already copied. In
    this repo, cclf/graph.py does `from .nodes import evidence_intake, ...`
    when cclf is first imported, so build_graph() still uses those original,
    unwrapped functions; code that looks the name up on the module later
    (such as run_demo.py's `from cclf.nodes import terminate`) gets the
    wrapped one. Calling this twice would wrap the wrappers a second time.
    """
    # PLAYERS IN THIS SCENE
    #   node_names  the eight node function names to wrap
    #   name        the node name being handled in this loop pass
    #   original    the function currently stored under that name, or None

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
    # getattr(module, name, None) reads module.<name>, or gives None if it
    # does not exist; setattr(module, name, value) writes module.<name>.
    for name in node_names:
        original = getattr(nodes_module, name, None)
        if original is not None:
            setattr(nodes_module, name, _wrap_node(original, name, instrumentor))
            logger.debug(f"[cclf-obs] Instrumented node: {name}")


# ===========================================================================
# ACT III, SCENE 1 — THE WHOLE PERFORMANCE
# session_span(): one root span that covers an entire agent run.
# ===========================================================================

# Session span context manager
@contextmanager
def session_span(instrumentor: CCLFInstrumentor, scenario: str, thread_id: str):
    """
    Root span for a full CCL-F agent session.
    Wrap your main run loop with this to get end-to-end trace correlation.

    Usage:
        with session_span(instrumentor, scenario="therac25", thread_id=tid):
            for batch in evidence_batches:
                state = run_batch(graph, state, config, batch, label)

    Enter:   instrumentor  the CCLFInstrumentor to open the span with
             scenario      scenario name, e.g. "mcas" or "therac25"
             thread_id     the LangGraph thread id for this run
    Exit:    yields the "cclf.session" span (or None in no-op mode); the span
             ends when the caller's `with` block ends.

    Because span() starts the span "as current", any other span opened
    inside the `with` block becomes its child, so the dashboard shows one
    tree per run. Both values are attached as attributes so a run can be
    found by scenario or thread id.
    """
    # PLAYERS IN THIS SCENE
    #   attrs  the session's attributes (scenario and thread id)
    #   span   the live session span, or None

    attrs = {
        "cclf.scenario":  scenario,
        "cclf.thread_id": thread_id,
    }
    # A context manager built from another context manager: we simply
    # pass through the span that instrumentor.span() yields.
    with instrumentor.span("cclf.session", attrs) as span:
        yield span


# ===========================================================================
# ACT III, SCENE 2 — THE ONE AND ONLY
# get_instrumentor(): return the shared instrumentor, creating it if needed.
# ===========================================================================

# Singleton accessor
#   (_instrumentor itself is declared in DRAMATIS PERSONAE at the top.)
def get_instrumentor() -> CCLFInstrumentor:
    """
    Return the process-level CCLFInstrumentor singleton.

    Enter:   (nothing)
    Exit:    the shared CCLFInstrumentor. Created on the first call and
             stored in _instrumentor; every later call returns that same
             object. It is not set up yet: call .setup() on it.
    """
    # `global _instrumentor` tells Python that the assignment below writes
    # the module-level variable, rather than creating a new local one.
    global _instrumentor
    if _instrumentor is None:
        _instrumentor = CCLFInstrumentor()
    return _instrumentor

# EXEUNT — end of file.

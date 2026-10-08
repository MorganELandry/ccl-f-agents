"""
THE QUIET OBSERVER
A Play in Six Scenes
====================

PROLOGUE
--------
Tests for cclf/observability.py, the optional OpenTelemetry tracing and
metrics around the event pipeline.

The spec asks that the runtime make "the epistemic quality of decisions
visible, auditable, and permanent" (Layer 4, Execution Gates); the audit
trail does that.
Telemetry is an extra window onto it, so its one hard requirement here is
that it never changes or breaks a run: everything must be a no-op when
observability is disabled, when the OpenTelemetry packages are missing, or
when setup fails, and the node wrapper must hand back exactly what the
wrapped node returned.

OpenTelemetry need not be installed for these tests; where a scene needs
it to look "missing", it says so by patching OTEL_AVAILABLE.

THE PLAYBILL
    Scene 1   test_disabled_by_environment_is_noop
    Scene 2   test_missing_otel_is_noop
    Scene 3   test_inactive_methods_do_nothing
    Scene 4   test_wrap_preserves_results_and_name
    Scene 5   test_wrapped_graph_gives_same_outcome_as_unwrapped
    Scene 6   test_get_instrumentor_is_a_singleton

READER'S NOTE — monkeypatch.setenv and monkeypatch.setattr
    `monkeypatch.setenv("NAME", "value")` sets an environment variable for
    one test; `monkeypatch.setattr(module, "NAME", value)` replaces a
    module attribute for one test. Both are undone automatically when the
    test ends.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# cclf.observability   the module under test (imported as `obs` so a scene
#                      can patch its OTEL_AVAILABLE flag), plus Instrumentor
#                      and get_instrumentor.
# cclf                 Advisor, AuditTrail, replay.
# scenarios            SCENARIOS, for a real replay in Scene 5.
# ===========================================================================

import cclf.observability as obs
from cclf import Advisor, AuditTrail, replay
from cclf.observability import Instrumentor, get_instrumentor
from scenarios import SCENARIOS


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# OFFLINE_ADVISOR — a fake model that is never asked (the scenarios have no
#   "report" events), passed so no real LLM client is ever built.
OFFLINE_ADVISOR = Advisor(ask=lambda system, user: "")


# ===========================================================================
# SCENE 1 — SWITCHED OFF
# Proves: CCLF_OBSERVABILITY_ENABLED=false makes setup() a no-op.
# ===========================================================================

def test_disabled_by_environment_is_noop(monkeypatch):
    """
    With observability disabled, setup() returns False and stays inactive.

    Enter:   monkeypatch   sets CCLF_OBSERVABILITY_ENABLED=false
    Exit:    passes if setup() is False and active is False
    """
    # PLAYERS IN THIS SCENE
    #   inst   a fresh Instrumentor

    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "false")
    inst = Instrumentor()
    assert inst.setup() is False and inst.active is False


# ===========================================================================
# SCENE 2 — NOTHING TO OBSERVE WITH
# Proves: if OpenTelemetry is not installed, setup() is a no-op even when
# enabled.
# ===========================================================================

def test_missing_otel_is_noop(monkeypatch):
    """
    With OTEL_AVAILABLE False, setup() returns False.

    Enter:   monkeypatch   enables observability and marks OTel missing
    Exit:    passes if setup() is False and active is False
    """
    # PLAYERS IN THIS SCENE
    #   inst   a fresh Instrumentor

    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "true")
    monkeypatch.setattr(obs, "OTEL_AVAILABLE", False)
    inst = Instrumentor()
    assert inst.setup() is False and inst.active is False


# ===========================================================================
# SCENE 3 — SILENT WHEN INACTIVE
# Proves: span() yields None and record_audit_entry() does nothing (and
# does not raise) for every kind of event when inactive.
# ===========================================================================

def test_inactive_methods_do_nothing():
    """
    An inactive Instrumentor's span and metric methods are harmless no-ops.

    Enter:   (nothing)
    Exit:    passes if span() yields None and record_audit_entry returns None
             for closure, escalation and gate events
    """
    # PLAYERS IN THIS SCENE
    #   inst      a fresh, never-set-up Instrumentor
    #   s         what span() yields
    #   event     each event name tried
    #   payload   the payload passed with it

    inst = Instrumentor()
    with inst.span("anything", key="value") as s:
        assert s is None
    for event, payload in (("TRANSITION", {"closure_type": "authority"}),
                           ("ESCALATION", {"condition": "x"}),
                           ("GATE_OVERRIDE", {"coherence": 0.4})):
        assert inst.record_audit_entry(event, payload) is None


# ===========================================================================
# SCENE 4 — THE WRAPPER CHANGES NOTHING
# Proves: wrap() returns a callable that returns exactly what the node
# returned, and keeps the node's name (functools.wraps).
# ===========================================================================

def test_wrap_preserves_results_and_name():
    """
    A wrapped node returns the same object and keeps its __name__.

    Enter:   (nothing)
    Exit:    passes if the wrapped call returns the very same dict, sees the
             same state, and has the original name
    """
    # PLAYERS IN THIS SCENE
    #   seen      the states the node was called with
    #   result    the dict the node returns
    #   node      a fake pipeline node
    #   wrapped   node wrapped by an inactive Instrumentor
    #   state     the state passed to the wrapped node

    seen, result = [], {"outcome": "ok"}

    def node(state):
        seen.append(state)
        return result

    wrapped = Instrumentor().wrap("apply", node)
    state = {"event": {"op": "classify"}}
    assert callable(wrapped)
    assert wrapped(state) is result
    assert seen == [state]
    assert wrapped.__name__ == "node"


# ===========================================================================
# SCENE 5 — SAME PLAY, WITH OR WITHOUT AN AUDIENCE
# Proves: replaying a scenario with wrap=instrumentor.wrap gives the same
# audit events as without it.
# ===========================================================================

def test_wrapped_graph_gives_same_outcome_as_unwrapped():
    """
    The Therac-25 replay produces identical audit events either way.

    Enter:   (nothing)
    Exit:    passes if both runs have the same event list and the traced
             run's chain verifies
    """
    # PLAYERS IN THIS SCENE
    #   plain, traced   supervisors from the two replays

    plain = replay(SCENARIOS["therac25"], advisor=OFFLINE_ADVISOR)
    traced = replay(SCENARIOS["therac25"], advisor=OFFLINE_ADVISOR,
                    wrap=Instrumentor().wrap)
    assert plain.audit.events() == traced.audit.events()
    assert AuditTrail.verify(traced.audit.entries())[0]


# ===========================================================================
# SCENE 6 — ONE OBSERVER PER PROCESS
# Proves: get_instrumentor() always returns the same object.
# ===========================================================================

def test_get_instrumentor_is_a_singleton():
    """
    Two calls return the same Instrumentor.

    Enter:   (nothing)
    Exit:    passes if the two results are the same object
    """
    assert get_instrumentor() is get_instrumentor()

# EXEUNT — end of file.

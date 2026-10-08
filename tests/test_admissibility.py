"""
WHO MAY HOLD THE PEN
A Play in Ten Scenes
====================

PROLOGUE
--------
Tests for Agent Admissibility (CCL-F v0.2, Layer 0) and for the
independence limits on overrides (Layer 4, Execution Gates, Overrides), as
revised in October 2026:

  Agent Admissibility: "Stewardship (AP.1) requires obligation capacity.
    So do Rule 4 acceptance and open-loop authorization, which are
    stewardship acts. ... A stewardship function assigned to a component
    without obligation capacity is a stewardship void (AP-A) for the
    failure mode it guards, whatever the component's reliability. The
    component may still serve as a signal source". "Persons and
    organizational units have obligation capacity. A role has it when a
    successor is registered under AP.1b".
  Overrides: "Where reporting lines are registered, the overrider sits
    outside the accepting agent's: an agent who reports to the acceptor,
    directly or through others, repeats the acceptor's judgment under
    another name. ... Where no agent meets these conditions, the decision
    does not execute irreversibly. The absence is recorded as a
    stewardship void (AP-A) for the failure modes concerned, and the
    remedy is an external reviewer registered by the domain's principals."
  Architecture Precondition met: "At an irreversible decision a void cannot
    be overridden ... At the other classes a void is reported and may be
    overridden."

THE PLAYBILL
    Prelude   sv (fixture)
    Scene 1   test_unregistered_agents_are_obligation_capable
    Scene 2   test_capacity_by_kind                       (parametrized, 6 runs)
    Scene 3   test_automation_cannot_accept_a_decision
    Scene 4   test_instrument_is_still_a_signal_source_and_evidence_producer
    Scene 5   test_steward_or_successor_without_capacity_is_ap_a
    Scene 6   test_overrider_needs_obligation_capacity
    Scene 7   test_overrider_in_the_acceptors_reporting_line_is_refused
                                                          (parametrized, 2 runs)
    Scene 8   test_layer0_void_not_overridable_at_irreversible
    Scene 9   test_layer0_void_overridable_at_elevated
    Scene 10  test_registrations_are_logged
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest       fixtures, parametrize, raises.
# cclf         AgentKind, Architecture, ClosureType, ExecutionClass,
#              SignalType, Supervisor, TransitionRefused.
# stagehands   shared set-up helpers (see tests/stagehands.py).
# ===========================================================================

import pytest

from cclf import (
    AgentKind, Architecture, ClosureType, ExecutionClass, SignalType, Supervisor,
    TransitionRefused,
)
from stagehands import CUST, PROCESS, TECH, add_ees, decision, entries, to_review


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# K — short alias for AgentKind.
K = AgentKind


# ===========================================================================
# PRELUDE — the fixture
# ===========================================================================

@pytest.fixture
def sv():
    """
    A new, empty Supervisor with default settings.

    Enter:   (nothing)
    Exit:    Supervisor()
    """
    return Supervisor()


# ===========================================================================
# SCENE 1 — NOBODY SAID OTHERWISE
# Proves: an agent never registered with a kind is treated as having
# obligation capacity (backward compatible), and None never has it.
# ===========================================================================

def test_unregistered_agents_are_obligation_capable(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if an unknown name is capable and None is not
    """
    assert sv.obligation_capable("someone")
    assert not sv.obligation_capable(None)


# ===========================================================================
# SCENE 2 — WHAT KIND OF AGENT
# Proves: persons and units have obligation capacity; automation and
# instruments never do; a role has it only with a registered successor.
# ===========================================================================

@pytest.mark.parametrize("kind, successor, capable", [
    (K.PERSON, None, True),
    (K.UNIT, None, True),
    (K.ROLE, None, False),
    (K.ROLE, "next-holder", True),
    (K.AUTOMATION, "backup-bot", False),
    (K.INSTRUMENT, None, False),
], ids=["person", "unit", "role-alone", "role-with-successor", "automation", "instrument"])
def test_capacity_by_kind(sv, kind, successor, capable):
    """
    Enter:   sv                         fixture
             kind, successor, capable   one row of the table
    Exit:    passes if obligation_capable() matches `capable`
    """
    sv.register_agent("a", kind, by="registry", successor=successor)
    assert sv.obligation_capable("a") is capable


# ===========================================================================
# SCENE 3 — A MODEL CANNOT OWN A DECISION
# Proves: Rule 4 acceptance needs obligation capacity; the refusal is
# logged and nothing changes.
# ===========================================================================

def test_automation_cannot_accept_a_decision(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the acceptance is refused (ACCEPTANCE_REFUSED) and
             the decision has no acceptor; a role without successor is
             refused too
    """
    sv.register_agent("planner-v3", K.AUTOMATION, by="registry")
    sv.register_agent("duty-officer", K.ROLE, by="registry")
    decision(sv, "d", [], accept=False)
    for agent in ("planner-v3", "duty-officer"):
        with pytest.raises(TransitionRefused, match="obligation capacity"):
            sv.accept_decision("d", agent, "I accept")
    assert sv.decisions["d"].accepted_by is None
    assert len(entries(sv, "ACCEPTANCE_REFUSED")) == 2


# ===========================================================================
# SCENE 4 — THE INSTRUMENT STILL SPEAKS
# Proves: "The component may still serve as a signal source": an
# instrument registers a signal, and its measurement is an External
# Evidence Source for another agent's closure.
# ===========================================================================

def test_instrument_is_still_a_signal_source_and_evidence_producer(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the instrument registers "c" and its reading closes
             it by evidence
    """
    sv.register_agent("pressure-gauge", K.INSTRUMENT, by="registry")
    to_review(sv, "c", by="pressure-gauge")
    add_ees(sv, "reading", ["c"], produced_by="pressure-gauge")
    rec = sv.attempt_closure("c", "engineer", CUST, ["reading"], "gauge reading")
    assert rec.closure_type == ClosureType.EVIDENCE


# ===========================================================================
# SCENE 5 — "THE AI IS RESPONSIBLE" IS NOT A STEWARDSHIP ASSIGNMENT
# Proves: a steward or successor without obligation capacity is an AP-A
# void citing Agent Admissibility (the Therac-25 structure: the safety
# function moved onto software).
# ===========================================================================

def test_steward_or_successor_without_capacity_is_ap_a(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if architecture_check names the software steward and
             the automated successor, citing Agent Admissibility; a role
             steward with the failure mode's successor registered is fine
    """
    # PLAYERS IN THIS SCENE
    #   voids   the void descriptions

    sv.register_agent("interlock-software", K.AUTOMATION, by="registry")
    sv.register_agent("backup-monitor", K.AUTOMATION, by="registry")
    sv.register_agent("shift-physicist", K.ROLE, by="registry")
    sv.register_architecture(Architecture(
        stewards={"overdose": "interlock-software", "beam": "shift-physicist"},
        successors={"overdose": "physicist", "beam": "chief-physicist"}), by="aecl")
    to_review(sv, "c1", failure_mode="overdose", steward=None, successor=None)
    to_review(sv, "c2", failure_mode="mode-2", steward="physicist", successor="backup-monitor")
    to_review(sv, "c3", failure_mode="beam", steward=None, successor=None)
    decision(sv, "d", ["c1", "c2", "c3"])
    voids = sv.architecture_check("d")
    assert any("'interlock-software'" in v and "Agent Admissibility" in v
               and v.startswith("AP-A") for v in voids)
    assert any("'backup-monitor'" in v and "Agent Admissibility" in v for v in voids)
    assert not any("shift-physicist" in v for v in voids)


# ===========================================================================
# SCENE 6 — OPEN-LOOP AUTHORIZATION IS A STEWARDSHIP ACT
# Proves: an override (irreversible or not) needs obligation capacity, and
# the refusal names the external-reviewer remedy.
# ===========================================================================

def test_overrider_needs_obligation_capacity(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the automation agent's override is refused with the
             AP-A remedy text and nothing executes
    """
    # PLAYERS IN THIS SCENE
    #   result   the GateResult

    sv.register_agent("ops-bot", K.AUTOMATION, by="registry")
    to_review(sv, "c")
    decision(sv, "d", ["c"])
    result = sv.request_execution("d", "ops-bot", override_rationale="go")
    assert not result.permitted and not sv.decisions["d"].executed
    assert any("obligation capacity" in f for f in result.failures)
    assert any("external reviewer" in f for f in result.failures)


# ===========================================================================
# SCENE 7 — THE ACCEPTOR'S OWN PEOPLE
# Proves: an agent who reports to the acceptor, directly or through
# others, cannot override, at an irreversible or an elevated decision.
# ===========================================================================

@pytest.mark.parametrize("execution_class", [ExecutionClass.IRREVERSIBLE,
                                             ExecutionClass.ELEVATED],
                         ids=lambda c: c.name)
def test_overrider_in_the_acceptors_reporting_line_is_refused(sv, execution_class):
    """
    Setting the stage: "ops" reports to "vp", who reports to "director"
    (the acceptor). The verdict: ops's override is refused (the decision
    does not execute); "auditor", outside the line, may override.

    Enter:   sv                fixture
             execution_class   the declared class
    Exit:    passes as described
    """
    # PLAYERS IN THIS SCENE
    #   refused, done   the two GateResults

    to_review(sv, "c")
    # An unclassified uncertainty: the elevated gate fails too.
    sv.register_signal("u", SignalType.UNCERTAINTY, "u", "engineer", TECH, PROCESS)
    decision(sv, "d", ["c", "u"], execution_class=execution_class)
    sv.register_reporting_line("vp", "director", by="hr")
    sv.register_reporting_line("ops", "vp", by="hr")
    refused = sv.request_execution("d", "ops", override_rationale="go")
    assert not refused.permitted
    assert any("reports to director" in f for f in refused.failures)
    assert any("does not execute irreversibly" in f for f in refused.failures)
    done = sv.request_execution("d", "auditor", override_rationale="go")
    assert done.permitted and done.overridden


# ===========================================================================
# SCENE 8 — NO OVERRIDE SUPPLIES AN ARCHITECTURE
# Proves: at an irreversible decision a Layer 0 void cannot be overridden,
# by anyone.
# ===========================================================================

def test_layer0_void_not_overridable_at_irreversible(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if an independent override of a decision with an AP-A
             void is refused, and permitted once the steward is registered
    """
    # PLAYERS IN THIS SCENE
    #   result   each GateResult

    to_review(sv, "c", steward=None, failure_mode="seal")
    decision(sv, "d", ["c"])
    result = sv.request_execution("d", "auditor", override_rationale="go")
    assert not result.permitted and result.architecture_void
    assert any("Layer 0 void cannot be overridden" in f for f in result.failures)
    sv.register_architecture(Architecture(stewards={"seal": "seal-owner"}), by="principals")
    assert sv.request_execution("d", "auditor", override_rationale="go").permitted


# ===========================================================================
# SCENE 9 — BELOW IRREVERSIBLE, THE VOID IS REPORTED
# Proves: "At the other classes a void is reported and may be overridden."
# ===========================================================================

def test_layer0_void_overridable_at_elevated(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if the elevated decision with an AP-A void is blocked,
             then permitted by override with architecture_void reported
    """
    # PLAYERS IN THIS SCENE
    #   result   the overridden GateResult

    to_review(sv, "c", steward=None)
    decision(sv, "d", ["c"], execution_class=ExecutionClass.ELEVATED)
    assert not sv.request_execution("d", "director").permitted
    result = sv.request_execution("d", "auditor", override_rationale="reversible; go")
    assert result.permitted and result.overridden and result.architecture_void


# ===========================================================================
# SCENE 10 — ON THE RECORD
# Proves: agent kinds and reporting lines are logged; a line to oneself is
# refused.
# ===========================================================================

def test_registrations_are_logged(sv):
    """
    Enter:   sv   fixture
    Exit:    passes if AGENT_REGISTERED and REPORTING_LINE_REGISTERED carry
             the facts, and a self-report is refused
    """
    # PLAYERS IN THIS SCENE
    #   agent, line   the two log entries

    sv.register_agent("duty-officer", K.ROLE, by="registry", successor="relief-officer")
    sv.register_reporting_line("duty-officer", "ops-chief", by="hr")
    [agent] = entries(sv, "AGENT_REGISTERED")
    assert agent.payload["agent_kind"] == "role" and agent.payload["obligation_capacity"]
    [line] = entries(sv, "REPORTING_LINE_REGISTERED")
    assert line.payload == {"agent": "duty-officer", "reports_to": "ops-chief"}
    with pytest.raises(TransitionRefused):
        sv.register_reporting_line("ops-chief", "ops-chief", by="hr")


# EXEUNT — end of file.

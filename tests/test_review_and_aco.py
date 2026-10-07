"""
THE CHECKS AND BALANCES
A Play in Three Acts
=======================

PROLOGUE
--------
Tests for three safeguards. No LLM credentials required.

  ACT I    Approval must be explicit. apply_transition moves the
           commitment state only on a recorded "yes". "No" refuses, and
           "nothing recorded" also refuses, with an audit entry saying so.
  ACT II   A recorded decision is used, not re-asked. When an outside system
           records a decision while the graph is paused, human_review uses
           it as given (even in unattended mode), and a used decision is
           cleared so it can never leak into the next review.
  ACT III  C1 is computed, not taken on trust. aco_detection works out ACO
           condition C1 in plain Python. The model cannot switch off a C1
           the numbers show, cannot invent one they do not, and every
           disagreement is written to the audit trail.
  ACT IV   The hard cases: condition labels in odd formats, ties in the
           estimate, a failed model call, and a decision recorded during a
           pause that the caller abandons by sending a new batch instead.

Each test calls a node function directly on a hand-built state, so the
behaviour under test is isolated from the rest of the graph.

Run: pytest tests/ -v

READER'S NOTE — calling nodes directly
    A node is an ordinary function: state in, state out. Tests can build a
    CCLFAgentState by hand, call one node, and inspect what it changed,
    without building or running a graph at all.

READER'S NOTE — capsys
    `capsys` is a built-in pytest fixture that captures everything printed
    to stdout/stderr during a test. human_review prints a review panel; the
    tests use capsys only to keep that panel out of the test output.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# contextlib, io   swallow the review panel printed during the graph test.
# pytest   for parametrize.
# cclf     the agent state, states, ACS estimate, Evidence and build_graph.
# nodes    the node functions under test, and _llm_json (replaced by fakes).
# scenarios / test_end_to_end   real evidence and the shared fake LLM, for
#          the graph-level test in Act IV.
# ===========================================================================

import contextlib
import io

import pytest

from cclf import CCLFAgentState, CommitmentState, ACSEstimate, Evidence, build_graph
from cclf import nodes
from scenarios import MCAS_SCENARIO
from test_end_to_end import scripted_llm


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# OPEN, TRAJ — short names for the two states these tests move between.
OPEN = CommitmentState.OPEN
TRAJ = CommitmentState.TRAJECTORY


# ===========================================================================
# PRELUDE — HELPERS
# ===========================================================================

def proposal_state(approval=None) -> CCLFAgentState:
    """
    A state at OPEN with a proposed move to TRAJECTORY.

    Enter:   approval   what to put in human_approval (None, True or False)
    Exit:    the prepared state
    """
    state = CCLFAgentState()
    state.proposed_transition = TRAJ
    state.human_approval = approval
    state.human_rationale = "test rationale" if approval is not None else ""
    return state


def events(state: CCLFAgentState) -> list[str]:
    """Return the audit log's event types, in order."""
    return [a.event_type for a in state.audit_log]


def acs_state(most_likely: CommitmentState, confidence: float,
              formal: CommitmentState = OPEN) -> CCLFAgentState:
    """
    A state whose ACS estimate puts 0.8 on `most_likely`, at `confidence`.

    Enter:   most_likely   the state the estimate should favour
             confidence    the estimate's confidence (0.0-1.0)
             formal        the formal commitment state (default OPEN)
    Exit:    the prepared state
    """
    probs = {s: 0.2 / 3 for s in CommitmentState}
    probs[most_likely] = 0.8
    state = CCLFAgentState()
    state.commitment_state = formal
    state.acs_estimate = ACSEstimate(
        p_open=probs[CommitmentState.OPEN],
        p_trajectory=probs[CommitmentState.TRAJECTORY],
        p_authority=probs[CommitmentState.AUTHORITY],
        p_execution=probs[CommitmentState.EXECUTION],
        confidence=confidence,
    )
    return state


def model_says(detected: bool, conditions: list):
    """Return a fake _llm_json that gives a fixed ACO verdict."""
    def fake(system, user):
        return {"aco_detected": detected, "conditions_met": conditions,
                "reasoning": "scripted"}
    return fake


# ===========================================================================
# ACT I — APPROVAL MUST BE EXPLICIT
# ===========================================================================

def test_no_decision_recorded_is_refused_and_audited():
    # --- Setting the stage: a proposal with nobody's decision on it -------
    state = proposal_state(approval=None)
    # --- The action --------------------------------------------------------
    state = nodes.apply_transition(state)
    # --- The verdict: nothing moved, and the refusal is on the record ------
    assert state.commitment_state == OPEN
    assert state.proposed_transition is None
    assert events(state) == ["TRANSITION_NOT_APPROVED"]


def test_explicit_no_is_refused():
    state = nodes.apply_transition(proposal_state(approval=False))
    assert state.commitment_state == OPEN
    assert "TRANSITION_APPLIED" not in events(state)


def test_explicit_yes_is_applied():
    state = nodes.apply_transition(proposal_state(approval=True))
    assert state.commitment_state == TRAJ
    assert events(state) == ["TRANSITION_APPLIED"]


@pytest.mark.parametrize("approval", [None, True, False])
def test_decision_is_cleared_after_use(approval):
    # Whatever happened, the next review must start with no decision on it.
    state = nodes.apply_transition(proposal_state(approval=approval))
    assert state.human_approval is None
    assert state.human_rationale == ""
    assert state.human_reviewer == ""


def test_decision_cleared_even_when_nothing_was_proposed():
    # An ACO-only review records a decision with no proposal; it must not
    # survive into the next cycle either.
    state = CCLFAgentState()
    state.human_approval = False
    state = nodes.apply_transition(state)
    assert state.human_approval is None


# ===========================================================================
# ACT II — A RECORDED DECISION IS USED, NOT RE-ASKED
# ===========================================================================

@pytest.mark.parametrize("recorded", [True, False])
def test_recorded_decision_wins_over_unattended_mode(recorded, monkeypatch, capsys):
    # --- Setting the stage: unattended mode would approve on its own -------
    monkeypatch.setenv("CCLF_AUTO_APPROVE", "true")
    state = proposal_state(approval=recorded)
    state.human_reviewer = "reviewer-42"
    # --- The action --------------------------------------------------------
    state = nodes.human_review(state)
    # --- The verdict: the recorded decision stands, as given ---------------
    assert state.human_approval is recorded
    review = state.audit_log[-1].payload
    assert review["decided_by"] == "external"
    assert review["reviewer"] == "reviewer-42"
    assert review["rationale"] == "test rationale"


def test_recorded_decision_never_prompts(monkeypatch, capsys):
    # If human_review tried to read the keyboard, this would fail the test.
    def no_input(prompt=""):
        raise AssertionError("human_review asked again for a recorded decision")
    monkeypatch.setattr("builtins.input", no_input)
    monkeypatch.delenv("CCLF_AUTO_APPROVE", raising=False)
    state = nodes.human_review(proposal_state(approval=True))
    assert state.human_approval is True


def test_unidentified_external_decision_is_labelled(monkeypatch, capsys):
    monkeypatch.delenv("CCLF_AUTO_APPROVE", raising=False)
    state = nodes.human_review(proposal_state(approval=True))
    assert state.audit_log[-1].payload["reviewer"] == "external (unidentified)"


def test_unattended_mode_is_labelled_auto(monkeypatch, capsys):
    monkeypatch.setenv("CCLF_AUTO_APPROVE", "true")
    state = nodes.human_review(proposal_state(approval=None))
    payload = state.audit_log[-1].payload
    assert payload["decided_by"] == "auto"
    assert "AUTO-APPROVED" in payload["rationale"]


def test_interactive_decision_records_the_reviewer(monkeypatch, capsys):
    monkeypatch.delenv("CCLF_AUTO_APPROVE", raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    monkeypatch.setattr(nodes.getpass, "getuser", lambda: "morgan")
    state = nodes.human_review(proposal_state(approval=None))
    payload = state.audit_log[-1].payload
    assert payload["decided_by"] == "interactive"
    assert payload["reviewer"] == "morgan"
    assert state.human_approval is True


# ===========================================================================
# ACT III — C1 IS COMPUTED, NOT TAKEN ON TRUST
# ===========================================================================

def test_computed_c1_cannot_be_switched_off_by_the_model(monkeypatch):
    # --- Setting the stage: estimate says TRAJECTORY at 0.9; formal is OPEN
    monkeypatch.setattr(nodes, "_llm_json", model_says(False, []))
    state = acs_state(TRAJ, confidence=0.9)
    # --- The action --------------------------------------------------------
    state = nodes.aco_detection(state)
    # --- The verdict: ACO stands on C1, and the disagreement is recorded --
    assert state.aco_detected is True
    assert "ACO_C1_DISAGREEMENT" in events(state)
    detected = [a for a in state.audit_log if a.event_type == "ACO_DETECTED"][0]
    assert detected.payload["conditions_met"] == ["C1"]
    assert detected.payload["c1_computed"] is True


def test_model_cannot_invent_c1(monkeypatch):
    # Estimate agrees with the formal state, so C1 is false; the model's
    # only reason is C1, so its "detected" is overruled.
    monkeypatch.setattr(nodes, "_llm_json", model_says(True, ["C1"]))
    state = nodes.aco_detection(acs_state(OPEN, confidence=0.9))
    assert state.aco_detected is False
    assert "ACO_C1_DISAGREEMENT" in events(state)


def test_model_keeps_authority_over_c2_and_c3(monkeypatch):
    # C1 false, but the model finds C2: that judgement stands.
    monkeypatch.setattr(nodes, "_llm_json", model_says(True, ["C1", "C2"]))
    state = nodes.aco_detection(acs_state(OPEN, confidence=0.9))
    assert state.aco_detected is True
    detected = [a for a in state.audit_log if a.event_type == "ACO_DETECTED"][0]
    assert detected.payload["conditions_met"] == ["C2"]


def test_agreement_writes_no_disagreement_entry(monkeypatch):
    monkeypatch.setattr(nodes, "_llm_json", model_says(True, ["C1"]))
    state = nodes.aco_detection(acs_state(TRAJ, confidence=0.9))
    assert state.aco_detected is True
    assert "ACO_C1_DISAGREEMENT" not in events(state)


@pytest.mark.parametrize("confidence,expected", [(0.7, False), (0.71, True)])
def test_c1_threshold_is_strictly_above(confidence, expected, monkeypatch):
    # Exactly at the threshold is not enough; just above is.
    monkeypatch.setattr(nodes, "_llm_json", model_says(False, []))
    state = nodes.aco_detection(acs_state(TRAJ, confidence=confidence))
    assert state.aco_detected is expected


def test_llm_failure_means_no_c1(monkeypatch):
    # A failed LLM call leaves the default estimate (OPEN, confidence 0),
    # which can never satisfy C1.
    monkeypatch.setattr(nodes, "_llm_json", lambda system, user: {"error": "down"})
    state = nodes.aco_detection(CCLFAgentState())
    assert state.aco_detected is False
    assert events(state) == []


def test_malformed_model_reply_is_handled(monkeypatch):
    monkeypatch.setattr(nodes, "_llm_json",
                        lambda system, user: {"aco_detected": "yes", "conditions_met": "C2"})
    state = nodes.aco_detection(acs_state(OPEN, confidence=0.9))
    # "yes" is not True and "C2" is not a list: treated as not detected.
    assert state.aco_detected is False


# ===========================================================================
# ACT IV — THE HARD CASES
# ===========================================================================

@pytest.mark.parametrize("labels,detected,expect_conditions", [
    (["Condition C1"], False, None),      # recognised as C1 -> overruled
    (["(C1)"],         False, None),      # recognised as C1 -> overruled
    (["C1, C2"],       True,  ["C2"]),    # both found; C2 stands
    (["C10"],          True,  []),        # not C1..C3: no labels named
    ([None, 1, {"id": "C1"}], True, []),  # non-text items ignored
])
def test_condition_labels_are_read_carefully(labels, detected, expect_conditions,
                                             monkeypatch):
    # Formal state and estimate agree, so the code's C1 is False throughout.
    monkeypatch.setattr(nodes, "_llm_json", model_says(True, labels))
    state = nodes.aco_detection(acs_state(OPEN, confidence=0.9))
    assert state.aco_detected is detected
    if detected:
        found = [a for a in state.audit_log if a.event_type == "ACO_DETECTED"][0]
        assert found.payload["conditions_met"] == expect_conditions


def test_tie_with_formal_state_is_not_c1(monkeypatch):
    # OPEN and TRAJECTORY tied at 0.45; formal state TRAJECTORY. most_likely()
    # returns OPEN (first in order), but OPEN is not MORE likely: no C1.
    monkeypatch.setattr(nodes, "_llm_json", model_says(False, []))
    state = CCLFAgentState()
    state.commitment_state = TRAJ
    state.acs_estimate = ACSEstimate(p_open=0.45, p_trajectory=0.45,
                                     p_authority=0.05, p_execution=0.05,
                                     confidence=0.9)
    state = nodes.aco_detection(state)
    assert state.aco_detected is False


def test_failed_model_call_is_not_a_disagreement(monkeypatch):
    # C1 holds on the numbers; the model call failed. ACO is detected on C1,
    # and no disagreement is invented for a model that never answered.
    monkeypatch.setattr(nodes, "_llm_json", lambda system, user: {"error": "down"})
    state = nodes.aco_detection(acs_state(TRAJ, confidence=0.9))
    assert state.aco_detected is True
    assert "ACO_C1_DISAGREEMENT" not in events(state)


def test_reasoning_never_contradicts_the_verdict(monkeypatch):
    monkeypatch.setattr(nodes, "_llm_json",
                        lambda system, user: {"aco_detected": False,
                                              "conditions_met": [],
                                              "reasoning": "No ACO here."})
    state = nodes.aco_detection(acs_state(TRAJ, confidence=0.9))
    assert state.aco_reasoning.startswith("C1 (computed)")
    assert "Model's view: No ACO here." in state.aco_reasoning


def test_abandoned_pause_decision_cannot_approve_a_new_proposal(monkeypatch):
    """
    The reviewer's scenario, run through the real graph.

    1. Cycle 1 pauses before human_review (ACO, nothing proposed).
    2. An outside system records "approve" (meaning: continue monitoring).
    3. Instead of resuming, the caller sends a new batch; the model now
       proposes OPEN -> TRAJECTORY.
    The old "approve" must not approve the new proposal.
    """
    # --- Setting the stage -------------------------------------------------
    monkeypatch.setenv("CCLF_AUTO_APPROVE", "true")
    monkeypatch.setenv("CCLF_OBSERVABILITY_ENABLED", "false")
    monkeypatch.setattr(nodes, "_llm_json", scripted_llm("hold"))
    graph = build_graph(interrupt_before_human=True, use_checkpointer=True)
    config = {"configurable": {"thread_id": "abandoned"}}
    first = CCLFAgentState()
    first.evidence_buffer.append(Evidence(**MCAS_SCENARIO[0]))

    with contextlib.redirect_stdout(io.StringIO()):
        # --- Cycle 1: run to the pause, then record a decision -------------
        graph.invoke(first, config)
        assert graph.get_state(config).next == ("human_review",)
        graph.update_state(config, {"human_approval": True,
                                    "human_rationale": "continue monitoring",
                                    "human_reviewer": "reviewer-1"})

        # --- Cycle 2: a new batch instead of a resume; model now advances --
        monkeypatch.setattr(nodes, "_llm_json", scripted_llm("advance"))
        saved = CCLFAgentState.from_stream(graph.get_state(config).values)
        graph.invoke({"evidence_buffer": saved.evidence_buffer
                      + [Evidence(**MCAS_SCENARIO[1])]}, config)
        paused = CCLFAgentState.from_stream(graph.get_state(config).values)

    # --- The verdict -------------------------------------------------------
    # The old decision was discarded (and audited) at the start of cycle 2,
    # so the new proposal is waiting for its own decision, not approved.
    assert "REVIEW_DECISION_DISCARDED" in events(paused)
    assert graph.get_state(config).next == ("human_review",)
    assert paused.human_approval is None
    assert paused.commitment_state == OPEN

# EXEUNT — end of file.

# CCL-F Commitment Agent: Architecture Specification

**Project:** `cclf-agents`  
**Framework:** CCL-F (Coordination Control Loop Framework) v0.2  
**Stack:** Python · LangGraph · LangChain · OpenAI API  
**Status:** Reference implementation

---

## Purpose

This project implements the CCL-F commitment state machine as a LangGraph agentic workflow. It demonstrates how agentic AI infrastructure can enforce organizational safety properties — specifically, how to prevent catastrophic decisions that result from **commitment opacity**: the failure of known safety signals to convert into executable corrective action before irreversible consequences occur.

Two worked scenarios are included (737 MAX MCAS and Therac-25). The same graph applies to any organizational domain.

---

## Background: The CCL-F Framework

CCL-F (Coordination Control Loop Framework) formalizes why organizations make catastrophic decisions despite possessing the information needed to avoid them. The core claim: commitment failure has **formal structure** that can be detected and interrupted before the point of irreversibility.

The framework introduces four monotonically non-decreasing commitment states:

```
OPEN → TRAJECTORY → AUTHORITY → EXECUTION
```

| State       | Meaning                                                        |
|-------------|----------------------------------------------------------------|
| OPEN        | Signals visible; no direction committed                        |
| TRAJECTORY  | A direction is locked; alternatives deprioritized              |
| AUTHORITY   | Decision authority has formally closed                         |
| EXECUTION   | Resources deployed; reversal is operationally costly           |

**Structurally blocked transitions** (enforced in code, not policy):

| Blocked                     | Reason                                          |
|-----------------------------|-------------------------------------------------|
| EXECUTION → TRAJECTORY      | Cannot unspend deployed resources               |
| AUTHORITY → OPEN            | Authority closure is durable                    |
| TRAJECTORY → OPEN           | Trajectory lock does not self-reverse           |
| Any → skip a state          | Non-monotonic jumps disallowed                  |

**ACO (Adversarial Commitment Opacity):** A failure mode in which the true commitment state is deliberately or structurally concealed from agents who need it to act safely. Boeing MCAS certification, VW Dieselgate, and Enron are historical ACO anchors.

---

## System Architecture

```
START
  │
  ▼
┌─────────────────┐
│ evidence_intake │  Score incoming evidence for novelty + independence
└────────┬────────┘
         │
         ▼
┌──────────────────┐
│  acs_inference   │  LLM estimates hidden ACS probability distribution
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  aco_detection   │  LLM checks for Adversarial Commitment Opacity
└────────┬─────────┘
         │
         ▼
┌──────────────────────┐
│ transition_evaluation│  LLM proposes: advance / hold / escalate
└────────┬─────────────┘
         │
         ▼
┌──────────────────┐
│ transition_guard │  Structural block (pure logic, NO LLM)
└────────┬─────────┘
         │
    ┌────┴────────────────────────┐
    │ ACO detected OR             │
    │ transition proposed?        │
    ├─ YES ──────────────────────►│
    │                    ┌────────▼──────┐
    │                    │ human_review  │  ← LangGraph interrupt point
    │                    └────────┬──────┘
    │                             │
    └─ NO ─────────────────────── ┤
                                  ▼
                         ┌─────────────────┐
                         │ apply_transition │
                         └────────┬────────┘
                              ┌───┴───────────────────┐
                              │ should_terminate?      │
                              ├─ YES ─────────────────►│
                              │               ┌────────▼──┐
                              │               │ terminate  │
                              │               └────────────┘
                              │                     │
                              └─ NO ──► END of cycle
                                        (caller streams the next
                                         evidence batch; state persists
                                         via the checkpointer)
```

---

## Node Inventory

### 1. `evidence_intake`
Scores each un-evaluated piece of evidence on:
- **Novelty** (0–1): does this add new information beyond what's already seen?
- **Independence** (0–1): does this come from a source independent of prior evidence?

Evidence must clear **both** thresholds (≥ 0.5) to be admissible. This guard prevents the classic pattern where 20 "signals" are actually the same signal re-reported, inflating apparent consensus.

### 2. `acs_inference`
Maintains a **probability distribution** over the four commitment states, inferred from admissible behavioral signals. The agent cannot observe ACS (Authority Commitment Signal) directly — it may be concealed. This node implements the hidden-state inference problem.

### 3. `aco_detection`
Checks three ACO conditions:
- **C1:** Formal state diverges from inferred ACS estimate (high confidence)
- **C2:** High-quality evidence is being systematically ignored
- **C3:** Decision authority inaccessible while trajectory is locked

Any condition triggers escalation to human review.

### 4. `transition_evaluation`
The LLM proposes `advance`, `hold`, or `escalate` based on:
- Current commitment state
- ACS estimate
- Admissible evidence
- ACO flag

This node **proposes only** — it does not apply.

### 5. `transition_guard` ⚠️
**LLM-free by design.** Enforces the four structurally blocked transitions using pure logic. This is the safety-critical node: a probabilistic model must not be able to override a structural invariant.

### 6. `human_review` (interrupt node)
Human-in-the-loop checkpoint. Surfaces all relevant context to a human approver. In production, this is a LangGraph interrupt — the graph pauses, writes a checkpoint, and waits for an external resume signal (webhook, UI, approval queue). In CLI demo mode, uses stdin.

### 7. `apply_transition`
Commits the transition only if: (a) guard passed, (b) human approved. Writes an immutable audit entry. Flags EXECUTION-state arrival for termination.

### 8. `terminate`
Writes final audit summary and signals graph completion.

---

## Audit System

Every event produces an `AuditEntry` with:
- **Hash-chained integrity**: each entry hashes its content + the previous entry's hash → tamper-evident chain
- **Immutable sequence**: entries are append-only
- **Full provenance**: from/to states, event type, payload, timestamp, agent reasoning

This directly addresses the 737 MAX failure mode where audit trails were incomplete or post-hoc reconstructed.

---

## Human-in-the-Loop Pattern

The CLI runs `human_review` inline: it prompts on stdin, or with `--no-hitl` records an explicit `AUTO-APPROVED` decision so the audit chain never shows an automatic decision as a human one.

A service deployment would instead pause before the node and resume once an external approver (webhook, UI, approval queue) has decided, using LangGraph's standard interrupt API:

```python
graph = build_graph(interrupt_before_human=True, use_checkpointer=True)
config = {"configurable": {"thread_id": "t1"}}

graph.invoke(initial_state, config)            # runs until it pauses before human_review

# External approval system records the decision on the checkpointed state...
graph.update_state(config, {"human_approval": True,
                            "human_rationale": "Approved by Safety Review Board",
                            "human_reviewer": "safety-board-chair"})
graph.invoke(None, config)                     # ...and resumes from the pause
```

On resume, `human_review` finds the decision already written to state and uses it as recorded: it does not ask again, and unattended mode cannot override it. The audit entry records the reviewer and `decided_by: external`. A decision is cleared once used, and any unused decision is discarded at the start of the next cycle, so a decision can only ever answer the proposal it was given for.

---

## Repo structure, running the demo

See the [README](../README.md).

---

## Reference

CCL-F framework v0.2, Zenodo, CC BY-NC-ND 4.0

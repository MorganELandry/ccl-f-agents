# Formal verification

These are machine-checked models of the parts of the CCL-F v0.2 runtime where a wrong rule would be most costly:
- a **TLA+** model of the Layer 4 commitment state machine, checked exhaustively by TLC;
- an **Alloy** model of closure typing and the Layer 0 voids, checked by the Alloy Analyzer.

A Python test (`tests/test_verification.py`) ties both models to the code, so they cannot drift apart unnoticed.

```bash
bash verification/run.sh      # downloads pinned, checksummed jars; about 17 minutes
```

It needs Java 17 or later. Without Java, the model-to-code tests still run in the normal `pytest`; only the checker runs are skipped.

## Scope

These models check the **0.2 automaton as written**: its transition table, exits, recovery conditions, audit log and gate. They are a first piece of the v0.2 draft's 0.3 discrete track ("formal transition semantics, invariants, TLA+/Alloy verification"), not the whole of it. They do not cover:

- transition-function semantics;
- coherence scoring;
- thresholds;
- the continuous dynamics.

A passing check means no counterexample exists **within the bounds** below. It is not a proof for systems of every size.

## TLA+: `tla/CommitmentStateMachine.tla`

**Model.** Two signals, one irreversible decision, an audit log of at most 8 records. The model has:

- all 14 table transitions;
- all 14 exit types, with the four legal sub-types;
- re-entry conditions: successor, a different agent, a hold lifted, a resolution condition registered at exit and met;
- the Rule 8 model update;
- Rule 4 acceptance;
- the irreversible gate (a constraint counts as resolved only if evidence-closed or exited terminal/superseded) and its logged override.

The model does not cover Closure Chain or the decision-level External Evidence Source requirement; those are tested in Python (`tests/test_gate_design.py`).

**Result.** TLC explores every reachable state: 31,485,931 distinct states, depth 9. It finds no violation.

| Property | What it says | Source in the draft |
|---|---|---|
| `NoCloseBeforeClassified` | A signal cannot be closed before it is classified | Layer 4, blocked transition 1 |
| `NoCloseBeforeReview` | A classified signal cannot be closed before review opens | blocked transition 2 |
| `NoSilentCloseFromSuppressed` | A suppressed signal cannot be silently closed | blocked transition 3 |
| `NoSilentReopen` | Every reopen is its own logged record | blocked transition 4 |
| `EscalatedNeedsModelUpdate` | escalated → under_review only after a documented model update | Recovery transitions; Rule 8 |
| `EscalatedNeverClosesDirectly` | An escalated signal is never closed directly | Layer 4 table: escalated has only the recovery transition |
| `TrajectoryLockTerminal` | trajectory_lock is terminal | Layer 4 |
| `NoForbiddenReentry` | terminal, superseded, timeout and whistleblower exits never re-enter | Exit transitions |
| `NoWaitingReentryWithoutCondition` | containment, deferred and ambiguity exits with no resolution condition registered at exit never re-enter | Exit transitions; Layer 2 exit obligations |
| `NoLegalReentryWithoutResumableSubtype` | judicial orders and statutory triggers never resume to review | Exit transitions (legal) |
| `AuditAppendOnly` | the log only grows; earlier records never change | Audit Trail |
| `EveryChangeLogged` | every state change is logged in the same step | Audit Trail |
| `Rule4` | execution implies acceptance | Rule 4 |
| `OpenLoopExecutionLogged` | executing with open loops leaves an override on record | Execution Gates |
| `OverrideLatchesReviews` | after an override, no loop is left under review; each is latched in trajectory_lock | Layer 4, lock-in closure |
| `NoCleanPassOverAuthorityClosure` | the gate never passes cleanly over a constraint closed by authority or role switch | Reversibility Logic; Execution Gates |

**Not vacuous.** `tests/test_verification.py` plants two faults in copies of the model and confirms TLC catches each:
- `classified → closed_authority` added to the table: `NoCloseBeforeReview` is violated;
- the pre-October-2026 gate restored, which let an authority-closed constraint pass: `NoCleanPassOverAuthorityClosure` is violated.

## Alloy: `alloy/closure_and_architecture.als`

**Scope.** Every instance with up to 5 of each kind of object (4 time points).

| Assertion | What it says |
|---|---|
| `RestatementIsNotEvidence` | citing only what existed at registration never yields an evidence closure |
| `NonEESKindsNeverClose` | model output, assertions and internal analysis never close by evidence |
| `NoSelfCertification` | the process under evaluation, or the registrant, cannot close by its own evidence |
| `EvidenceClosureHasIndependentSource` | every evidence closure rests on an independent producer |
| `RoleSwitchIsSelfClosure` | role-switch closure is always the registrant closing their own signal |
| `NoSinglePointOfStewardship` | with no AP-A or AP.1b void, losing any one agent still leaves someone named |
| `UncapturedMeansIndependentReporter` | with no AP-F void, an independent reporter exists |

**Non-vacuity.** Five `run` commands confirm that each closure type, a captured channel and a succession void can all occur.

**What it found.** With the runtime's original AP.1b rule (a void only when no successor is registered), `NoSinglePointOfStewardship` had a counterexample: a failure mode whose successor *is* its steward. The draft calls that "a single point of failure". The runtime now reports it as an AP.1b void, and `tests/test_gates.py` scene 21 guards the fix.

## Keeping models and code in step

`tests/test_verification.py` checks the following without needing Java:

- the TLA+ transition table equals `cclf.statemachine.TRANSITIONS`;
- the open states, exit types, exits that leave a loop open, and legal sub-types match;
- the model's re-entry rule gives the same answer as `reentry_allowed()` for every exit type, legal sub-type and combination of conditions (544 cases);
- Alloy's EES-eligible kinds equal `EES_ELIGIBLE_KINDS`.

With `TLA2TOOLS_JAR` and `ALLOY_JAR` set (which `run.sh` does), it also runs TLC at a small bound, the mutation check, and every Alloy command.

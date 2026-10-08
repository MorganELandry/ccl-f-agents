# Formal verification

These are machine-checked models of the parts of the CCL-F v0.2 runtime where a wrong rule would be most costly:
- a **TLA+** model of the Layer 4 commitment state machine, checked exhaustively by TLC;
- a **TLA+** model of a federation: three nodes as separate machines, one free to fork and lie, over an adversarial network;
- an **Alloy** model of closure typing, the Layer 0 voids, Closure Chain and the decision-level independence rules, checked by the Alloy Analyzer.

A Python test (`tests/test_verification.py`) ties both models to the code, so they cannot drift apart unnoticed.

```bash
bash verification/run.sh      # downloads pinned, checksummed jars; about 2 hours
```

It needs Java 17 or later. Without Java, the model-to-code tests still run in the normal `pytest`; only the checker runs are skipped.

## Scope

These models check the **0.2 automaton as written**: its transition table, exits, recovery conditions, audit log, gates, execution class assignment, Closure Chain and the decision-level External Evidence Source. They are a first piece of the v0.2 draft's 0.3 discrete track ("formal transition semantics, invariants, TLA+/Alloy verification"), not the whole of it. They do not cover:

- transition-function semantics;
- coherence scoring;
- thresholds;
- the continuous dynamics.

A passing check means no counterexample exists **within the bounds** below. It is not a proof for systems of every size.

## TLA+: `tla/CommitmentStateMachine.tla`

**Model.** One model, checked in three configurations (below). It has:

- all 14 table transitions;
- all 14 exit types, with the four legal sub-types;
- re-entry conditions: successor, a different agent, a hold lifted, a resolution condition registered at exit and met;
- the Rule 8 model update;
- Rule 4 acceptance;
- the three gates: routine (signals registered), elevated (each signal at least classified) and irreversible (a constraint counts as resolved only if evidence-closed or exited terminal/superseded), with the logged override;
- Execution Class Assignment: the decision may be registered at any class, with or without a tested reversal path; the gate applies the declared class only with that path, otherwise irreversible; reclassification, refused requests, the relabel-after-refusal review, and its resolution;
- Closure Chain: one signal's closing evidence may depend on another's (or each on the other, a cycle); soundness is computed as the runtime computes it, from no sound loops upward; a reopen upstream weakens every closure downstream and logs each one;
- the decision-level External Evidence Source: cited in the Rule 4 acceptance, or supplied by a chain-sound evidence closure.

Two things are abstracted to a yes/no: who produced the reversal evidence ("a tested reversal path exists") and who produced the acceptance evidence ("the acceptance cites an EES"). Each loop has one closing evidence item, given by its dependencies. Those independence tests, and "at least one qualifying item" across several items, are checked by the Alloy model and the Python tests instead.

| Configuration | What varies | Bound | Result |
|---|---|---|---|
| `CommitmentStateMachine.cfg` (lifecycle) | the full signal lifecycle, two signals; decision fixed as irreversible, no relabels | log of 8 records | 45,694,483 distinct states, depth 9; no violation |
| `Classes.cfg` (execution classes) | every class, reversal, refusal, relabel and review path; one signal | log of 7 records | 37,073,616 distinct states, depth 8; no violation |
| `Chain.cfg` (Closure Chain depth) | two signals, s1's evidence depending on s2; no exits | log of 12 records | 12,382,235 distinct states, depth 13; no violation |

In the lifecycle configuration s1's evidence depends on s2. The lifecycle run's bound is too short for a reopen to weaken a closure downstream (that takes ten records), which is why `Chain.cfg` exists. Every property below is checked in all three configurations; the cycle case is checked by the tests (`CycleBack = TRUE`).

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
| `NoCleanPassOverAuthorityClosure` | the irreversible gate never passes cleanly over a constraint closed by authority or role switch | Reversibility Logic; Execution Gates |
| `NoCleanPassOverBrokenChain` | the irreversible gate never passes cleanly over an evidence closure whose chain is broken, or without an External Evidence Source | Closure Chain; Execution Gates |
| `ChainWeakeningLogged` | a closure that loses its standing is logged in the same step | Closure Chain ("the weakened link is logged") |
| `SoundAllTheWayUp` | a sound loop is evidence-closed, and so is everything it depends on | Closure Chain |
| `CycleNeverSound` | a loop on a dependency cycle is never sound | Closure Chain ("A loop cannot be its own upstream") |
| `LowerClassNeedsReversal` | the gate applies a class below irreversible only with a tested reversal path | Execution Class Assignment |
| `NoLowerClassExecutionWithoutReversal` | nothing executes below irreversible without a tested reversal path | Execution Class Assignment |
| `RelabelAfterRefusalEscalates` | lowering the declared or applied class after a refusal opens the relabel review | Execution Class Assignment; Escalation Conditions |
| `NoExecutionWhileRelabelOpen` | nothing executes, by override or otherwise, while that review is open | Execution Class Assignment |
| `ReclassificationLogged` | every change of class or reversal support is logged | Execution Class Assignment |

**Not vacuous.** `tests/test_verification.py` plants ten faults in copies of the model and confirms TLC catches each:
- `classified → closed_authority` added to the table: `NoCloseBeforeReview` is violated;
- the pre-October-2026 gate restored, which let an authority-closed constraint pass: `NoCleanPassOverAuthorityClosure` is violated;
- the declared class trusted as given: `LowerClassNeedsReversal` is violated;
- the relabel review never opened: `RelabelAfterRefusalEscalates` is violated;
- an override allowed past the open review: `NoExecutionWhileRelabelOpen` is violated;
- only declared-class lowerings counted, so adding evidence after a refusal slips through: `RelabelAfterRefusalEscalates` is violated;
- soundness computed without looking upstream: `SoundAllTheWayUp` is violated, and on a cycle `CycleNeverSound` too;
- a reopen that doesn't log the closures it weakens: `ChainWeakeningLogged` is violated;
- the External Evidence Source dropped from the gate: `NoCleanPassOverBrokenChain` is violated.

## TLA+: `tla/FederatedClosure.tla`

**Model.** Node A has a decision resting on a loop owned by node B, and B's closing evidence rests on a loop owned by node C. This is `cclf/federation.py` with the following abstractions:

- A node's log is a sequence of loop events: registered, closed by evidence with a verified origin (`ok`), closed by evidence that fails its origin check (`unverified`), closed by authority, reopened.
- An **honest** node keeps one history and follows the state machine. A **dishonest** node may keep two histories (a fork) and write any event into either.
- A may receive any prefix of any history, at any time, in any order, any number of times. That is an adversarial network: delay, reordering, duplication, replay. Loss is never taking the step.
- Signatures are assumed unforgeable: a segment always comes from its node, and closure kinds are as their producers attested.
- The agents are **separate machines**. Every step belongs to one node and changes only that node's variables; `NodeIsolation` checks this.

`Verified` is what A's code checks before relying on a closure. `Grounded`, what the draft asks for, is written separately. Planted faults change `Verified` and `Receive`, never `Grounded`.

| Configuration | Bound | Result |
|---|---|---|
| `Federation.cfg`: B dishonest, C honest, B's evidence rests on C | histories of 3 events, A's log of 6 records | 23,081,672 distinct states, depth 16; no violation |

| Property | What it says | Source in the draft |
|---|---|---|
| `LocalClosureOnlyWhenGrounded` | A's mirror is closed only while A's verified copies of B's log, and C's, show the loop closed by evidence with a verified origin | Key Definitions: Attempted Closure, Local Closure; Closure Chain |
| `EquivocatorNeverRelied` | a node caught signing two histories is never relied on | Audit Trail (append-only) |
| `NoFalseAccusation` | only a node that really signed two differing histories is called an equivocator | |
| `NoRollback` | A's view of a node only grows | Audit Trail |
| `NoHistorySwitch` | A's view of a node never switches to a different history | Audit Trail |
| `ClosureOnlyByAcceptance` | the mirror closes only by a logged acceptance | Attempted Closure |
| `WithdrawalLogged` | a withdrawn acceptance is logged in the same step | Audit Trail |
| `ALogAppendOnly` | A's own log only grows | Audit Trail |
| `NodeIsolation` | every step changes the state of at most one node | (the federation's premise: no central authority) |

**Not vacuous.** The tests confirm, as violated witness invariants, that A really accepts, withdraws and catches forks, and they plant nine faults that TLC must catch: ignoring the third node, accepting unverified evidence, no recheck on a new log, no fork detection, accepting a rollback, trusting an equivocator, a silent withdrawal, A writing into B's log, and one write that moves two nodes.

**Not modeled here** (the Python tests cover them): more than one receiver, lineage statements, attestation relay binding, grants and revocations.

## Alloy: `alloy/closure_and_architecture.als`

**Scope.** Every instance with up to 5 of each kind of object (4 time points) for closure typing and Layer 0; up to 4 of each, with 5 iteration steps, for Closure Chain and the decision rules.

| Assertion | What it says |
|---|---|
| `RestatementIsNotEvidence` | citing only what existed at registration never yields an evidence closure |
| `NonEESKindsNeverClose` | model output, assertions and internal analysis never close by evidence |
| `NoSelfCertification` | the process under evaluation, or the registrant, cannot close by its own evidence |
| `EvidenceClosureHasIndependentSource` | every evidence closure rests on an independent producer |
| `RoleSwitchIsSelfClosure` | role-switch closure is always the registrant closing their own signal |
| `NoSinglePointOfStewardship` | with no AP-A or AP.1b void, losing any one agent still leaves someone named |
| `UncapturedMeansIndependentReporter` | with no AP-F void, an independent reporter exists |
| `SoundIsAFixedPoint` | one more round of the chain computation changes nothing (enough steps were taken) |
| `SoundIsLeast` | every set of loops closed under one round contains the sound set, so self-supporting structures never count |
| `SelfSupportNeverSound` | a loop whose every qualifying item depends on itself is never sound |
| `MutualSupportNeverSound` | two loops resting only on each other are never sound |
| `NonEvidenceUpstreamBreaksTheChain` | evidence resting on a loop not closed by evidence makes nothing sound |
| `SoundAllTheWayUp` | a sound loop has a qualifying item whose upstream loops are all sound |
| `LowerClassNeedsIndependentProof` | a class below irreversible applies only with reversal evidence from someone who neither set the class nor accepts the decision |
| `NoSelfCertifiedReversal` | reversal evidence from the class-setters or the acceptor never lowers the class |
| `NonEESNeverSupportsReversal` | model output, assertions and internal analysis never show a reversal path tested |
| `AcceptorCannotSupplyTheEES` | a decision supported only by its acceptor's own evidence has no External Evidence Source |
| `UnsoundClosuresNeverSupplyTheEES` | with nothing in the acceptance and no sound loop, there is no External Evidence Source |

**Non-vacuity.** Ten `run` commands confirm that each closure type, a captured channel, a succession void, a two-level sound chain, an evidence closure that isn't sound, a lower class that applies, a declared lower class gated as irreversible, and an External Evidence Source supplied by a loop can all occur.

**Planted faults.** `tests/test_verification.py` plants three faults and confirms each breaks its assertion: computing the chain from every loop instead of from none (`SelfSupportNeverSound`), letting the class-setter vouch for a reversal path (`NoSelfCertifiedReversal`), and letting the acceptor supply the decision's External Evidence Source (`AcceptorCannotSupplyTheEES`).

**What it found.** With the runtime's original AP.1b rule (a void only when no successor is registered), `NoSinglePointOfStewardship` had a counterexample: a failure mode whose successor *is* its steward. The draft calls that "a single point of failure". The runtime now reports it as an AP.1b void, and `tests/test_gates.py` scene 21 guards the fix.

## Keeping models and code in step

`tests/test_verification.py` checks the following without needing Java:

- the TLA+ transition table equals `cclf.statemachine.TRANSITIONS`;
- the open states, exit types, exits that leave a loop open, and legal sub-types match;
- the model's re-entry rule gives the same answer as `reentry_allowed()` for every exit type, legal sub-type and combination of conditions (544 cases);
- Alloy's EES-eligible kinds equal `EES_ELIGIBLE_KINDS`;
- the model's execution classes equal `ExecutionClass`.

With `TLA2TOOLS_JAR` and `ALLOY_JAR` set (which `run.sh` does), it also runs TLC on all three configurations, the cycle and the federation model at small bounds, the federation's witnesses, every planted fault, and every Alloy command.

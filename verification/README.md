# Formal verification

These are machine-checked models of the parts of the CCL-F v0.2 runtime where a wrong rule would be most costly:
- a **TLA+** model of the Layer 4 commitment state machine, checked exhaustively by TLC;
- a **TLA+** model of a federation: three nodes as separate machines, one free to fork and lie, over an adversarial network;
- an **Alloy** model of closure typing, the Layer 0 voids, Closure Chain and the decision-level independence rules, checked by the Alloy Analyzer.

A Python test (`tests/test_verification.py`) checks that the models and the code agree on the transition table, the open states and exit groups (the exits that leave a loop open, and the exits to an external process that the latch leaves in place), the re-entry rule, the evidence kinds that can be an External Evidence Source, and the execution classes; the rest of each model is written by hand from the draft, so a change to any other rule must be carried into the models by hand.

```bash
bash verification/run.sh      # downloads pinned, checksummed jars; about 2 hours
```

It needs Java 17 or later. Without Java, the model-to-code tests still run in the normal `pytest`; only the checker runs are skipped.

## Scope

These models check the **0.2 automaton as written**, in its October 2026 revision: its transition table and post-execution latch, exits, recovery conditions, audit log, gates, the structural review hold and the Emergency Justification, execution class assignment, Closure Chain and the decision-level External Evidence Source. They are a first piece of the v0.2 draft's 0.3 discrete track ("formal transition semantics, invariants, TLA+/Alloy verification"), not the whole of it. They do not cover:

- transition-function semantics;
- coherence scoring;
- thresholds;
- the continuous dynamics.

A passing check means no counterexample exists **within the bounds** below. It is not a proof for systems of every size.

## TLA+: `tla/CommitmentStateMachine.tla`

**Model.** One model, checked in four configurations (below). It has:

- all 14 table transitions, and the nine pairs of the post-execution latch (`executed_open`, terminal);
- all 14 exit types, with the four legal sub-types;
- re-entry conditions: successor, a different agent, a hold lifted, a resolution condition registered at exit and met;
- the Rule 8 model update;
- Rule 4 acceptance;
- the three gates: routine (signals registered), elevated (each signal at least classified) and irreversible (a constraint counts as resolved only if closed by a chain-sound evidence closure or exited as superseded; a terminal exit no longer counts), with the logged override;
- the post-execution latch: at an irreversible override, every signal the gate did not count as resolved, in whatever state (open, closed by authority or role switch, closed by evidence that is not chain-sound, or exited by any other type), moves to `executed_open`, except a signal exited to an external process (whistleblower, legal), which keeps its exit state (it still fails the gate); the override never produces `trajectory_lock`;
- the structural review hold, with reviews of two kinds: not suspendable (a review only a Rule 8 model update resolves, which escalates its signal; a suppressed signal; the relabel review) and suspendable (an off-envelope or containment review, opened on any registered signal and resolved later by what its trigger requires). As in the runtime, an off-envelope or containment review escalates its signal while the signal is in review, at once or when it arrives there, and resolving it releases the signal back to review unless a Rule 8 review still holds it; a Rule 8 review may join a signal already escalated that way. No irreversible decision executes, cleanly or by override, while either kind is unresolved;
- the Emergency Justification: an irreversible decision held only by suspendable reviews may execute, including over a signal escalated by such a review alone; the latch applies (that signal moves from `escalated` to `executed_open`), the holding reviews stay unresolved, and a post-event review is opened;
- Execution Class Assignment: the decision may be registered at any class, with or without a tested reversal path; the gate applies the declared class only with that path, otherwise irreversible; reclassification, refused requests, the relabel-after-refusal review, and its resolution;
- Closure Chain: one signal's closing evidence may depend on another's (or each on the other, a cycle); soundness is computed as the runtime computes it, from no sound loops upward; a reopen upstream weakens every closure downstream and logs each one;
- Closure Chain upstream: an upstream loop counts as resolved if it is sound or exited as superseded, so a supersession also cuts a dependency cycle;
- the decision-level External Evidence Source: cited in the Rule 4 acceptance only. Loop closures no longer supply it.

Abstracted to a yes/no: who produced the reversal evidence ("a tested reversal path exists"), who produced the acceptance evidence ("the acceptance cites an EES for the principal risk claim"), and the EES a supersession needs (every superseded exit is taken to have one). Each loop has one closing evidence item, given by its dependencies, so "every cited item" and "the item" are the same here. Those independence tests, and the every-item rule across several items, are checked by the Alloy model and the Python tests instead.

**Not modeled here**, and why:

- *Loop types.* Every signal is a constraint. The model has no uncertainty, dissent, classification or framing loops, so it does not check the evidence closure ratio or the rule that such a loop is latched only when open. Giving each signal a type would multiply every configuration by the type assignments for a rule the Python tests check directly.
- *The Emergency Justification's content.* Its five elements, who gives it (not the acceptor, outside their reporting line, unless on scene), and the recurrence count need identities, failure modes and more than one decision. The count is fixed at three per failure mode, whatever the domain's recurrence threshold: the third justification on a failure mode since that mode's last resolved Rule 7 review is refused and opens a Rule 7 review that no justification can suspend, and resolving that review starts the count again. The model has one decision, no agents and no failure modes; the Python tests check these.
- *Per-trigger resolution, below the two kinds of hold.* The model distinguishes a suspendable review (off-envelope or containment) from one that cannot be suspended, and resolves each in one abstract step: `ResolveEnvReview` for the first, `DocumentModelUpdate` (or `ResolveRelabel`) for the second. It does not track operational states or the trigger behind a non-suspendable review, so it does not check which resolution each trigger accepts: an off-envelope review only by evidence-based reclassification to nominal or elevated uncertainty, containment by independent steward review, a count trigger (recurrence, authority closures, AP-G) or a relabel only by a Rule 8 update, and the other triggers by a Rule 8 update or an independent finding that no model change is needed. The Python tests check these. Element 4 (reclassified Experimental, or kept in containment) is likewise not modeled. A signal carries at most one off-envelope or containment review at a time; the runtime keeps one per trigger, so a signal may have both.
- *The post-event review's hold.* An Emergency Justification opens the post-event review, and it is logged. In the runtime it then holds later irreversible decisions on the same loops, as an off-envelope review does, and a further Emergency Justification may suspend it. That needs a second decision; the model has one, and nothing in it waits on the review after execution.
- *The annotation on an external exit.* At an irreversible override, a loop exited to an external process keeps its exit state (checked: `ExternalExitKeptAtExecution`); the authorization record the runtime attaches to it as an annotation is not modeled.
- *Reviews that outlive their signal's state.* The runtime holds an irreversible decision with any unresolved review naming one of its signals, whatever state the signal is in. The model ties a Rule 8 review's hold to the `escalated` state and the suppression review's hold to `suppressed` (as before October 2026), so an exit from `escalated`, or a re-entry from `suppressed`, ends that hold in the model but not in the runtime. The model therefore permits more executions than the runtime, never fewer, so its safety properties still bind the runtime. Off-envelope and containment reviews are held as in the runtime, in any state.

| Configuration | What varies | Bound | Result |
|---|---|---|---|
| `CommitmentStateMachine.cfg` (lifecycle) | the full signal lifecycle, two signals; decision fixed as irreversible, no relabels, no classification reviews | log of 8 records | 45,211,733 distinct states (86,059,985 generated), depth 9, 29 min 27 s; no violation |
| `Classes.cfg` (execution classes) | every class, reversal, refusal, relabel and review path; one signal | log of 7 records | 37,029,495 distinct states (61,373,709 generated), depth 8, 13 min 23 s; no violation |
| `Chain.cfg` (Closure Chain depth) | two signals, s1's evidence depending on s2; no exits | log of 12 records | 11,254,517 distinct states, depth 13, 6 min 29 s; no violation |
| `Emergency.cfg` (Emergency Justification) | two signals, s1's evidence depending on s2; off-envelope and containment reviews, the Emergency Justification; no exits or relabels | log of 10 records | 3,287,449 distinct states (3,288,569 generated), depth 11, 1 min 42 s; no violation |

Results are from TLC 2026.10.06 (rev 94d0c50) with two workers on a 2-core machine (wall-clock times as measured on it). The external-exit latch change reaches only configurations with exits, so only the lifecycle and execution-class runs were repeated after it; `Chain.cfg` and `Emergency.cfg` have no exits, and their state spaces are unchanged.

In the lifecycle configuration s1's evidence depends on s2. The lifecycle run's bound is too short for a reopen to weaken a closure downstream (that takes ten records), which is why `Chain.cfg` exists. Every property below is checked in all four configurations; the cycle case is checked by the tests (`CycleBack = TRUE`).

| Property | What it says | Source in the draft |
|---|---|---|
| `NoCloseBeforeClassified` | A signal cannot be closed before it is classified | Layer 4, blocked transition 1 |
| `NoCloseBeforeReview` | A classified signal cannot be closed before review opens | blocked transition 2 |
| `NoSilentCloseFromSuppressed` | A suppressed signal cannot be silently closed | blocked transition 3 |
| `NoSilentReopen` | Every reopen is its own logged record | blocked transition 4 |
| `EscalatedNeedsModelUpdate` | escalated → under_review only once every review holding the signal is resolved by what its trigger requires: a Rule 8 review by a documented model update, an off-envelope or containment review by its own resolution in that step | Recovery transitions; Rule 8; Escalation Conditions (per-trigger resolution) |
| `EnvReviewHoldsTheLoop` | a signal named by an unresolved off-envelope or containment review is never simply under review: it is escalated (invariant) | Escalation Conditions; `under_review → escalated` |
| `EscalatedNeverClosesDirectly` | An escalated signal is never closed directly | Layer 4 table: escalated has only the recovery transition |
| `TrajectoryLockTerminal` | trajectory_lock is terminal | Layer 4 |
| `ExecutedOpenTerminal` | executed_open is terminal | Layer 4, the `executed_open` state |
| `NoForbiddenReentry` | terminal, superseded, timeout and whistleblower exits never re-enter (the latch may still record one as `executed_open`) | Exit transitions |
| `NoWaitingReentryWithoutCondition` | containment, deferred and ambiguity exits with no resolution condition registered at exit never re-enter | Exit transitions; Layer 2 exit obligations |
| `NoLegalReentryWithoutResumableSubtype` | judicial orders and statutory triggers never resume to review | Exit transitions (legal) |
| `AuditAppendOnly` | the log only grows; earlier records never change | Audit Trail |
| `EveryChangeLogged` | every state change is logged in the same step | Audit Trail |
| `Rule4` | execution implies acceptance | Rule 4 |
| `OpenLoopExecutionLogged` | executing past a failing gate leaves an open-loop authorization on record: an override or an Emergency Justification | Execution Gates |
| `NoOpenLoopAfterIrreversibleExecution` | after an irreversible execution, by any path, no signal is open, closed by authority or role switch, closed by evidence that is not chain-sound, or exited by a type other than superseded, whistleblower or legal (stated with its own literal sets) | POST-EXECUTION LATCH; Execution Gates, last paragraph |
| `ExternalExitKeptAtExecution` | a signal exited whistleblower or legal keeps its exit (type and legal sub-type) through execution by any path | Layer 4, the `executed_open` state ("A loop exited to an external process ... keeps that exit state") |
| `OverrideNeverLocks` | execution never moves a signal into trajectory_lock | Layer 4, the `executed_open` state |
| `NoIrreversibleExecutionPastReview` | nothing irreversible executes, cleanly, by override or under an Emergency Justification, while a signal is suppressed, or escalated by anything but an off-envelope or containment review alone (reviews that cannot be suspended; stated with its own literal sets) | Layer 4, Overrides; Escalation Conditions |
| `SuspendableReviewNeedsEJ` | an irreversible decision executes past an unresolved off-envelope or containment review only under an Emergency Justification | Overrides, Emergency Justification |
| `EJSuspendsWithoutResolving` | an Emergency Justification is given only over a decision held by an off-envelope or containment review, and every such review is still unresolved right after it | Emergency Justification ("suspends the holding reviews; it does not resolve them") |
| `EJOpensPostEventReview` | an Emergency Justification opens the post-event review in the same step | Emergency Justification |
| `NoCleanPassOverAuthorityClosure` | the irreversible gate never passes cleanly over a constraint closed by authority or role switch | Reversibility Logic; Execution Gates |
| `NoCleanPassOverNonResolvingExit` | the irreversible gate never passes cleanly over a constraint exited by any type but superseded (the terminal-exit loophole) | Execution Gates, operational definitions |
| `NoCleanPassOverBrokenChain` | the irreversible gate never passes cleanly over an evidence closure whose chain is broken, or without an External Evidence Source cited in the acceptance | Closure Chain; Execution Gates |
| `ChainWeakeningLogged` | a closure that loses its standing is logged in the same step | Closure Chain ("the weakened link is logged") |
| `SoundAllTheWayUp` | a sound loop is evidence-closed, and everything it depends on is sound or superseded | Closure Chain |
| `CycleNeverSound` | a loop on a dependency cycle is never sound, unless a supersession upstream cuts the cycle | Closure Chain ("A loop cannot be its own upstream") |
| `LowerClassNeedsReversal` | the gate applies a class below irreversible only with a tested reversal path | Execution Class Assignment |
| `NoLowerClassExecutionWithoutReversal` | nothing executes below irreversible without a tested reversal path | Execution Class Assignment |
| `RelabelAfterRefusalEscalates` | lowering the declared or applied class after a refusal opens the relabel review | Execution Class Assignment; Escalation Conditions |
| `NoExecutionWhileRelabelOpen` | nothing executes, by override, Emergency Justification or otherwise, while that review is open | Execution Class Assignment |
| `ReclassificationLogged` | every change of class or reversal support is logged | Execution Class Assignment |

**Not vacuous.** `tests/test_verification.py` plants thirty-three faults in copies of the model and confirms TLC catches each:
- `classified → closed_authority` added to the table: `NoCloseBeforeReview` is violated;
- the pre-October-2026 gate restored, which let an authority-closed constraint pass: `NoCleanPassOverAuthorityClosure` is violated;
- the declared class trusted as given: `LowerClassNeedsReversal` is violated;
- the relabel review never opened: `RelabelAfterRefusalEscalates` is violated;
- an override allowed past the open review: `NoExecutionWhileRelabelOpen` is violated;
- only declared-class lowerings counted, so adding evidence after a refusal slips through: `RelabelAfterRefusalEscalates` is violated;
- soundness computed without looking upstream: `SoundAllTheWayUp` is violated, and on a cycle `CycleNeverSound` too;
- a reopen that doesn't log the closures it weakens: `ChainWeakeningLogged` is violated;
- the External Evidence Source dropped from the gate: `NoCleanPassOverBrokenChain` is violated;
- an override allowed past an escalated signal, or a suppressed signal not counted as held: `NoIrreversibleExecutionPastReview` (or `NoOpenLoopAfterIrreversibleExecution`) is violated. These run in a small test-only configuration (one irreversible decision, no relabels or exits, a 7-record log) that reaches escalate-then-override in seconds.

Planted for the October 2026 revision (Scenes 16 and 17):
- the latch restricted to signals under review (the old rule): `NoOpenLoopAfterIrreversibleExecution` is violated (a closed_authority constraint survives the override);
- the latch skipping exited signals: `NoOpenLoopAfterIrreversibleExecution` is violated (a terminal exit survives);
- the latch moving signals into trajectory_lock: `OverrideNeverLocks` is violated;
- the latch moving a whistleblower or legal exit into `executed_open`: `ExternalExitKeptAtExecution` is violated;
- a terminal exit treated as an exit to an external process, so the latch leaves it standing: `NoOpenLoopAfterIrreversibleExecution` is violated;
- a whistleblower or legal exit counted as resolving at the gate: `NoCleanPassOverNonResolvingExit` is violated;
- a transition out of executed_open: `ExecutedOpenTerminal` is violated;
- the terminal exit counted as resolving again: `NoCleanPassOverNonResolvingExit` is violated;
- any exit upstream counted as resolving the chain: `SoundAllTheWayUp` is violated;
- loop closures allowed to supply the decision's EES (the old rule): `NoCleanPassOverBrokenChain` is violated;
- off-envelope and containment reviews not counted as holds: `SuspendableReviewNeedsEJ` is violated;
- an Emergency Justification allowed past an escalated or suppressed signal: `NoIrreversibleExecutionPastReview` is violated;
- a Rule 8 review that joins an off-envelope hold taken for part of it (and suspended with it): `NoIrreversibleExecutionPastReview` is violated;
- an Emergency Justification with no suspendable hold, or one that resolves the reviews it suspends: `EJSuspendsWithoutResolving` is violated;
- no post-event review: `EJOpensPostEventReview` is violated;
- the justification logged as a plain permission: `OpenLoopExecutionLogged` (or `SuspendableReviewNeedsEJ`) is violated;
- the Rule 8 update releasing a signal an off-envelope review still names: `EnvReviewHoldsTheLoop` (or `EscalatedNeedsModelUpdate`) is violated;
- resolving the off-envelope review releasing a signal a Rule 8 review still holds: `EscalatedNeedsModelUpdate` is violated;
- no pending escalation (a signal arrives in review unescalated), or an off-envelope review that does not escalate a signal in review: `EnvReviewHoldsTheLoop` is violated.

Three witnesses must fail in `Emergency.cfg` (at an 8-record log): the invariants `NeverLatches` and `NeverEmergency`, and the action property `NeverEJOverEscalated`. A loop really is latched, a justification really is given, and one is given over a signal escalated by an off-envelope or containment review.

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
| `NoSelfCertification` | the closing agent, or the process under evaluation, cannot close by its own evidence (the registrant is no longer excluded as such) |
| `EvidenceClosureHasIndependentSource` | every evidence closure rests on a producer that is neither the closing agent nor the process under evaluation |
| `RoleSwitchIsSelfClosure` | role-switch closure is always the registrant closing their own signal |
| `NoSinglePointOfStewardship` | with no AP-A or AP.1b void, losing any one agent still leaves someone named |
| `UncapturedMeansIndependentReporter` | with no AP-F void, an independent reporter exists |
| `SoundIsAFixedPoint` | one more round of the chain computation changes nothing (enough steps were taken) |
| `SoundIsLeast` | every set of loops closed under one round contains the sound set, so self-supporting structures never count |
| `SelfSupportNeverSound` | a loop citing any item that depends on itself is never sound |
| `MutualSupportNeverSound` | two loops each citing evidence that rests on the other are never sound |
| `NonEvidenceUpstreamBreaksTheChain` | a loop citing any item that rests on a loop not closed by evidence is not sound |
| `SoundAllTheWayUp` | every item a sound loop cites rests only on sound loops |
| `OneCleanItemDoesNotCarryTheRest` | a loop citing any item that rests on a loop not sound is not sound, however good its other items (the old rule needed only one) |
| `LowerClassNeedsIndependentProof` | a class below irreversible applies only with reversal evidence from someone who neither set the class nor accepts the decision |
| `NoSelfCertifiedReversal` | reversal evidence from the class-setters or the acceptor never lowers the class |
| `NonEESNeverSupportsReversal` | model output, assertions and internal analysis never show a reversal path tested |
| `AcceptorCannotSupplyTheEES` | a decision supported only by its acceptor's own evidence has no External Evidence Source |
| `LoopClosuresNeverSupplyTheEES` | with nothing cited in the acceptance there is no External Evidence Source, whatever the loops' closures show |

**Non-vacuity.** Twelve `run` commands confirm that each closure type, a captured channel, a succession void, a two-level sound chain, an evidence closure that isn't sound, an evidence closure that isn't sound although one of its qualifying items rests on nothing, an evidence closure resting on the registrant's evidence, a lower class that applies, a declared lower class gated as irreversible, and a decision with an External Evidence Source can all occur.

**Planted faults.** `tests/test_verification.py` plants six faults and confirms each breaks its assertion: computing the chain from every loop instead of from none (`SelfSupportNeverSound`), letting the class-setter vouch for a reversal path (`NoSelfCertifiedReversal`), letting the acceptor supply the decision's External Evidence Source (`AcceptorCannotSupplyTheEES`), and three pre-October rules: the EES excluding the registrant instead of the closing agent (`NoSelfCertification`), one clean item carrying a closure (`OneCleanItemDoesNotCarryTheRest`), and the loops' sound closures supplying the decision's EES (`LoopClosuresNeverSupplyTheEES`).

**Not modeled here:** exits. "Resolved" upstream means sound; the supersession that also resolves an upstream loop is checked by the TLA+ model.

**What it found.** With the runtime's original AP.1b rule (a void only when no successor is registered), `NoSinglePointOfStewardship` had a counterexample: a failure mode whose successor *is* its steward. The draft calls that "a single point of failure". The runtime now reports it as an AP.1b void, and `tests/test_gates.py` scene 21 guards the fix.

## Keeping models and code in step

`tests/test_verification.py` checks the following without needing Java:

- the TLA+ transition table, the nine latch pairs into `executed_open` included, equals `cclf.statemachine.TRANSITIONS`;
- the open states, exit types, exits that leave a loop open, exits to an external process (`EXTERNAL_EXITS`), and legal sub-types match;
- the model's re-entry rule gives the same answer as `reentry_allowed()` for every exit type, legal sub-type and combination of conditions (544 cases);
- Alloy's EES-eligible kinds equal `EES_ELIGIBLE_KINDS`;
- the model's execution classes equal `ExecutionClass`.

With `TLA2TOOLS_JAR` and `ALLOY_JAR` set (which `run.sh` does), it also runs TLC on all four configurations, the cycle and the federation model at small bounds, the federation's and the Emergency configuration's witnesses, every planted fault, and every Alloy command.

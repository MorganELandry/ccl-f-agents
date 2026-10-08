# Architecture

This repository is a runtime monitor for the **Coordination Control Loop Framework (CCL-F), v0.2 working draft**. It implements the parts of the draft that a program can check from recorded facts:

- the Layer 4 commitment state machine;
- Layer 2 closure typing, escalation conditions and loop exits;
- the Layer 4 coherence score and execution gates;
- the Layer 0 architecture voids that can be detected from registered facts.

Where the draft leaves something open, the code makes a choice and labels it an implementation decision. Those choices are listed in [DECISIONS.md](DECISIONS.md). They are this project's reading of the draft, not claims the draft makes.

## Components

```
events (plain dicts) ──► graph.py (LangGraph)  interpret ─► apply ─► assess
                                                  │           │         │
                                             advisor.py       ▼         ▼
                                             (proposes   supervisor.py  coherence
                                              only)      ├ statemachine.py
                                                         ├ types.py
                                                         └ audit.py (hash chain)
```

| Module | Role |
|---|---|
| `cclf/types.py` | The vocabulary: six signal types, five operational states, the commitment states, 14 exit types, four closure types, evidence kinds, referents, execution classes, ten escalation conditions. Records: `Signal`, `Evidence`, `ClosureRecord`, `ExitRecord`, `Decision`, `Architecture`. |
| `cclf/statemachine.py` | The Layer 4 transition table, transcribed row by row, plus named reasons for blocked transitions, `exit_allowed()` and `reentry_allowed()`. |
| `cclf/audit.py` | Append-only audit trail. Each entry holds the SHA-256 of the previous one, so editing, deleting or reordering an entry breaks `AuditTrail.verify()`. Entries cut off the end are caught only against a `head()` hash kept elsewhere. |
| `cclf/supervisor.py` | The rule engine. Every state change goes through it, and every rule it enforces is labelled with the draft section it comes from. |
| `cclf/advisor.py` | An optional language model that proposes a signal type and operational state for a free-text report (AI Applications: "AI as Coordination Signal Classifier"). It cannot register, close, classify or authorize anything, and its output never counts as evidence. |
| `cclf/graph.py` | A three-node LangGraph pipeline that replays events through the supervisor. A refused operation is recorded as the outcome, so a replay continues. |
| `cclf/observability.py` | Optional OpenTelemetry spans and metrics (see `observability/README.md`). |

The supervisor holds all state. The graph only orchestrates, and the model only proposes, so no safety rule depends on the model or on graph wiring.

## Signal lifecycle (Layer 4)

```
unregistered → registered → classified → under_review ─┬─► closed_evidence
                                                        ├─► closed_authority
                                                        ├─► closed_role_switch
                                                        ├─► suppressed
                                                        ├─► escalated
                                                        └─► trajectory_lock (terminal)

closed_* → under_review          reopen: rationale required; a role-switch closure needs an independent reviewer
suppressed → under_review        re-entry logged; the suppression stays on the record
escalated → under_review         only after structural review documents a Rule 8 model update
any open state → exited(type)    with that exit type's obligations
exited → under_review            only where the exit type's re-entry rule allows
```

Blocked, each with a named reason:

- closing a signal before it is classified or before review opens;
- closing a suppressed signal without re-entry;
- closing an escalated signal before structural review has documented a model update;
- any move out of a closed state except back into review;
- any move out of `trajectory_lock`.

## Closure typing (Layer 2, Key Definitions)

`Supervisor.attempt_closure()` decides the closure type. The caller does not choose it.

| Closure | When |
|---|---|
| **Evidence** | Some attached evidence passes **Evidence Novelty** (it was not present at registration) and the **External Evidence Source** test (its kind is a primary document, direct measurement, formal verification or independent party, and its producer is neither the process under evaluation nor the signal's registrant). Model output, assertions and internal analysis never qualify. |
| **Role switch** | The registrant closes their own signal while acting for the other referent (technical reality vs. customer, Rule 5.3) with nothing new. Reopening it needs an independent reviewer. |
| **Authority** | Anything else that closes the signal: a decision without qualifying evidence. |
| **Lock-in** | Recorded when an override of a failing irreversible gate latches constraint and anomaly signals under review into `trajectory_lock`. |

**Closure Chain.** Evidence can name the loops it depends on (`add_evidence(..., depends_on=[...])`). An evidence closure is *chain-sound* only if at least one item of its qualifying evidence has every upstream loop itself closed by a chain-sound evidence closure. Soundness is computed when needed, so reopening an upstream loop weakens every closure downstream of it, and each one that loses its standing is logged as `CHAIN_WEAKENED`. A closure that isn't chain-sound stays recorded as an evidence closure but counts as non-evidence at the gates, in the ratio and in the coherence score. Each evidence closure's audit entry records whether it was chain-sound when made (`chain_sound`) and which upstream loops were not (`broken_links`).

If a signal has a registered closure authority and the closer is outside it, the closure is logged as an `ATTEMPTED_CLOSURE`, and the signal stays open. Adopting a frame (`adopt_frame`) by someone within the framing signal's closure authority is an authority closure, and the signals it displaces are suppressed. From anyone else it is only an attempted closure.

## Escalation (Layer 2)

The ten escalation conditions each open a `StructuralReview`. Reviews are deduplicated per condition and scope: a repeat trigger adds its signals to the open review, logs `REVIEW_JOINED`, and escalates any added signal that is under review at once. A review is resolved only with a documented Rule 8 model update, and an escalated signal returns to review only then.

| Condition | Trigger in this runtime |
|---|---|
| `recurrence_threshold` | A recurrence group reaches the threshold (D1, default 3) |
| `off_envelope_or_containment` | A signal is classified off-envelope or containment |
| `authority_closure_count` | An irreversible decision's signals have more authority closures than the threshold (D5, default 1) |
| `role_switch_on_constraint` | A constraint signal is closed by role switch |
| `lock_in_with_open_constraints` | An irreversible gate is overridden while constraint or anomaly loops are open (latched into `trajectory_lock` or still failing the gate) |
| `suppressed_before_execution` | An irreversible request is made over a suppressed signal; the review blocks that same request |
| `framing_adopted_over_open_constraints` | A frame is adopted while it displaces open constraint signals |
| `credibility_discounting` | A credibility discount is not supported by the target's track record (D7) |
| `sender_discount_recurrence` | The agent's third unsupported discount (D6); discounts earned by a declining accuracy record do not count. The agent is placed under AP-G |
| `execution_class_downgrade_after_block` | A decision's declared class, or the class the gate would apply, is lowered after one of its execution requests was refused. Until the review is resolved the decision cannot execute at any class, even by override |

## Exits (Layer 2, Loop Exit Taxonomy)

All 14 exit types are supported. Their obligations are enforced, and a refused exit is logged as `EXIT_REFUSED`:

- terminal, legal and key-person exits note the open loop state;
- a delegated exit names a successor;
- a whistleblower exit names the external pathway and the suppression event behind it;
- a legal exit gives one of four sub-types;
- a containment, deferred or ambiguity exit can register a resolution condition: what the loop is waiting for.

Nine exit types leave the loop open (`EXIT_LEAVES_LOOP_OPEN`). At the irreversible gate, an exited constraint or anomaly loop counts as resolved only after a terminal or superseded exit (`RESOLVING_EXITS`); any other exit, including timeout, whistleblower and legal, still blocks it. Re-entry follows the taxonomy:

- stated for recoverable and delegated exits;
- a successor is needed for forced and key-person exits;
- a different agent is needed for a boundary exit;
- inferred for exhaustion;
- for legal exits, only a regulatory intervention or investigative hold, once lifted;
- refused here for whistleblower, which continues in an external process;
- none for terminal, superseded and timeout, which have no transition in the draft;
- for containment, deferred and ambiguity, only when the resolution condition registered at exit is met (D2); with none registered, never; the refusal says to re-register the concern as a new signal linked to the exited one.

## Coherence score (Layer 4)

The draft's five factors and provisional weights are used as given:

- open loops .30
- classification stability .25
- closure quality .20
- recurrence pressure .15
- authority compression .10

The factor formulas are D3. Closure quality counts each reopen as a closure that did not hold.

## Execution gates (Layer 4)

Requirements are cumulative across the three execution classes.

| Class | Requires |
|---|---|
| Routine | Every signal the decision depends on is registered; no Layer 0 void |
| Elevated | Plus: classification acknowledged; no open loop left merely registered |
| Irreversible | Plus all of the following: <ul><li>every constraint and anomaly loop closed by a chain-sound evidence closure, or exited terminal or superseded (weakest link)</li><li>evidence closure ratio (D4) over the other loop types</li><li>at least one External Evidence Source among the decision's evidence closures or the evidence cited in its Rule 4 acceptance</li><li>classification stabilized (D8)</li><li>recurrence groups reviewed</li><li>no unresolved structural reviews</li><li>open off-envelope or containment signals resolved</li><li>coherence at or above the threshold (D3)</li></ul> |

**Execution class is checked, not trusted.** Every decision is irreversible unless shown otherwise. A declared routine or elevated class applies only if the decision has a registered reversal path, backed by at least one External Evidence Source showing the path was tested. That evidence can't come from whoever registered, reclassified or accepted the decision, or from a process under evaluation in its loops. Without that support, the gate applies the irreversible requirements and reports both classes (`GateResult.declared_class`, `GateResult.execution_class`). `reclassify_decision()` logs every change. Lowering a class after a refused request escalates, and that review blocks execution at every class, without override, until it is resolved.

**Rule 4 acceptance** is required for every class and cannot be overridden: an agent must explicitly accept authorization, risk and rationale.

Other gate failures, apart from that relabeling block, can be overridden. An override:

- is logged with identity, rationale and time (`GATE_OVERRIDE`);
- reports any architecture void;
- on an irreversible decision, latches constraint and anomaly loops under review into `trajectory_lock` with a lock-in closure record, and logs `OPEN_LOOP_IRREVERSIBLE_EXECUTION` with those and every other constraint or anomaly loop that still fails the gate.

An executed irreversible decision cannot be executed again.

## Layer 0 (Architecture Precondition)

`architecture_check()` runs for every execution class and reports the voids it can see from registered facts. For each constraint and anomaly signal's failure mode (D9), it checks:

- **AP-A / AP.1:** no steward.
- **AP.1b:** no successor, or a successor who is the steward (still a single point of failure).
- **AP-F / AP.6:** every registered reporter is an interested party (a captured channel).
- **AP-G:** the registrant is under sender discount.

Across the whole architecture, it also checks:

- **AP.2:** a registered channel has not been tested under load, so it is treated as absent.

AP.3, AP.4, AP.5 and AP.8 need interviews or document review and are not checked.

## Audit

Every operation that changes state appends an entry with a logical clock time, the event, the actor and a payload. Payload enums are stored as their values. The runtime refuses an operation with no actor. `AuditTrail.verify()` recomputes the chain from the first entry onward. Given `expected_head`, it also checks that the chain ends at that hash. `run_demo.py` prints the head for this purpose.

## What the runtime cannot do

- **Read meaning.** It checks evidence by kind and producer, not by content. A restatement filed as a "direct measurement" by an independent party passes.
- **Authenticate actors.** Names are recorded as given.
- **Check AP.3, AP.4, AP.5 or AP.8.**
- **Supply the thresholds.** The draft leaves them domain-configured; the defaults here (D1, D3–D6) are starting points.

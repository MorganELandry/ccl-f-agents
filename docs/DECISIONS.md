# Implementation decisions

The CCL-F v0.2 working draft names many thresholds and tests without giving values or formulas. Where it is silent, the code had to choose. Each choice below is this project's reading of the draft, not a claim the draft makes. In the code, labelled choices are tagged `D1`–`D9`, and the others are marked `IMPLEMENTATION DECISION` in plain words.

The configurable values live in `Settings` (`cclf/supervisor.py`). A caller can pass different values per `Supervisor`.

## Labelled decisions

| ID | Draft says | This runtime | Where |
|---|---|---|---|
| **D1** | Rule 7: an escalation threshold for recurrence | **3** members of a recurrence group. Taken from the draft's Challenger account: "the escalation threshold was crossed after the third occurrence." | `Settings.recurrence_threshold` |
| **D2** | Containment, deferred and ambiguity exits re-enter "when the resolution condition registered at exit is met" (settled in the draft, October 2026) | The runtime cannot observe the condition, so `reenter(..., condition_met=True)` is the re-entering agent's stated claim, logged with the condition it answers. With no condition registered, re-entry is refused, and the refusal says to re-register the concern as a new signal linked to the exited one. | `statemachine.reentry_allowed` |
| **D3** | Coherence score: five factors with provisional weights, a "domain-configured threshold", and no formulas | **Threshold 0.6.** Factor formulas: <ul><li>**open loops:** 1 − (open or locked signals ÷ signals). Trajectory lock counts as open.</li><li>**classification stability:** the share of signals that pass D8.</li><li>**closure quality:** chain-sound evidence closures ÷ (real closures + reopens); 1.0 when there are neither.</li><li>**recurrence pressure:** 1 − the largest min(1, members ÷ threshold) over the decision's unreviewed groups.</li><li>**authority compression:** 1 − the largest share of all real closures that are one agent's non-evidence closures (an evidence closure that is not chain-sound counts as non-evidence); 1.0 with fewer than two real closures.</li></ul> | `Supervisor.coherence` |
| **D4** | A "minimum evidence closure ratio" for irreversible execution, applied (since October 2026) to the uncertainty, dissent, classification and framing loops only | **0.5** of those loops' real closures, counting only chain-sound evidence closures as evidence. Skipped when there are none. | `Settings.min_evidence_closure_ratio` |
| **D5** | Escalate when authority closures accumulate on an irreversible decision | Escalate when the count **exceeds 1**, that is, on the second authority closure. Fires once per decision. | `Settings.authority_closure_threshold` |
| **D6** | AP-G threshold: three, now stated and defended in the draft (Layer 2, AP-G threshold) | **3**. Only unsupported discounts count toward it (`unsupported_discounts`); every discount is still logged and counted in `discounts`. | `Settings.sender_discount_threshold` |
| **D7** | "Stable or improving accuracy rate": later recorded outcomes no less accurate than earlier ones; no outcome record means a discount is unsupported (operational definition added October 2026) | With at least two outcomes: later-half accuracy ≥ earlier-half accuracy, and overall accuracy ≥ ½. A single correct outcome also counts. **No record at all means the discount is unsupported**, so it escalates. | `Supervisor.accuracy_stable_or_improving`, `discount_supported_by_record` |
| **D8** | Rule 3: classification "stabilized" before irreversible execution, defined (October 2026) as no reclassification to a different operational state since review opened | Never classified means not stable. Classified but never reviewed means stable. Otherwise, take the classification in force when review opened; the signal is stable if every later classification equals it. Re-confirming the same state is fine. | `Supervisor._classification_stable` |
| **D9** | Layer 0 voids for "high-consequence failure modes" | **Constraint and anomaly signals** count as high-consequence. Only voids that can be seen from registered facts are checked: AP-A/AP.1, AP.1b, AP-F/AP.6, AP-G, AP.2. AP.3, AP.4, AP.5 and AP.8 need interviews or document review. | `Signal.high_consequence`, `Supervisor.architecture_check` |

## Other decisions

### Evidence and closure

- **Evidence Novelty by logical clock.** "Not present at registration" means the evidence was not attached at registration and its timestamp is later than the signal's. The runtime cannot tell whether new evidence merely restates old analysis.
- **External Evidence Source by kind and producer.** The draft's test is causal independence, which a runtime cannot see. Here it is two recorded facts:
  - the evidence's kind is a primary document, direct measurement, formal verification or independent party;
  - its producer is neither the process under evaluation nor the signal's registrant.
  
  Model output, assertions and internal analysis never qualify.
- **Nominal needs cited EES evidence.** A nominal classification (Rule 2) is accepted only when at least one cited item passes the EES test. Otherwise it is recorded as elevated uncertainty, and `CLASSIFICATION_REJECTED` is logged. Novelty is not required here. The runtime cannot check what the evidence says.
- **Role switch detected by referent.** A role-switch closure is one where the signal's registrant closes it while acting for the other referent (technical vs. customer, Rule 5.3) with no qualifying evidence.
- **No registered boundary means no limit.** If a signal has no closure authority set, anyone's closure counts. Otherwise, closers outside the set only attempt a closure.
- **Independent reviewer.** Reopening a role-switch closure requires an agent who is neither the registrant nor the closer.
- **Frame adoption** by someone within the framing signal's closure authority is an authority closure, and the signals it displaces are suppressed. From anyone else it is an attempted closure, and nothing is suppressed.

### Layer 0

- **A successor must be someone else.** AP.1b says "a single named steward with no registered successor is a single point of failure". A successor who is the same agent as the steward is treated as the same void. The Alloy model in `verification/` found this gap, and the draft's AP.1b now says so too (October 2026): "A successor who is the same agent or unit as the steward does not satisfy this condition".

### Escalation

- **One open review per condition and scope.** A repeat trigger adds signals to the existing review instead of opening a new one, logs `REVIEW_JOINED`, and escalates at once any added signal that is under review (found by the October 2026 comment audit; previously such a signal waited until it next entered review).
- **A resolved recurrence group stays reviewed.** Later members do not reopen it.
- **Recovery only through Rule 8.** An escalated signal returns to review only when its review is resolved with a documented model update.

### Exits

- **Exits that leave the loop open.** Nine exit types count as still open (for example in the coherence score and the off-envelope/containment gate check), following the draft's "Loop State After": recoverable, delegated, deferred, forced, exhaustion, boundary, ambiguity, key person and containment. The constraint-and-anomaly gate requirement is stricter: only terminal and superseded exits meet it.
- **Re-entry by exit type.**
  - **Stated:** recoverable and delegated.
  - **Needs a successor:** forced and key person.
  - **Needs a different agent:** boundary.
  - **Inferred:** exhaustion.
  - **Legal:** only regulatory intervention or investigative hold, and only once lifted; statutory triggers and judicial orders do not resume.
  - **External:** whistleblower. Re-entry is refused here because the loop continues in an external process.
  - **On a registered condition:** containment, deferred and ambiguity, when the resolution condition registered at exit is met (D2).
  - **None:** terminal, superseded and timeout (the draft gives no transition), and containment, deferred or ambiguity exits with no resolution condition registered.

### Gates

- **Cumulative classes.** The routine requirements apply to every class, and the elevated requirements also apply to irreversible.
- **Layer 0 voids fail every class.** The draft marks execution gates "Structurally void" when the precondition is not satisfied, so a void blocks routine and elevated decisions too.
- **"Classification acknowledged"** means every signal has an operational state. **"Open loops documented"** means no signal is still merely registered. (The draft adopted both readings as operational definitions in October 2026.)
- **Recurrence groups reviewed** fails only for a group with an unresolved review, as the draft's operational definition now also says.
- **Unresolved structural reviews block irreversible execution.**
- **Open off-envelope or containment signals block irreversible execution.** This follows the Key Definitions: off-envelope needs evidence-based classification before irreversible execution, and containment needs independent steward review.
- **Suppressed signals.** An irreversible request over a suppressed signal escalates first, so the review it opens blocks that same request.
- **Overrides.**
  - Every gate failure can be overridden except Rule 4 acceptance and the block on a decision whose class was lowered after a refused request (the draft says this one cannot be overridden).
  - A Layer 0 void can be overridden. It is still reported, and the override log records it.
  - Lock-in latching applies only to constraint and anomaly signals that are under review, the only state the transition table lets move to `trajectory_lock`. Those that fail the gate in any other way (open in another state, or closed without chain-sound evidence) are logged as still open.
  - An elevated override latches nothing.
- **Decision-level EES** (draft, October 2026). Evidence cited in the Rule 4 acceptance counts if its kind is EES-eligible and its producer is neither a process under evaluation in the decision's loops nor the accepting agent. The draft states no novelty or chain test for acceptance evidence, so the runtime applies none.
- **Closure Chain** (draft, October 2026). Dependencies are whatever `depends_on` records; the runtime cannot discover them. A dependency cycle is accepted at registration and simply never counts. `CHAIN_WEAKENED` is logged on reopen, the only way a closed upstream loop can lose its standing.
- **Execution Class Assignment** (draft, October 2026).
  - Reversal evidence must be EES-eligible and produced by none of these: an agent who registered or reclassified the decision, its accepting agent, or a process under evaluation in its loops. No novelty test applies, because the draft states none.
  - Support is assessed when needed. If the evidence's producer later becomes the accepting agent, the support is withdrawn.
  - "Blocked" means any execution request that wasn't permitted, including a Rule 4 refusal.
  - A lowering without reversal support is accepted, not refused; like a registration at that class, it is simply gated as irreversible.
  - The authority-closure-count escalation uses the applied class, so it also fires for a decision declared lower without support.
  - The TLA+ model covers execution classes in its own configuration (`verification/tla/Classes.cfg`), with the reversal evidence's independence abstracted to a yes/no.
- **Duplicate IDs are refused** for signals, evidence and decisions, so an accepted record cannot be silently replaced.

### Model use

- **The advisor only proposes.** It suggests a signal type and operational state for a free-text report. The supervisor applies Rule 2 to its proposal as to anyone's. If the model is unavailable or its reply is unusable, the proposal falls back to uncertainty with elevated uncertainty, never nominal.

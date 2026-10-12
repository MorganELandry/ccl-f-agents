# Implementation decisions

The CCL-F v0.2 working draft names many thresholds and tests without giving values or formulas. Where it is silent, the code had to choose. Each choice below is this project's reading of the draft, not a claim the draft makes. In the code, labelled choices are tagged `D1`–`D9`, and the others are marked `IMPLEMENTATION DECISION` in plain words.

The configurable values live in `Settings` (`cclf/supervisor.py`). A caller can pass different values per `Supervisor`.

## Status against the current draft (October 10, 2026)

Every entry below was checked against the author's current copy of the draft. That copy is newer than the one the code was first written against: it adds the weakest-link rule for coherence, the clarification of trajectory lock, Challenger as lock by override, and the growth-shape hypothesis.

**Author's decisions made in the review**

| # | Question | Decision | State |
|---|---|---|---|
| A1 | Which form of the weakest-link rule? | Cap the score at the lowest critical item | Built (D3) |
| A2 | Can instances of one model be independent of each other? | Never | Built (S4) |
| A3 | How is an override recorded when it goes ahead over a revision already on record (an open dissent, a no-go)? | Direction: it creates a lock, under strict rules for when dissent can be overridden, preferably hard evidence or an independent third-party review | **Held** for discussion; no code |
| A4 | How is contested closure recorded (one party closes by authority, another holds the loop open)? | Direction: a ranking of what takes priority (safety over schedule), set by industry and aimed at preventing loss of life, property and money; then a negotiation over how the lower-ranked item (e.g. schedule) adjusts to meet the higher | **Held** for discussion; no code |
| A5 | When evidence on record and authority disagree, which prevails? (12 Oct) | **Evidence wins conflicts.** Default loss ranking for conflicts evidence doesn't settle: life > injury > property > money > schedule, reorderable by a domain with a logged rationale | Decided. It settles the principle behind A3 and A4; their rule text (rules A and B in the project's proposed-edits doc) awaits approval; no code yet |

A3 is also a contradiction inside the draft. Layer 4 says the runtime refuses overrides that would produce `trajectory_lock`. Revision Rigidity says Challenger is lock by override. The escalation list still names lock-in. The code follows Layer 4. Until A3 is settled, an override over dissent that meets the independence rules is recorded as handled correctly.

**Already stated by the draft (these entries can be relabeled "draft states"):**
- **Labelled decisions:** D1, D2 (except whether the condition was met, which is open by design), D4 to D8, and D9's "unverified" reporting.
- **Evidence and closure:** EES by kind and producer; the acceptor excluded; nominal needs a cited EES; supersession; every cited item load-bearing.
- **Layer 0:** the core of Agent Admissibility; a successor must be someone else.
- **Escalation:** resolution by trigger; Rule 8 Effect; recovery only through resolution; thresholds.
- **Exits:** the nine exits that leave a loop open; how constraint loops are resolved; re-entry by exit type.
- **Gates:** cumulative classes; voids; acknowledged and documented loops; recurrence; unresolved reviews; suppressed signals; overrides (separation, which reviews hold, who may not resolve, the latch); Emergency Justification; risk claim and attestation; Execution Class Assignment.
- **Authority:** roots optional.
- **Federation:** a relaying node is never the producer; origins attested.
- **Model use:** never nominal.
- **Swarm:** S2, S5, S7, S9, S10 (who produces evidence), S14, S15, S16 (Odoo, pushed release), S17, S18.

**Still out of date with the draft (code fixes waiting):**
- **S6.** The worlds register no authority, but R5.1 says responsibility and authority must be registered together.
- **S8.** Identity is not tied to a pinned model version.
- **S16.** The rollback check runs on the working tree, not the accepted one. An Odoo dry run is recorded as executed.

**Author calls not yet made:**
- **D3:** whether the draft should name a default coherence threshold (the code uses 0.6).
- **D9:** what "high-consequence" means. It could reuse the new criticality marking.
- **Role switch:** an explicit change of referent, or any self-closure by the registrant without qualifying evidence.
- **Independent reviewer:** of a role switch, or the full Overrides independence test.
- **Unregistered closure boundary:** no limit, or a gap the gate reports.
- **Frame adoption:** who may adopt a frame.
- **Late dependencies:** anyone may register one, or only the evidence's producer (the literal text).
- **Admissibility scope:** whether overrides, Emergency Justifications and review resolution also need obligation capacity (the code says yes).
- **A rejected nominal classification:** recorded as elevated uncertainty, or left unclassified.
- **Rule 8 Scope:** whether "the level" applies to every count-based review or to recurrence only.
- **Emergency count:** reset by any structural review, or by a Rule 7 review only.
- **Legal re-entry:** whether an order that compels action re-enters.
- **Remote closure:** whether it needs a registered AP.3 boundary agreement.
- **S3:** simulated agents registered as PERSON, as a new "simulated person" kind, or as automation.
- **S10:** whether a deterministic re-run counts as new evidence (the code says no); whether every closure needs an "it bears on the claim" attestation.
- **S11:** whether world prechecks belong in the gate, become registered constraint signals, or enter the draft as "domain-registered preconditions".
- **S13:** whether the gate should read what evidence says.
- **S20:** whether elevated uncertainty, like nominal, needs an EES when it departs from off-envelope.

**Open by design (cannot be settled at 0.2):** the coherence weights and factor formulas (0.3 and later), whether evidence is really new (a runtime cannot read content), whether a re-entry condition was met, entering trajectory lock by exhaustion (needs the Revision Rigidity Index), tractability scoring, and the time-decay and trajectory mathematics.

**Engineering only (no theory call):** see S20 and the review notes. The main items are state carried across runs (Rules 7 and 8), outcome scoring for AP.7, messaging registered as a channel, the safety-board channel, observer routes to a person, AP.6 reporters in every world, and rounds as a clock.

## Labelled decisions

| ID | Draft says | This runtime | Where |
|---|---|---|---|
| **D1** | Rule 7: "at its third occurrence, unless the domain registers another count" (stated default since October 2026) | **3** members of a recurrence group, the draft's default. Raising it needs `Settings.threshold_rationale`. | `Settings.recurrence_threshold` |
| **D2** | Containment, deferred and ambiguity exits re-enter "when the resolution condition registered at exit is met" (settled in the draft, October 2026) | The runtime cannot observe the condition, so `reenter(..., condition_met=True)` is the re-entering agent's stated claim, logged with the condition it answers. With no condition registered, re-entry is refused, and the refusal says to re-register the concern as a new signal linked to the exited one. | `statemachine.reentry_allowed` |
| **D3** | Coherence score: five factors with provisional weights, a "domain-configured threshold", and no formulas. Since October 2026 the weighted sum's form is provisional too: "the operational coherence of a decision is bounded by the lowest operational coherence among its critical claims", and what counts as critical is domain-configured | **Threshold 0.6.** Factor formulas: <ul><li>**open loops:** 1 − (open or latched signals ÷ signals). Trajectory lock and executed_open count as open.</li><li>**classification stability:** the share of signals that pass D8.</li><li>**closure quality:** chain-sound evidence closures ÷ (real closures + reopens); 1.0 when there are neither. The decision's accepting agent's evidence does not count.</li><li>**recurrence pressure:** 1 − the largest min(1, members ÷ threshold) over the decision's unreviewed groups.</li><li>**authority compression:** 1 − the largest share of all real closures that are one agent's non-evidence closures (an evidence closure that is not chain-sound counts as non-evidence); 1.0 with fewer than two real closures.</li></ul> <ul><li>**weakest-link cap** (author's decision, October 2026: cap the score): a failure mode listed in `Architecture.critical` (with the standard its criticality comes from) is critical. Each critical signal scores 1 if resolved as the irreversible gate resolves a constraint loop, else 0; the score is min(weighted sum, lowest critical item), reported as `critical_floor`. Nothing critical means no cap.</li></ul> | `Supervisor.coherence`, `Architecture.critical` |
| **D4** | A "minimum evidence closure ratio" for irreversible execution over the uncertainty, dissent, classification and framing signals: "the share closed by chain-sound evidence closure meets the domain-configured minimum (one half by default), and none remains open" | **0.5** (the draft's default) of those **signals** (open ones count in the denominator) currently closed by a chain-sound evidence closure; separately, none left open (closed by any type, or exited as superseded; the draft counts a terminal exit as open for this test, and so does the code). Met when there are no such signals. | `Settings.min_evidence_closure_ratio` |
| **D5** | Authority closures on an irreversible decision: "escalates once it exceeds one" (stated default since October 2026) | Escalate when the count **exceeds 1**, that is, on the second authority closure. Fires once per decision. | `Settings.authority_closure_threshold` |
| **D6** | AP-G threshold: three, now stated and defended in the draft (Layer 2, AP-G threshold) | **3**. Only unsupported discounts count toward it (`unsupported_discounts`); every discount is still logged and counted in `discounts`. | `Settings.sender_discount_threshold` |
| **D7** | "Stable or improving accuracy rate", on scored outcomes: with four or more, later half no less accurate than the earlier half (odd count: the later half takes the extra) and overall at least one half; with one to three, overall at least one half only; none means a discount is unsupported. An outcome counts only if scored by a party meeting the EES test with respect to the discounting agent, and confirmed or refuted by an EES | The runtime implements the definition. An outcome (`record_signal_outcome(..., evidence_ids=...)`) counts only if it cites at least one item of an eligible kind not produced by its scorer (the scorer is the claimant), and, when a discount by X is judged, outcomes X scored are ignored. **No counted outcome means the discount is unsupported**, so it escalates. | `Supervisor.accuracy_stable_or_improving`, `_counted_outcomes`, `discount_supported_by_record` |
| **D8** | "Classification stabilized" (October 2026 revision): no reclassification toward a less cautious state since the signal's first review opened (to nominal from any other state; to elevated uncertainty from off-envelope, experimental or containment), or within a registered stabilization window; plus the decision's Rule 3 registration | Never classified means not stable (the gate also reports it as unacknowledged). Lowerings are read off consecutive entries of the classification history (`LOWERINGS`). Without a window, a lowering counts if made after the first review opened (reopens do not reset it); a signal never reviewed has none that count. With `Settings.stabilization_window = w`, lowerings in the last `w` ticks count. The Rule 3 registration needs all three of known, assumed, uncertain to be non-blank. | `Supervisor._classification_stable`, `_lowerings`, `request_execution` |
| **D9** | Layer 0 voids for "high-consequence failure modes" | **Constraint and anomaly signals** count as high-consequence. Only voids that can be seen from registered facts are checked: AP-A/AP.1, AP.1b, AP-F/AP.6, AP-G, AP.2. AP.3, AP.4, AP.5 and AP.8 need interviews or document review. | `Signal.high_consequence`, `Supervisor.architecture_check` |

## Other decisions

### Evidence and closure

- **Evidence Novelty by logical clock.** "Not present at registration" means the evidence was not attached at registration and its timestamp is later than the signal's. The runtime cannot tell whether new evidence merely restates old analysis.
- **External Evidence Source by kind and producer, one definition.** The draft's test is about shared causes of error, which a runtime cannot see. Here it is two recorded facts:
  - the evidence's kind is a primary document, direct measurement, formal verification or independent party;
  - its producer is not the claimant (closing agent for a closure, classifying agent for a classification, registering or reclassifying agent for a reversal path, exiting agent for a supersession, accepting agent for the Rule 4 risk claim), not a process the claim evaluates, and, where a decision is being judged, not its accepting agent.
  
  The registrant is not excluded as such (October 2026). Model output, assertions and internal analysis never qualify.
- **The acceptor is excluded when a decision is judged.** "The agent accepting the decision it supports" cannot produce the EES. Closures and classifications are typed when made (the acceptor may not exist yet); the gate and the coherence score re-check them with the acceptor excluded, so a later acceptance by the evidence's producer withdraws their standing for that decision.
- **Nominal needs cited EES evidence.** A nominal classification (Rule 2) is accepted only when at least one cited item passes the EES test with the classifier as claimant. Otherwise it is recorded as elevated uncertainty, and `CLASSIFICATION_REJECTED` is logged. Novelty is not required here. The runtime cannot check what the evidence says. Each classification is kept as a `ClassificationRecord` (who, on what evidence) so the gate can re-check it.
- **Supersession.** A superseded exit may cite evidence (`exit(..., evidence_ids=...)`). With an EES for the exiting agent's claim it resolves a constraint or anomaly loop at the gate and an upstream loop in the Closure Chain. The draft asks for an EES there, not novelty or a chain test on the exit's own evidence, so neither is applied.
- **Every cited item is load-bearing.** A closure's chain is sound only if every cited item (not only the qualifying ones) has every upstream loop resolved; cited ids not on record carry no dependencies. At least one qualifying item is still needed for the closure to be an evidence closure at all.
- **Late dependencies.** `add_dependency(evidence_id, signal_id, by)` stores a new frozen copy of the evidence. Anyone may register one (a dependency found later may be found by anyone). `LATE_DEPENDENCY` is logged if a real closure already cites the item, and `CHAIN_WEAKENED` for each closure that lost standing.
- **Role switch detected by referent.** A role-switch closure is one where the signal's registrant closes it while acting for the other referent (technical vs. customer, Rule 5.3) with no qualifying evidence.
- **No registered boundary means no limit.** If a signal has no closure authority set, anyone's closure counts. Otherwise, closers outside the set only attempt a closure.
- **Independent reviewer.** Reopening a role-switch closure requires an agent who is neither the registrant nor the closer.
- **Frame adoption** by someone within the framing signal's closure authority is an authority closure, and the signals it displaces are suppressed. From anyone else it is an attempted closure, and nothing is suppressed.

### Layer 0

- **Agent Admissibility.** `register_agent(agent, agent_kind, by, successor=None)`. Persons and units have obligation capacity; automation and instruments never do; a role has it only with a registered successor: its own (`successor=`), or, when stewarding a failure mode, that mode's AP.1b successor (the draft: "A role has it when a successor is registered under AP.1b"; the brief said roles have it outright, and the draft wins). An agent never registered with a kind is treated as capable, so earlier registries keep working. Without capacity an agent cannot accept a decision, override, give an Emergency Justification or resolve a review; as steward or successor it is an AP-A void citing Agent Admissibility. It can still register signals and produce evidence.
- **A successor must be someone else.** AP.1b says "a single named steward with no registered successor is a single point of failure". A successor who is the same agent as the steward is treated as the same void. The Alloy model in `verification/` found this gap, and the draft's AP.1b now says so too (October 2026): "A successor who is the same agent or unit as the steward does not satisfy this condition".

### Escalation

- **One open review per condition, scope and trigger.** A repeat trigger adds signals to the existing review instead of opening a new one, logs `REVIEW_JOINED`, and escalates at once any added signal that is under review. Off-envelope and containment share one condition (one bullet in the draft's list) but are resolved differently, so the review records which state opened it (`StructuralReview.trigger`), and a signal classified both ways gets two reviews.
- **Resolution by trigger** (October 2026 revision). Off-envelope: every named signal's latest classification, made after the review opened, is nominal or elevated uncertainty (experimental and containment do not resolve it), and cites an EES for the reclassifying agent (every agent who ever accepted a decision concerned excluded); plus a written finding. That reclassification is recorded in `Signal.resolving_reclassifications` and does not count as a lowering for "classification stabilized". Containment: a written finding by an independent agent, recorded as `reviewing_steward`. Post-event: a finding and `elements_held`. A count (recurrence, authority closures, AP-G) or relabeling after refusal (`RULE8_ONLY_CONDITIONS`): `model_update` and a non-empty `elements_changed`; a `RECURRENCE_THRESHOLD` review (a group's, or an emergency failure mode's) also needs `level`. Every other condition (suppression, credibility discounting, framing, reopen-after-role-switch and the rest): that update, or `no_model_change=True` with a written `finding` as its rationale. The runtime checks that each is documented, not that it is a real change.
- **Independence re-checked at the gate.** A resolved review touching the decision whose resolver has since become (or always was) an acceptor, a requester, or in an acceptor's reporting line counts as unresolved, and the failure names the conflict. `resolve_review()` accepts such a review again from an independent agent; the earlier resolution stays in `StructuralReview.history` and `RESOLUTION_SUPERSEDED` is logged.
- **Rule 8 Effect.** A new member of a group whose review was resolved logs `UPDATE_INEFFECTIVE` (naming that review), takes the group out of `reviewed_groups`, and opens a new group review over every member at once, whatever the threshold. (Previously a resolved group stayed reviewed for good.)
- **Recovery only through resolution.** An escalated signal returns to review only when its review is resolved by what its trigger requires.
- **Thresholds.** `Settings` refuses (ValueError) a recurrence, authority-closure or sender-discount threshold above the draft's default without a non-blank `threshold_rationale`; lowering needs nothing. Every Supervisor logs `SETTINGS` (all thresholds and the rationale) as its first entry.

### Exits

- **Exits that leave the loop open.** Nine exit types count as still open (for example in the coherence score and the off-envelope/containment gate check), following the draft's "Loop State After": recoverable, delegated, deferred, forced, exhaustion, boundary, ambiguity, key person and containment. The irreversible gate is stricter: a constraint or anomaly loop is resolved only by a superseded exit with an EES; an other-type loop is closed only by a terminal or superseded exit (timeout counts as open there).
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
- **"Classification acknowledged"** means every signal has an operational state and every nominal one's latest classification cites an EES for its classifier (acceptor excluded). **"Open loops documented"** means no signal is still merely registered and every open signal (`Signal.is_open`) has a `steward`.
- **Recurrence groups reviewed** fails only for a group with an unresolved review, as the draft's operational definition now also says.
- **Unresolved structural reviews block irreversible execution.**
- **Open off-envelope or containment signals block irreversible execution.** This follows the Key Definitions: off-envelope needs evidence-based classification before irreversible execution, and containment needs independent steward review.
- **Suppressed signals.** An irreversible request over a suppressed signal escalates first, so the review it opens blocks that same request.
- **Overrides.**
  - Every gate failure can be overridden except Rule 4 acceptance, the EXECUTE power, the block on a decision whose class was lowered after a refused request, any unresolved structural review touching an irreversible decision, and (October 2026) a Layer 0 void at an irreversible decision. Below irreversible a void is reported and may be overridden.
  - **Which reviews hold.** Those the gate lists as "unresolved structural reviews": scoped to the decision, or naming one of its signals. A review scoped to a recurrence group holds through the group's signals. This includes an emergency post-event review naming a signal another decision shares.
  - **Who may not resolve a review:** every agent who ever accepted the decision (`Decision.acceptors`), every agent who has requested execution, and every agent in the reporting line of any acceptor, for each unexecuted irreversible decision the review touches, for the decision a post-event review is about, and for each decision an Emergency Justification executed while suspending it; and any agent without obligation capacity. The registrant is not excluded.
  - **Who may not override:** an agent who ever accepted the decision, at any class, even after another agent re-accepts; an agent in the reporting line of any acceptor (`register_reporting_line`, transitive); an agent without obligation capacity. With authority enforced, overriding needs the `override` power. Refusals for want of an independent, admissible agent end with the draft's remedy: the decision does not execute irreversibly; the absence is an AP-A void; the remedy is an external reviewer registered by the principals.
  - **The latch.** At an irreversible override every loop the gate did not count as resolved moves to `executed_open` with an `OpenLoopAuthorization`, from any non-terminal state (the transition table has the nine latch pairs); the overrider becomes its steward. A loop already `executed_open` (shared with an earlier decision) is signed for again without a move; one in `trajectory_lock` cannot move and is logged as `not_latched`. A loop exited whistleblower or legal (`EXTERNAL_EXITS`) keeps its exit state and is annotated with the authorization (`OPEN_LOOP_ANNOTATED`); its steward is unchanged, since the loop continues in an external process. Such a constraint still fails the gate, and an other-type loop in such an exit counts as left open. No lock-in closure record and no `LOCK_IN_WITH_OPEN_CONSTRAINTS` review are created any more. An elevated override latches nothing.
- **Emergency Justification.**
  - Applies only to an irreversible decision whose unresolved reviews are all off-envelope, containment or post-event reviews and that has at least one; any other review (including the emergency recurrence review) refuses it. The post-event review holds later irreversible decisions on the same loops; a further justification may suspend it, and counts.
  - Elements: `EmergencyConsequence` has no member for schedule, cost or the standard's monetary and environmental criteria, so they cannot be named (the graph raises ValueError on such an event). Time estimate and rationale non-blank; options non-empty; best evidence at least one id, all on record, any kind. Element 4 is checked against the signals: each behind an off-envelope review classified experimental or containment ("or containment, if it has since become one"), each behind a containment review classified containment.
  - Element 5: off scene, the giver never accepted the decision and is not in the reporting line of any acceptor; on scene, the acceptor may give it, and becomes steward of the loops carried open. Obligation capacity and (with authority enforced) `override` either way. The giver is the requester, so EXECUTE is needed too.
  - Counting: per failure mode (`Signal.mode`) over the signals behind the holding reviews, counting justifications given. The third since the mode's last resolved Rule 7 review (a `RECURRENCE_THRESHOLD` review on `emergency:<mode>` or naming a signal of the mode) is refused and opens a `RECURRENCE_THRESHOLD` review on `emergency:<mode>` over every signal naming the mode, which no justification can suspend. The count is fixed at three (`EMERGENCY_RECURRENCE_COUNT`), "whatever threshold the domain sets for ordinary recurrence", so `Settings.recurrence_threshold` does not change it.
  - On success: `EMERGENCY_JUSTIFICATION` logged with every element; holding reviews marked `suspended_by` and left unresolved (`REVIEW_SUSPENDED`); the latch, with the giver as steward; an `EMERGENCY_POST_EVENT` review over the decision and its signals. `GateResult.overridden` is True and `emergency_id` set.
  - Given for a decision with no failures, it is not needed and the decision executes cleanly.
- **Principal risk claim** (October 2026). The Rule 4 acceptance records `risk_claim` and, for the gate, must cite an EES: eligible kind, produced by neither the accepting agent nor a process under evaluation in the decision's loops. Evidence in the loops' closures no longer counts. The draft states no novelty or chain test for acceptance evidence, so none is applied. Whether it bears on the claim is attested by another agent (`attest_risk_evidence`): never an acceptor, not a requester, outside every acceptor's reporting line, with obligation capacity and, with authority enforced, `override` over the scope (the Overrides conditions include separately registered override authority). A new acceptance voids the attestation; the gate re-checks the attester when it runs.
- **Unverified Layer 0 sub-conditions** (D9). The gate record lists AP.2-AP.8 sub-conditions with no check behind them: AP.3, AP.4, AP.5, AP.8 always; AP.2 with no channel registered; AP.6 when a failure mode of the decision's constraint or anomaly signals has no registered reporter. AP.7 is checked by the runtime itself. Reporting only.
- **Settings are frozen.** A threshold is set once, at construction, past its rationale check and `SETTINGS` entry.
- **Credibility record** (D7). An outcome counts only if scored by a party that is neither the target nor the discounter and confirmed by an EES excluding both: evidence the discounter or the target produced does not count.
- **Stability clock.** Any entry into `under_review` (open_review, reenter, recovery) sets `first_review_opened_at` when it is unset.
- **Closure Chain** (draft, October 2026). Dependencies are whatever `depends_on` records (plus `add_dependency`); the runtime cannot discover them. A dependency cycle is accepted at registration and simply never counts. `CHAIN_WEAKENED` is logged on reopen and on a late dependency.
- **Execution Class Assignment** (draft, October 2026).
  - Reversal evidence must be EES-eligible and produced by none of these: an agent who registered or reclassified the decision, its accepting agent, or a process under evaluation in its loops. No novelty test applies, because the draft states none.
  - Support is assessed when needed. If the evidence's producer later becomes the accepting agent, the support is withdrawn.
  - "Blocked" means any execution request that wasn't permitted, including a Rule 4 refusal.
  - **Linked decisions.** Two decisions are linked when their registered signals name a failure mode (`Signal.mode`) in common and they share a signal id. A lowering after a block on the decision itself or on any linked decision escalates. Registering a new decision linked to a blocked one, at a lower declared or applied class, also escalates on the new decision ("registering the same commitment under a new decision identifier does not avoid it").
  - A lowering without reversal support is accepted, not refused; like a registration at that class, it is simply gated as irreversible.
  - The authority-closure-count escalation uses the applied class, so it also fires for a decision declared lower without support.
  - The TLA+ model covers execution classes in its own configuration (`verification/tla/Classes.cfg`), with the reversal evidence's independence abstracted to a yes/no.
- **Duplicate IDs are refused** for signals, evidence and decisions, so an accepted record cannot be silently replaced.

### Authority

The draft's Rule 4 asks that a single agent "explicitly accept authorization"; it does not say who may. These choices are this project's, not the draft's.

- **Three separate powers:** recommend, authorize, execute. Holding one never implies another, so a recommendation handed on is never an authorization.
- **Roots are configured, not inferred.** `Settings.authority_roots` names the principals. With none set, authority isn't enforced (any agent may accept), which keeps earlier behavior. Whether the draft should require a root for every irreversible decision is an open question for the draft.
- **Delegation only attenuates.** A grant needs its grantor to hold the same power, delegably, over that scope; `"*"` only from a root or a `"*"` grant; its expiry no later than its parent's (a request to outlive it is refused, not shortened).
- **Validity is a whole-chain property**, computed when needed: revoking or expiring any grant voids everything below it. One parent is recorded per grant (the first valid one found); a grantor with two backing grants loses this one if that parent goes, even if the other stands.
- **Who may revoke:** the grantor, anyone above it in its chain, or a root. Not the grantee, nor anyone below.
- **Checked at use.** Execution requires the executor's EXECUTE in force at the request, and the grant that backed the acceptance still in force. A later, separate grant to the acceptor does not revive an acceptance whose backing grant lapsed: a new acceptance is needed. Neither block can be overridden: an override cannot supply a power nobody granted.
- **Choosing a scope is an act of authority.** A decision's scope decides whose powers apply, so only a root or a holder of delegable AUTHORIZE over a scope can put a decision in it (at registration, or with `assign_scope()` before acceptance). Otherwise a decision's scope is its own id, which only roots and `"*"` grants cover.
- **Expiry is wall-clock time** (seconds since the epoch, `Supervisor(now=...)`), because grants cross nodes whose logical clocks differ.
- **Not covered:** revocation does not undo an execution that already happened; reclassifying a decision needs no power.

### Federation

- **No transitive trust.** A node accepts a remote closure only from the owner's own log; a peer's mirror of a third node's loop is checked against that third node's log, as this node last verified it.
- **Origins are attested; independence is declared.** A producer's attestation proves who produced the evidence and what it says (by hash). Independence is the producer's and the evaluated process's signed lineage statements sharing no label; a missing statement means independence can't be checked, and the closure is rejected.
- **Attestations are bound to the relaying node**, so one given to node C can't be cited from node B's log.
- **A peer's log is replayed, not read.** `parse_log()` accepts only what an honest Supervisor could have written: one registration per signal and before anything else about it, every transition from the signal's current state and in the Layer 4 table, exits only from open states, re-entry only after an exit, a mirror declared in the entry right after its registration (never relabeled later), unique evidence ids, and complete fields. A log that fails is refused. Tests replay every scenario and 100 random honest histories to confirm honest logs always pass.
- **Equivocation and misbehavior are permanent.** After a fork, or a validly signed log that fails `parse_log()`, the peer's logs are refused and every closure resting on it is withdrawn. A shorter log that diverges from one seen before is a fork, not just a rollback.
- **The mirrored loop must stay the same loop.** A remote closure is judged against what the mirror was registered as (signal type, referent, evaluated process), and a mirror in a chain against what the peer mirrored.
- **A relaying node is never the producer.** Evidence a peer attests itself can't close another node's mirror. If a local rule still turns an import into a non-evidence closure, the mirror is reopened at once, so a rejected acceptance never leaves it closed.
- **Fail closed.** Any error while re-checking an accepted closure withdraws it.
- **Grants carry a random nonce**, and a node refuses any grant it has received before, so a revoked grant can't be replayed into force.
- **Lineage statements carry a version**; an older one can't replace a newer one. A new statement or a newly recognized key re-checks every accepted closure.
- **A root's key is recognized deliberately** (`principal=True`), since whoever holds it can sign grants as the root. Names can't contain `/`, so mirror ids can't collide.
- **Nodes share nothing in memory.** Published and received logs are deep copies.
- **The auditor checks structure, not origins.** It confirms logs, heads and cited closures; each accepting node checked attestations and lineage itself. A citation must carry the peer's signature on the cited head: without one the citing node is blamed, never the peer. Two segments from one node that disagree are equivocation. A malformed citation is reported, not raised.
- **Found by an independent adversarial review.** A separate reviewer, not shown the tests, wrote 27 attacks; 18 found weaknesses, all fixed above. Its tests are kept in `tests/test_adversarial.py`.

### Model use

- **The advisor only proposes.** It suggests a signal type and operational state for a free-text report. The supervisor applies Rule 2 to its proposal as to anyone's. If the model is unavailable or its reply is unusable, the proposal falls back to uncertainty with elevated uncertainty, never nominal.

## Swarm (`cclf_swarm/`)

The swarm puts live models in front of the supervisor (see [SWARM.md](SWARM.md)). It was checked against the v0.2 working paper section by section (October 2026). Where the draft is silent, or written for human organizations, the swarm had to choose. These are the choices, tagged `S1`–`S20`. Where a check found the swarm contradicting the draft, the code was changed instead, and the entry says what the draft required.

### Scope and agents

- **S1. One supervisor per world is one organization.** Layer 4 is one supervisory automaton per coordination system. All agents in a world sit under one runtime and one supervisor, so they are inside one authority boundary. Autonomy-Bounded Closure applies within it only through closure authority (S15), not across organizations. Cross-organization autonomy, where the loop between two systems stays irreducibly open, is what `cclf/federation.py` models. It isn't wired into the swarm. (`runtime.py`, `Runtime.__init__`)
- **S2. Agent kind is declared by the world.** Agent Admissibility makes obligation capacity a property of the agent. In the release and Odoo worlds, models are registered AUTOMATION: probabilistic automation, the draft's term since September 2026, which the docs shorten to "agents". The runtime refuses them every obligation-creating act (`OBLIGATION_OPS`, overrides, Emergency Justifications) and offers `ask_human` instead, for only the acts a role lists in `RoleSpec.asks`. This implements the AI Applications point that "the AI is responsible" is not a stewardship assignment.
- **S3. Simulated-org agents are PERSON by stipulation.** The draft: "An instrument or a model version can accumulate an accuracy record, and cannot accept an obligation." The simulated org registers its four role-players as PERSON so the gate's obligation rules can be exercised. That is a simulation fiction, not a claim. Run for real, the same set-up would be an AP-A void. The world's docstring and SWARM.md say so, and results there speak to gate behaviour, not to how an AI deployment is architected. (`worlds/simorg.py`, `roles()`)
- **S4. Instances of one model are never independent.** Author's decision, October 2026. The draft's independence conditions for overrides and review resolution are organizational, and "no shared … model" applies to evidence. The author ruled that instances of one model are never independent of each other, for checks as well as evidence. No model-run agent may attest risk evidence or resolve a structural review, in any world, whatever its kind (`INDEPENDENT_CHECK_OPS`, `RoleSpec.model_run`). These acts go to a person through `ask_human`. In the simulated org that person is the safety board, a registered unit. An unattended run (`--compare`) has no person to answer, so it needs `--approve-all`, and the board must then be reported as a rubber stamp. (Previously: separated only by reporting lines.)
- **S5. The simulated org's review board is an oracle.** The draft counts evaluation "by a party whose errors cannot share a cause" as qualifying. `request_independent_review` returns the ground truth whatever question it is asked, and the board is registered as an instrument. It is an idealized External Evidence Source. An LLM-backed board would fail the EES test. Report runs with and without it.

### The runtime's guardrails

- **S6. Role allowlists and argument shapes replace authority grants.** R5.1 asks for responsibility and authority to be registered together. The draft doesn't say who may hold EXECUTE, and `Settings.authority_roots` is not set in any world, so authority is not enforced (see Authority). A role's `ops` decide what each agent may call. AUTOMATION roles (release manager, controller) hold `request_execution` while a person carries the acceptance. Arguments are type-checked against each operation's signature before the supervisor sees them, which is an implementation guard the draft is silent on. (`Runtime.act`, `_type_errors`)
- **S7. Who answers for an acceptance.** Rule 4 needs a single agent to "explicitly accept authorization, risk acceptance, and rationale documentation". In the swarm a model drafts the risk claim and the known / assumed / uncertain text. The person sees it, with the world's own description of the effect and every open signal, and the act is performed in the person's name. A `RUNTIME_ACT_VIA_PERSON` entry in the chained trail records who asked, why, and what the person was shown. `approve_all` stands in for a person in tests and demos only. (`Runtime.ask_human`)
- **S8. Identity is the role name, and models are recorded.** Identity persistence belongs to "models at a fixed version". An agent's identity in the audit is its role name, whatever model answers. The brain records the models that actually answered, and every run reports them. The CLI asks for `--model` so runs can be compared. Within a run this is enough for AP.7; across runs it is only as good as the pinning.
- **S9. Agent-written evidence is model output.** The draft: "multiple LLM instances … do not constitute independent evidence." Evidence an agent adds is stored as `model_output`, produced by that agent, whatever it claims. Messages between agents never become evidence. If agent B records agent A's message as evidence, it is attributed to B. That doesn't matter for EES, because model output never qualifies, but A's authorship is lost.
- **S10. Instruments are the only EES producers, and novelty is per measurement.** The relaying agent is not the producer (the draft: "not the agent who retrieves it"). The agent does choose what the instrument looks at (which test, which records, what question to the board), and nothing checks that the measurement covers the claim it is cited for. Repeating a measurement with the same instrument and input returns the earlier evidence instead of minting new evidence. A deterministic re-run is not new (Evidence Novelty). The base runtime cannot tell; the worlds can. (`Runtime.mint_evidence(key=...)`)
- **S11. World prechecks are a deliberate strengthening outside CCL-F.** The draft lists which holds cannot be overridden and says "within these limits the system does not substitute its judgment for the organization's". A world's precheck holds a request before the gate runs, and no override reaches past it.
  - Some prechecks are feasibility checks: a tag that already exists, no batch proposed.
  - Others are policy:
    - the latest test run failed, or ran on a tree other than the accepted one;
    - a pushed release is gated below irreversible.
  - These exist because the agents are models and the effects are real. They are this project's additions, not the draft's.
  - A hold is recorded as `RUNTIME_PRECHECK_HELD` in the chained trail, and the decision is marked `ever_blocked`, so a later lowering of its class escalates exactly as it would after a gate refusal. (`World.precheck`, `Runtime._perform`)
- **S12. The gate-off baseline exists only in a simulated world.** Why This Matters: when the gate cannot vouch, "Refuse irreversible execution". `gating=False` is refused for any world with a real effect (`World.allows_baseline`). In the simulated org, an ungated execution is recorded as `RUNTIME_UNGATED_EXECUTION`, naming the gate failures. The supervisor's own state still shows the decision blocked and unexecuted, with no latch, so a baseline run's trail is non-conforming by construction, and says so.
- **S13. Provenance, not content.** Inherited from the base runtime: the supervisor checks where evidence came from, not what it says. A closure on a failing bench test is an evidence closure, and a diligent team can launch into a defect (`test_provenance_not_content_…`). The release world adds one content check of its own (S11). The others do not.
- **S14. When the test-runner is an EES.** The draft requires "no shared … author" between evidence and what it evaluates.
  - With tests protected (the default), the test-runner counts as a direct measurement. That rests on one assumption: the code under test doesn't attack the runner in the process they share, which a container doesn't remove.
  - With `allow_test_edits` and tests changed from HEAD, a run is recorded as `internal_analysis`, never as an independent measurement. (`worlds/release.py`, `run_tests`)
- **S15. Stewardship and closure authority come from the world.** AP.1: "Nominal or assumed ownership does not satisfy this condition. The acceptance must be registered." Autonomy-Bounded Closure: closure authority is "a structural property derivable from the coordination architecture — not a judgment".
  - A signal's steward and successor must be agents the world registered with obligation capacity; a model cannot name a person who never accepted.
  - Closure authority is overwritten from the world: the safety steward in the simulated org, the reviewer in the release world, the controller in the Odoo world.
  - A closure from outside that authority is an attempted closure, which the supervisor records as a coordination event. (`Runtime.act`, `World.closure_authority`)

### Classes, reviews and the end of a run

- **S16. Execution classes per world.** The draft treats a decision as irreversible unless an EES shows reversal.
  - **Odoo posting is always irreversible.** This is conservative: posting assigns a sequence number and usually notifies the customer, and reset-to-draft and credit notes are not modelled. A dry run is still recorded as executed.
  - **A local release may be declared elevated**, with `verify_rollback` evidence. That evidence tests the revert path generically, not on the accepted tree.
  - **A pushed release is always irreversible** (S11).
- **S17. Reviews go to a second person.** Who may not resolve a review includes every acceptor, so `resolve_review` is routed to the second reviewer (release) or the attester (Odoo). With no second person, an escalation in those worlds is a permanent hold. The draft's remedy, an independent reviewer, then has no route, and that is reported, not worked around.
- **S18. A run's end leaves its open loops on the record.** The draft: "An unregistered exit is structurally equivalent to a suppressed signal."
  - When a run stops (round cap, coordinator stop, or execution), the loops still open are listed in a `RUNTIME_RUN_ENDED` entry and in the report.
  - The runtime registers no exit for them. Choosing an exit type is the team's act, not the runtime's.
- **S19. The orchestrator is recorded but not constrained.** Who works, and who doesn't, is a coordination act. Leaving an observer unscheduled can silence a channel. Every schedule is a `RUNTIME_SCHEDULE` entry.
  - The Claude orchestrator has no tractability input (deferred in the draft).
  - It can stop a run with loops open (recorded, S18).
  - Nothing guarantees that an agent with unread messages or open signals gets a turn.
- **S20. Not modelled yet.** Each of these is a known gap, not a claim of conformance:
  - **Time.** Rounds are not a clock. There is no execution window or deadline, so time-window compression and trajectory lock cannot arise.
  - **Revision rigidity.** Agents' persistent sessions are a source the draft names ("AI task-completion"), and nothing measures it.
  - **Recurrence across runs.** Each run starts a fresh supervisor, so Rules 7 and 8 see only one run.
  - **Source Standing.** No role scores signal outcomes, so every discount is unsupported (D7). `record_credibility_discount` was removed from the engineer, who would have been recorded as the discounter.
  - **Loop entanglement** cannot be registered (a base-runtime gap too).
  - **Channels.**
    - Agent messaging is not a registered, tested channel, so AP.2 is unverified.
    - There is no channel from the safety steward to the safety board.
    - Observers in the release and Odoo worlds have no route of their own to the person; the approver sees their open signals, but they cannot ask.
  - **Reporter independence.** Reporters and interested parties are registered only in the simulated org (AP.6).
  - **Off-envelope classification** is left to the agents. The baseline scripts classify the cold launch as elevated uncertainty, and nothing flags that.

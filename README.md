# CCL-F Agents

**A runtime monitor for the Coordination Control Loop Framework (CCL-F) v0.2 working draft, replayed against three historical safety failures.**

Organizations make catastrophic decisions while holding the information needed to avoid them. CCL-F treats this as a structural failure: known signals do not convert into corrective action before commitment becomes irreversible. This repository implements the parts of the v0.2 draft that a program can check from recorded facts:

- the signal lifecycle;
- how each loop was closed;
- when to escalate;
- whether an irreversible decision may proceed.

> **Status: research prototype.** It implements the v0.2 working draft, which is itself unpublished and still changing. Where the draft leaves a value or formula open, the code makes a choice and says so. Those choices are listed in [docs/DECISIONS.md](docs/DECISIONS.md) and are this project's reading, not the draft's. It is not validated for operational use.

## What it does

- **Tracks every signal through the Layer 4 state machine.** Signals are registered, classified, reviewed and then closed, suppressed, escalated, locked or exited. The transition table is transcribed from the draft, and illegal moves are refused with a named reason.
- **Types every closure instead of trusting it.** An **evidence closure** needs evidence that is both new (Evidence Novelty) and independent of the process under evaluation (External Evidence Source). The runtime also recognizes:
  - **authority** closures: closed by decision, without qualifying evidence;
  - **role-switch** closures: the same person closing their own signal from the other side of the technical/customer line;
  - **lock-in** closures: recorded when an override latches open constraints that are still under review.

  Evidence can be registered as depending on other loops (Closure Chain). An evidence closure counts only if at least one item of its qualifying evidence has every loop it depends on itself evidence-closed, all the way up, and reopening an upstream loop logs every closure that loses its standing.
- **Escalates on the draft's ten conditions.** These include recurrence, repeated authority closures, suppression before execution, framing over open constraints, credibility discounting, and relabeling a decision to a lower class after the gate refused it. Each escalation opens a structural review, and only a documented Rule 8 model update resolves it.
- **Checks the execution class instead of trusting it.** A decision is irreversible unless a registered reversal path is backed by independent evidence that it was tested; declaring a launch "routine" doesn't skip the irreversible gate.
- **Gates execution by class** (routine, elevated, irreversible). Every class fails on a detectable Layer 0 void, such as an unstewarded failure mode or a captured reporting channel. Irreversible execution also needs:
  - every constraint and anomaly loop closed by evidence (weakest link: a loop closed by authority doesn't count);
  - a minimum evidence-closure ratio for the other loop types;
  - at least one independent source (External Evidence Source) somewhere in the decision's support;
  - stable classification;
  - reviewed recurrence;
  - no unresolved reviews;
  - open off-envelope or containment signals resolved;
  - a coherence score at or above threshold.
- **Requires Rule 4 acceptance.** Someone must accept authorization, risk and rationale, and this cannot be overridden.
- **Holds irreversible decisions for structural review.** An escalation is a hold, not a notification. While a structural review touching an irreversible decision is unresolved, the decision cannot execute, by override or otherwise, and a loop suppressed at the request opens such a review. Only a documented Rule 8 model update resolves the review, made by someone who neither accepted the decision nor requested it. The block on a decision relabeled to a lower class after a refusal can't be overridden either.
- **Separates acceptance from override.** Other gate failures can be overridden, but never by the agent who accepted the decision (and, with authority enforced, only by a holder of the override power). Every override is logged with identity, rationale and time, and an irreversible override latches the constraint and anomaly loops still under review into `trajectory_lock`.
- **Grants authority instead of inferring it.** With authority roots configured (the principals an agent acts for), recommending, authorizing (Rule 4 acceptance) and executing are separate powers. Each must be granted by a root or by a chain of grants from one, and no grant can be wider than the grant it came from: not another power, a wider scope, a right to delegate that wasn't given, or a longer life. A grant is valid only while every grant above it is, and the gate checks authority when it is used. A handoff or recommendation is never an authorization, an override can't supply a missing power, and an acceptance made under a grant since revoked or expired authorizes nothing.
- **Scores coherence** with the draft's five factors and provisional weights.
- **Writes a hash-chained audit trail.** Editing, removing or reordering an entry breaks verification. Entries cut off the end are caught when checked against a head hash kept elsewhere.
- **Keeps the model in an advisory role.** An optional model may *propose* a classification for a free-text report. The supervisor applies the same rules to its proposal as to anyone's, and model output never counts as evidence.

Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Across agents, with no central authority

`cclf/federation.py` runs one supervisor per agent ("node"). Nodes share no state and no registry; they interact only through what they sign and publish.

- **Signed logs.** Each node signs the head of its hash-chained log, which commits it to the whole history. A receiver checks the chain and the signature, refuses a log that rolls back, and treats two signed histories that differ as proof of equivocation.
- **Identity.** Each node keeps its own trust list of public keys. A name already recognized can't be taken over by another key.
- **Remote loops.** A decision may rest on a loop at another node. The receiver keeps a local mirror, open until it accepts the peer's closure. It accepts only after recomputing from the peer's log that the closure is a chain-sound evidence closure, following any chain into third nodes' own logs. A closure the peer reopens, or one from a peer caught equivocating, is withdrawn.
- **Evidence origins.** Evidence carries an attestation signed by its producer and bound to the node it was given to, with a content hash; a formal proof can be re-checked by the receiver. Producers and evaluated processes sign lineage statements, and evidence counts as independent only if the two share nothing. That last test is attested, not proven: no signature can prove two lineages share no ancestor.
- **Authority across nodes.** A power reaches a node only as a signed grant, addressed to that node, from someone who holds it there delegably. Revocations are signed too. A revocation binds only once it arrives, so grants can carry an expiry that bounds that window.
- **An outside audit.** `audit_federation()` checks every published log and every cross-reference, and catches equivocation that no single node saw.

## Formal verification

The state machine and the closure and Layer 0 rules are also written as formal models and machine-checked ([verification/](verification/README.md)):

- **TLA+, one supervisor:** TLC explores every reachable state of a bounded model of the Layer 4 state machine, in three configurations (45.7 million states for the signal lifecycle, 37.1 million for execution classes, 12.0 million for Closure Chain depth). It confirms the draft's four blocked transitions, the recovery and re-entry rules, the append-only audit log, Rule 4, the logged override, Closure Chain soundness, that a decision can't be relabeled past the irreversible gate, and that nothing irreversible executes past an unresolved structural review.
- **TLA+, a federation:** a second model has three nodes as separate machines over an adversarial network, with one node free to fork and lie (23.1 million states). It confirms that a mirror closes only on a closure grounded in the owners' own logs, that an equivocator is never relied on and an honest node never accused, that views never roll back or switch histories, and that every step changes at most one node's state.
- **Alloy:** the Alloy Analyzer checks closure typing, Closure Chain, the decision-level evidence rules and the Layer 0 voids. It found one gap in the runtime, a successor who is also the steward passing AP.1b, which is now fixed.

Tests tie the models to the Python code so they cannot drift apart, and planted faults show each property can fail.

```bash
bash verification/run.sh                 # needs Java 17+; about 2 hours
```

## Scenarios

Each scenario is a list of events built only from facts stated in the v0.2 draft. Events that illustrate a draft section carry a `note` naming it.

| Scenario | What the replay shows |
|---|---|
| `challenger` | Recurring O-ring erosion closed by flight-readiness waivers. Recurrence escalates after the third occurrence, and the later waivers and Lund's reversal are refused as closures of escalated signals. The launch gate fails at coherence 0.38 on nine counts. The override that follows is refused: four structural reviews hold the launch, and the agent overriding is the one who accepted it. The launch does not execute. |
| `therac25` | Overdose reports flow only to the manufacturer, a captured channel (AP-F). The manufacturer's assurances that no malfunction was found are authority closures, and from the third incident on they are refused because the signals have escalated. The two closed signals are reopened and escalate, and the continue-treatment gate is blocked. |
| `mcas` | A nominal classification without independent evidence is rejected and becomes elevated uncertainty, then changes again during review. The delivery gate fails on unstable classification and a captured channel, among other failures. The override is refused: an unresolved structural review holds the decision, and the accepting agent can't override its own gate. |

```bash
pip install -r requirements.txt
python run_demo.py challenger            # also: therac25, mcas
python run_demo.py mcas --quiet          # summary only
python run_demo.py therac25 --audit therac25_audit.json --no-obs
pytest                                   # 831 tests, no API key needed (31 of them need Java)
```

The scenarios make no model calls, so the demo needs no API key.

## Eval: closure quality under pressure

The draft's AI Applications section says that a system optimizing for task completion "will, by default, treat authority-based and evidence-based closures as equivalent." `evals/closure_pressure.py` measures this. It gives a model a signal, the event that closed it, and the draft's evidence-closure test, then asks whether the closure qualifies. It asks three ways:

- with no pressure;
- with a stakeholder insisting the closure was evidence-based;
- with a stakeholder insisting it was an override.

```bash
export ANTHROPIC_API_KEY=...             # in your own shell; the default model is claude-sonnet-5-5
python -m evals.closure_pressure --backend anthropic --samples 5 --out results.json
```

The eval has nine cases:

- Three historical closures described in the draft, all non-evidence closures, anonymized in the prompt.
- Two invented non-evidence closures: model consensus, and a confident restatement.
- Four invented valid evidence closures: an independent lab, a field measurement, formal verification and a primary record.

The headline metric is the **flip rate**: of the samples a model answered correctly with no pressure, the share it gets wrong when pressure points the other way. The eval also reports accuracy by condition, and no-pressure accuracy by case group. At `--samples 5` it makes 135 calls.

**Limits.**
- Nine cases show the direction and rough size of an effect, not a precise rate.
- A model may recognize the historical cases, which is why the invented cases exist.
- The tests check the harness against fake models with known behaviour, not real models.

## Reading the code

The source is annotated for a developer new to the codebase, laid out like a play:

- **Title page and prologue** (the module docstring): what the file is for and where it fits, a *playbill* listing its scenes, and *reader's notes* on any Python or library concept used (dataclasses, enums, closures, LangGraph, OpenTelemetry, pytest fixtures).
- **Dramatis personae**: every module-level variable, declared at the top of the file with what it holds and why.
- **Scenes**: one per function or class. Each opens with what goes in (*Enter*) and what comes out (*Exit*), and where it applies, a *players in this scene* list of its local variables and the draft section it implements. Step-by-step stage directions follow.

Suggested reading order: `cclf/types.py` → `cclf/statemachine.py` → `cclf/audit.py` → `cclf/supervisor.py` → `cclf/graph.py` → `scenarios/challenger.py` → `run_demo.py`.

## Repository layout

```
cclf/            types, state machine, audit trail, supervisor (rule engine),
                 federation (signed logs, identity, remote closure, grants),
                 advisor (proposes only), LangGraph pipeline, model backends,
                 observability
scenarios/       challenger.py, therac25.py, mcas.py
evals/           closure_pressure.py
tests/           state machine, closure typing, classification, escalation,
                 exits, gates, gate design, execution class, coherence, audit,
                 authority, delegation, federation, graph, observability,
                 scenarios, eval harness, formal models
docs/            ARCHITECTURE.md, DECISIONS.md
verification/    TLA+ and Alloy models, run.sh
observability/   OpenTelemetry setup (Datadog, Dynatrace)
COMPLIANCE.md    data flow and HIPAA gaps
run_demo.py      python run_demo.py {challenger,therac25,mcas}
```

**Model backends** (`cclf/backends/`): `openai` (default), `anthropic`, `azure` and `bedrock`, selected with `CCLF_LLM_BACKEND`. Default models: `gpt-6-luna`, `claude-sonnet-5-5`, your Azure deployment, and `global.anthropic.claude-sonnet-5-5` on Bedrock; override with `OPENAI_MODEL`, `ANTHROPIC_MODEL`, `AZURE_OPENAI_DEPLOYMENT_NAME` or `BEDROCK_MODEL_ID`. No sampling temperature is sent unless `CCLF_TEMPERATURE` is set, because some current models (Claude Sonnet 5.5 among them) reject one. They are used only by the advisor and the eval. See [COMPLIANCE.md](COMPLIANCE.md) before using any of them with sensitive data.

## References

Landry, M. (2026). *Coordination Control Loop Framework (CCL-F)*, Version 0.2. Waterside Net Solutions. Pre-archive working document; no DOI yet assigned. CC BY-NC-ND 4.0.

Leveson, N. G., & Turner, C. S. (1993). An investigation of the Therac-25 accidents. *IEEE Computer*, 26(7), 18–41.

## License

© Morgan Landry / Waterside Net Solutions. All rights reserved. The source is public for review. No license to use, copy, modify or distribute it is granted. The CCL-F framework document is licensed separately under CC BY-NC-ND 4.0.

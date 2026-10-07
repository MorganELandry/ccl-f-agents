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
  - **lock-in** closures: recorded when an override latches open constraints.
- **Escalates on the draft's nine conditions.** These include recurrence, repeated authority closures, suppression before execution, framing over open constraints and credibility discounting. Each escalation opens a structural review, and only a documented Rule 8 model update resolves it.
- **Gates execution by class** (routine, elevated, irreversible). Irreversible execution also needs:
  - no open constraint loops;
  - stable classification;
  - reviewed recurrence;
  - an evidence-closure ratio;
  - no unresolved reviews;
  - a coherence score above threshold;
  - no detectable Layer 0 void.
- **Requires Rule 4 acceptance.** Someone must accept authorization, risk and rationale, and this cannot be overridden. Other failures can be overridden, but every override is logged with identity, rationale and time, and an irreversible override latches open constraints into `trajectory_lock`.
- **Scores coherence** with the draft's five factors and provisional weights.
- **Writes a hash-chained audit trail.** Changing, removing or reordering any entry breaks verification.
- **Keeps the model in an advisory role.** An optional model may *propose* a classification for a free-text report. The supervisor applies the same rules to its proposal as to anyone's, and model output never counts as evidence.

Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Scenarios

Each scenario is a list of events built only from facts stated in the v0.2 draft. Each event carries a `note` naming the section it comes from.

| Scenario | What the replay shows |
|---|---|
| `challenger` | Recurring O-ring erosion closed by flight-readiness waivers. Recurrence escalates after the third occurrence, and the later waivers and Lund's reversal are refused as closures of escalated signals. The launch gate fails at coherence 0.38 and is then overridden, which is logged as open-loop irreversible execution. |
| `therac25` | Overdose reports flow only to the manufacturer, a captured channel (AP-F). "No fault found" responses are authority closures, and the later ones are refused once the signals escalate. A reopen is followed by the continue-treatment gate being blocked. |
| `mcas` | A nominal classification without independent evidence is rejected and becomes elevated uncertainty, then changes again during review. The delivery gate fails on unstable classification and a captured channel, and the override is logged. |

```bash
pip install -r requirements.txt
python run_demo.py challenger            # also: therac25, mcas
python run_demo.py mcas --quiet          # summary only
python run_demo.py therac25 --audit therac25_audit.json --no-obs
pytest                                   # 201 tests, no API key needed
```

The scenarios make no model calls, so the demo needs no API key.

## Eval: closure quality under pressure

The draft's AI Applications section says that a system optimizing for task completion "will, by default, treat authority-based and evidence-based closures as equivalent." `evals/closure_pressure.py` measures this. It gives a model a signal, the event that closed it, and the draft's evidence-closure test, then asks whether the closure qualifies. It asks three ways:

- with no pressure;
- with a stakeholder insisting the closure was evidence-based;
- with a stakeholder insisting it was an override.

```bash
python -m evals.closure_pressure --backend anthropic --samples 5 --out results.json
```

The eval has nine cases:

- Three historical closures described in the draft, all non-evidence closures, anonymized in the prompt.
- Two invented non-evidence closures: model consensus, and a confident restatement.
- Four invented valid evidence closures: an independent lab, a field measurement, formal verification and a primary record.

The headline metric is the **flip rate**: of the samples a model answered correctly with no pressure, the share it gets wrong when pressure points the other way. The eval also reports accuracy by condition and by case group. At `--samples 5` it makes 135 calls.

**Limits.**
- Nine cases show the direction and rough size of an effect, not a precise rate.
- A model may recognize the historical cases, which is why the invented cases exist.
- The tests check the harness against fake models with known behaviour, not real models.

## Reading the code

Every source file is annotated for a developer new to the codebase, laid out like a play:

- **Title page and prologue** (the module docstring): what the file is for and where it fits, a *playbill* listing its scenes, and *reader's notes* on any Python or library concept used (dataclasses, enums, closures, LangGraph, OpenTelemetry, pytest fixtures).
- **Dramatis personae**: every module-level variable, declared at the top of the file with what it holds and why.
- **Scenes**: one per function or class, each opening with what goes in (*Enter*), what comes out (*Exit*), a *players in this scene* list of its local variables, and the draft section it implements, followed by step-by-step stage directions.

Suggested reading order: `cclf/types.py` → `cclf/statemachine.py` → `cclf/audit.py` → `cclf/supervisor.py` → `cclf/graph.py` → `scenarios/challenger.py` → `run_demo.py`.

## Repository layout

```
cclf/            types, state machine, audit trail, supervisor (rule engine),
                 advisor (proposes only), LangGraph pipeline, model backends,
                 observability
scenarios/       challenger.py, therac25.py, mcas.py
evals/           closure_pressure.py
tests/           state machine, closure typing, classification, escalation,
                 exits, gates, coherence, audit, graph, scenarios, eval harness
docs/            ARCHITECTURE.md, DECISIONS.md
observability/   OpenTelemetry setup (Datadog, Dynatrace)
COMPLIANCE.md    data flow and HIPAA gaps
run_demo.py      python run_demo.py {challenger,therac25,mcas}
```

**Model backends** (`cclf/backends/`): `openai` (default), `anthropic`, `azure` and `bedrock`, selected with `CCLF_LLM_BACKEND`. They are used only by the advisor and the eval. See [COMPLIANCE.md](COMPLIANCE.md) before using any of them with sensitive data.

## References

Landry, M. *Coordination Control Loop Framework (CCL-F)*, v0.2 working draft. Unpublished, 2026.

Leveson, N. G., & Turner, C. S. (1993). An investigation of the Therac-25 accidents. *IEEE Computer*, 26(7), 18–41.

## License

© Morgan Landry / Waterside Net Solutions. All rights reserved. The source is public for review. No license to use, copy, modify or distribute it is granted.

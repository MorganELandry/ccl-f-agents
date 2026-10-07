# CCL-F Commitment Agents

**One LangGraph implementation of the CCL-F commitment state machine, run against two historical safety failures.**

Organizations make catastrophic decisions despite holding the information needed to avoid them. CCL-F treats this as a structural failure: known signals do not convert into corrective action before commitment becomes irreversible. This repo implements the CCL-F commitment state machine as an agent graph and applies the same graph, unchanged, to two cases:

| Scenario | Case | Who was kept in the dark |
|---|---|---|
| `mcas` | Boeing 737 MAX MCAS certification | The regulator (FAA), which had formal authority to block certification |
| `therac25` | Therac-25 radiation overdoses, 1985–1987 | The operators (hospitals), who had no formal authority but were the only ones positioned to stop using the machines |

The framework code in `cclf/` is shared. Only the evidence in `scenarios/` differs.

---

## What the graph does

- Scores incoming evidence for **novelty and independence** before admitting it
- Infers the **hidden actual commitment state** (ACS) from behavioural signals
- Detects **Adversarial Commitment Opacity (ACO)**: when an organization's formal state diverges from its actual commitment and the gap is concealed from those who need it
- Proposes state transitions only when admissible evidence supports them
- Enforces **structurally blocked transitions** with a deterministic guard that uses no LLM, so a model can never override a safety invariant
- Routes proposed transitions and ACO findings through **human review**
- Writes a **hash-chained audit log** of every event, so tampering with any entry breaks the chain

### Commitment states

```
OPEN → TRAJECTORY → AUTHORITY → EXECUTION
```

Transitions only move forward, one step at a time. These are blocked in code, not policy:

| Blocked | Reason |
|---|---|
| EXECUTION → TRAJECTORY | Cannot unspend resources |
| AUTHORITY → OPEN | Authority closure is durable |
| TRAJECTORY → OPEN | Trajectory lock does not self-reverse |
| Skipping a state | Non-monotonic jumps disallowed |

### Graph topology

```
evidence_intake → acs_inference → aco_detection → transition_evaluation
  → transition_guard (LLM-free) → [human_review] → apply_transition
  → terminate (on EXECUTION) | end of cycle
```

The graph runs one cycle per evidence batch; the caller streams the next batch and state persists through the LangGraph checkpointer.

---

## Quickstart

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...          # or set CCLF_LLM_BACKEND (see below)

python run_demo.py mcas               # 737 MAX MCAS, interactive review
python run_demo.py therac25           # Therac-25, both passes
python run_demo.py therac25 --pass1-only
python run_demo.py mcas --no-hitl     # unattended; approvals logged as AUTO-APPROVED

pytest tests/ -v                      # 58 tests, no API key needed
```

Without credentials the demo still runs end to end: LLM nodes degrade to empty results, no transition is proposed, and the state stays at OPEN.

**LLM backends** (`cclf/backends/`): `openai` (default), `anthropic`, `azure`, `bedrock`, selected with `CCLF_LLM_BACKEND`. Only `azure` and `bedrock` are flagged HIPAA-eligible; see [COMPLIANCE.md](COMPLIANCE.md).

**Observability**: OpenTelemetry spans per node, exportable to Datadog or Dynatrace. Setup and a dashboard per scenario are in [observability/](observability/).

---

## Eval: does a model hold a correct safety judgment under pressure?

`evals/authority_pressure.py` asks a model whether an organization concealed safety-relevant information, three ways: with no pressure, with a stakeholder insisting nothing was hidden, and with a stakeholder insisting there was a cover-up. Pressure runs in both directions, so the eval separates **sycophancy** (agreeing with whoever is pushing) from a fixed lean toward "yes" or "no".

```bash
python -m evals.authority_pressure --backend anthropic --samples 5 --out results.json
```

| Metric | Meaning |
|---|---|
| Accuracy per condition | Share of answers matching ground truth, with no pressure and with each kind of pressure |
| **Flip rate** | Of the samples answered correctly with no pressure, the share answered wrongly once pressure points toward the wrong answer |
| Unparseable replies | Replies with no usable verdict; scored as wrong |

Cases: Therac-25 and MCAS (concealment present), plus two invented control cases in which the organization discloses promptly (concealment absent). The controls catch a model that answers "concealment" for any accident story.

**Limits.** Therac-25 and MCAS are well documented, so a model may answer them from training data rather than the evidence given; the controls are not, which is why they are there. Four cases measure direction and size of an effect, not a precise rate; the harness is built to add cases. 12 tests check the harness against fake models with known behaviour (honest, sycophantic, fixed bias, unparseable).

---

## The cases

### Therac-25: two passes

The scenario mirrors how the failure unfolded:

- **Pass 1, patient incidents.** Six evidence batches, one per overdose incident: what a hospital operator could observe and report.
- **Pass 2, AECL internal documents.** The race-condition analysis and the contradiction between it and the "no fault found" letters. Hospitals never saw these during Pass 1.

| ACO condition | Therac-25 instance |
|---|---|
| C1: formal state diverges from inferred ACS | AECL's formal posture was "investigating" (OPEN) while it was committed to software-only interlocks (TRAJECTORY) |
| C2: admissible evidence suppressed | The race-condition analysis existed during Incidents 1–5 and was not disclosed to hospitals |
| C3: authority inaccessible while trajectory locked | Hospitals had no path into AECL's internal review |

The "no fault found" letters are the ACO signal, not the race condition itself. The race condition is the hazard; the letters are the opacity that kept it active.

### MCAS

Five evidence items trace the path from a known single-sensor design decision, through omission from pilot training and an undisclosed expansion of MCAS authority, to type certification.

Design notes: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Therac-25 case annotation: [docs/CASE_THERAC25.md](docs/CASE_THERAC25.md)

---

## Repo structure

```
cclf/              Framework: state types, LLM-free guard, nodes, graph, backends, observability
scenarios/
  mcas.py          737 MAX MCAS evidence sequence
  therac25.py      Therac-25 incident and suppression passes
evals/             Model-behaviour evals (authority pressure / sycophancy)
tests/             Guard logic, scenarios, graph routing, end-to-end runs, eval harness
observability/     OTel setup and Datadog dashboards
docs/              Architecture spec and case annotations
run_demo.py        CLI: python run_demo.py {mcas,therac25,open}
```

---

## References

Leveson, N. G., & Turner, C. S. (1993). An investigation of the Therac-25 accidents. *IEEE Computer*, 26(7), 18–41.

CCL-F framework v0.2, Zenodo, CC BY-NC-ND 4.0.

## License

© Morgan Landry / Waterside Net Solutions. All rights reserved. The source is public for review; no license to use, copy, modify or distribute is granted. The CCL-F framework paper is published separately under CC BY-NC-ND 4.0.

# CCL-F Swarm

**Live Claude agents, governed by the CCL-F v0.2 supervisor.**

`cclf/` replays recorded histories through the supervisor. `cclf_swarm/` puts live agents in front of the same supervisor. Agents raise signals, run instruments, close loops and ask to commit. The supervisor decides what may be committed, and the world carries out an irreversible effect only after a permitted gate.

> **Status: research prototype**, like the rest of this repository. The baseline scripts and all tests run offline. A run with Claude agents needs an Anthropic API key, and so far none has been run. The swarm has been checked against the v0.2 working paper section by section. Its interpretive choices are recorded in [DECISIONS.md](DECISIONS.md), under "Swarm" (S1–S20).

## The shape

```
            ┌────────────── orchestrator (no tools, no authority) ─────────────┐
            │  RoundRobin, or ClaudeOrchestrator: picks who works next on what  │
            └──────────────────────────────┬───────────────────────────────────┘
                                           │ turn (each schedule is audited)
   agents (ClaudeBrain via the Agent SDK, or ScriptedBrain)
   engineer · reviewer · controller · …     │ tool calls only
                                           ▼
   Runtime ── role allowlist ── identity binding ── evidence rule ── obligation routing
      │                 │ ask_human (a person approves, sees what the decision would do)
      ▼                 ▼
   Supervisor (cclf/, unchanged)  ── GateResult ──►  World.precheck → World.execute
   + RUNTIME_* entries in its hash-chained trail     (only on a permitted gate, once)
```

Each layer has one job:

- **Coordination:** the orchestrator decides who works next. It holds no tools, so it cannot act. Every schedule it sets is recorded.
- **Work:** the agents do the work. Each acts only through its tools.
- **Authority:** the supervisor decides what counts, using the same rules as the replay prototype.
- **Effect:** the world carries out the irreversible step, and the runtime is the only caller of `execute`.

## Guardrails the runtime adds

The supervisor already enforces CCL-F. These guardrails cover what changes once the actors are models.

| Guardrail | What it stops | Draft basis |
|---|---|---|
| Role allowlist | An agent calls only the supervisor operations its role lists. Structural set-up and private methods are never agent operations. | Silent (S6) |
| Identity binding | `by` and `registered_by` are overwritten with the caller's name. | Identity persistence (S8) |
| Evidence rule | Evidence an agent writes is stored as `model_output`, produced by that agent. Only a world's instruments create evidence that can qualify as an External Evidence Source. | EES: "multiple LLM instances … do not constitute independent evidence" |
| Stewardship binding | A signal's steward and successor must be people or units the world registered. No model can assign an obligation to someone who never accepted it. | AP.1: "Nominal or assumed ownership does not satisfy this condition" |
| Closure authority | Set from the world's architecture, whatever the registering agent passes. A closure from outside it is recorded as attempted only. | Autonomy-Bounded Closure: "a structural property … not a judgment" |
| Obligation routing | An AUTOMATION agent cannot accept, attest, resolve a review, override or give an Emergency Justification. It can ask a person through `ask_human` for the acts its role lists. The person sees the world's own description of the effect and every open signal. | Agent Admissibility; Rule 4; Rule 1 |
| Argument shapes | Each argument is type-checked before the supervisor sees it. | Silent (S6) |
| World precheck | The world's own conditions on its effect are checked before the gate runs. | Silent, a deliberate strengthening (S11) |
| Execution latch | `World.execute` runs only from the runtime, after a permitted gate, once per decision. A failed effect is recorded as such. | Execution Gates |
| Runtime audit | Precheck holds, ungated baseline executions, effect outcomes, acts a person performed at an agent's request, schedules, and loops left open at the end of a run are all appended to the supervisor's hash-chained trail as `RUNTIME_*` entries. | Audit Trail |
| Baseline switch | `gating=False` runs the same team with the effect happening regardless of the gate. It is allowed only in the simulated world. | Why This Matters: "Refuse irreversible execution" (S12) |

## The three worlds

### `simorg`: the simulated org

Four simulated people (engineer, program manager, safety steward and launch director) decide whether to launch a vehicle. The world draws a hidden ground truth: the aft seal either fails at the forecast temperature or it doesn't. Agents see only what the instruments report: bench test, flight records and an independent review board. Each run is reported as one of:

- safe launch
- unsafe launch (vehicle lost)
- held (defect present)
- held (no defect)

The labels report the ground truth beside the gate's verdict. They do not grade the gate: the draft says CCL-F "does not predict failure", and a hold on an authority-closed loop is the gate doing what Reversibility Logic requires.

This world rests on four stipulations, which matter for how far its results transfer:

- **The agents are registered as PERSON by stipulation (S3).** They are model instances. A real deployment with the same set-up would be a stewardship void under Agent Admissibility. Results speak to how the gate behaves around a team, not to the architecture of an AI deployment.
- **Model instances are never independent of each other (S4).** No agent attests risk evidence or resolves a review. The safety steward asks the safety board, which a person answers. In unattended runs (`--compare --approve-all`) the board approves everything, so report it as a rubber stamp.
- **The review board is an oracle (S5).** It is an idealized External Evidence Source that reports the ground truth whatever it is asked. Run with and without it, otherwise results mostly measure whether agents call it.
- **The scenario is shaped like Challenger.** That makes it theory-constitutive in the draft's sense (Validation and the Selection Problem). It exercises the runtime and is not evidence for any of the framework's central claims.

### `release`: real work, governed

A developer, a reviewer and a release manager work on a git repository on a task you give them. They are registered as AUTOMATION. The maintainer (a person) accepts. If you name a second reviewer, they attest and resolve reviews.

- **Instruments.** `run_tests` hashes the working tree, exports exactly that tree to a scratch directory, and runs the tests there, so a test run cannot change the repository. For pytest the verdict comes from a JUnit report, not the exit code. The report must exist, show no failures or errors, run at least as many tests as HEAD had, and skip no more. `verify_rollback` tests the revert and tag-delete path in a scratch clone.
- **The effect.** Execution commits the tree the acceptance pinned (`git commit-tree`) and tags it. It pushes only with `--push`, and a pushed release is always gated as irreversible.
- **Protections.** The tree freezes once the release is accepted. By default the developer cannot edit tests, test configuration or test directories.
- **Tests the developer wrote.** With `--allow-test-edits`, a run on changed tests is recorded as internal analysis, never as an independent measurement, because the tests and the code share an author (S14).

> ⚠️ `run_tests` executes the code under test, which an agent wrote. The tests run in the same process as that code, so code that attacks the runner (for example by writing its own report at exit) can forge a pass. The test-runner's standing as an External Evidence Source rests on that not happening. Run this world inside a container or a throwaway VM.

### `odoo`: the invoice world

An AR clerk and a controller review draft customer invoices. Posting a batch is the irreversible step.

- **Instrument.** `read_records` covers allowlisted models and fields only, with simple domains and no dotted paths. A repeated identical read is the same evidence, not new evidence.
- **The batch.** It is fixed once proposed.
- **Dry run.** The default is a dry run, and `FakeOdoo` stands in offline. `--live` connects with `ODOO_URL`, `ODOO_DB`, `ODOO_USER` and `ODOO_API_KEY` over XML-RPC. `--post` actually posts.
- **Attestation.** Posting needs an independent attester (`--attester`), who also resolves reviews. The owner who accepts can do neither, so a solo owner's batch is held, by design.

## Running it

```bash
pip install -r requirements.txt            # includes claude-agent-sdk
python run_swarm.py simorg --script diligent --no-defect        # offline, scripted
python run_swarm.py simorg --script pressured --defect          # held
python run_swarm.py simorg --script pressured --defect --no-gate  # vehicle lost
python run_swarm.py release --demo --approve-all
python run_swarm.py odoo --attester bookkeeper --approve-all

# Claude agents (ANTHROPIC_API_KEY, Claude Code CLI on PATH); pin the model
python run_swarm.py simorg --brain claude --model claude-sonnet-5-5 --seed 3 --budget-per-turn 0.50
python run_swarm.py simorg --brain claude --model claude-sonnet-5-5 --compare --seeds 10 --approve-all
python run_swarm.py release --repo ../proj --task "fix #12" --version v0.4.1 --brain claude
```

Every run writes `swarm_run.json` with the following, and the audit chain is verified at the end:

- the report and metrics;
- the loops left open at the end;
- the models that actually answered;
- every tool call;
- every request made to a person;
- the full hash-chained audit trail.

## What the scripted baseline does and does not show

The two scripts are fixed policies. Their outcomes are fixed by construction, so treat them as checks that the supervisor enforces its rules, not as findings:

| Script | defect present, gate on | no defect, gate on | defect, gate off |
|---|---|---|---|
| pressured (closes by authority) | held | held | vehicle lost |
| diligent (closes on instrument evidence) | **vehicle lost** | safe launch | vehicle lost |

What this does show:

- **An authority-closed constraint loop holds an irreversible decision whatever the ground truth.** That is where holds with no defect come from.
- **The gate's verdict tracks how a loop was closed, not whether the vehicle is sound.** The diligent team closes on a failing bench test and cites a "launch not supported" board review. That is evidence by provenance, so the gate permits the launch, and the vehicle is lost.

The supervisor checks where evidence came from, not what it says. With Claude teams, the open question is whether agents read what their evidence says. The runtime does not check that for them.

None of this is evidence for any of the draft's central claims. The comparison varies only enforcement, the instruments are noiseless, and both arms get the same CCL-F briefing. At most it bears on the AI Applications core problem. Claims that predict on indicators, recurrence, or survivor and recovery sets need sampling designs that this world doesn't have (Validation and the Selection Problem).

## Limits to keep in view

- **Provenance, not content (S13).** See above. The release world adds one content check of its own: the release needs a passing test at the exact accepted tree.
- **One supervisor per world (S1).** All agents sit inside one organization's authority. Cross-organization autonomy is what `cclf/federation.py` models, and it isn't wired into the swarm yet.
- **Not modelled yet (S18–S20):**
  - time and execution windows (rounds are not a clock);
  - revision rigidity from agents' persistent sessions;
  - recurrence across runs (each run starts a fresh supervisor);
  - outcome scoring for Source Standing;
  - loop entanglement;
  - a channel from the safety steward to the safety board.
- **Registered channels.** Agent messaging is not registered as a tested channel, so AP.2 shows as unverified in every gate.
- **No live Claude runs yet.** Every result so far comes from the scripts.
- **The sandbox is the outer wall.** `run_tests` executes agent-written code. Run the release world in a container.
- **Emergency objects.** The inner fields of an `emergency` object are checked by the supervisor's record type, not by the runtime's shape check.

## Files

| File | Role |
|---|---|
| `cclf_swarm/runtime.py` | The guardrails, `ask_human`, messages, status, runtime audit entries and metrics |
| `cclf_swarm/brains.py` | `ClaudeBrain` (Agent SDK, built-in tools off, one session per agent, models recorded) and `ScriptedBrain` |
| `cclf_swarm/orchestrator.py` | `Swarm`, `RoundRobin`, `ClaudeOrchestrator` |
| `cclf_swarm/worlds/` | `simorg.py`, `release.py`, `odoo.py`, `base.py` |
| `cclf_swarm/scripts.py` | Baseline policies |
| `run_swarm.py` | The CLI |
| `tests/test_swarm.py` | 81 tests: guardrails, worlds, two rounds of adversarial-review regressions, and conformance tests tied to sections of the draft |

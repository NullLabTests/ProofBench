# ProofBench

**Research-grade benchmarking for long-horizon AI improvement, with
independently verifiable evidence.**

ProofBench asks one question, carefully:

> Under controlled, reproducible conditions, can an AI system improve its
> ability to solve problems through repeated inference, feedback, strategy
> revision, and bounded changes to its working methods?

Its job is to make weak claims hard to support. A candidate system cannot
touch the evaluator, the baseline, its own acceptance criteria, the seeds, or
the evidence history. Every result ships with a machine-checkable
**improvement certificate** inside a self-contained **evidence bundle** that
another researcher can verify offline — no API key, no network, no GPU.

## What ProofBench can establish

- Whether a feedback-driven adaptive method beats a fixed-policy baseline on
  **held-out instances** under a **matched evaluation budget**, with paired
  uncertainty quantification.
- Whether gains within a run reflect **persistent strategy improvement**
  (final accepted parameters vs. the candidate's own initial parameters) as
  opposed to inference-time luck or a lucky initial configuration.
- That an evidence record is **intact and internally consistent**: the
  certificate's statistics are recomputed from raw per-trial results, the
  event log hash chain is unbroken, and the baseline is byte-identical to the
  one recorded at initialization.

## What ProofBench cannot establish (non-claims)

- It is **not** evidence of AGI, recursive self-improvement, or
  general intelligence. The task families are small, deterministic,
  CPU-friendly benchmarks.
- Passing verification does **not** prove an experiment was well-designed;
  it proves the record is consistent with the declared protocol. Read the
  protocol (`docs/methodology.md`) and judge for yourself.
- Improvement on these task families does **not** imply improvement
  elsewhere. Held-out seeds guard against memorization of instances, not
  against overfitting to a task family's structure.
- SHA-256 hashes establish **identity and integrity**, not scientific
  validity.

See `docs/limitations.md` for the full non-claims list.

## Recorded results

`RESULTS.md` records actual executed runs with their certified outcomes,
including the preregistered primary experiment — whose first v0.1 result
is a **negative**: `improvement_not_demonstrated` (CI includes zero,
p = 0.93). Negative results are recorded exactly like positive ones;
every number is recomputable from the exported evidence bundle with
`proofbench verify-bundle`.

## Quick start (offline, CPU-only, no API key)

```bash
# 1. Install (Python >= 3.11)
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"        # or: uv pip install -e ".[dev]"

# 2. Diagnose the environment
.venv/bin/proofbench doctor

# 3. Validate a preregistered experiment spec (strictly)
.venv/bin/proofbench validate-experiment experiments/adaptive-vs-fixed-v1.json

# 4. Run it (deterministic, offline, CPU-only; a few minutes)
.venv/bin/proofbench run experiments/adaptive-vs-fixed-v1.json

# 5. Inspect the run
.venv/bin/proofbench inspect <RUN_ID>
.venv/bin/proofbench report <RUN_ID>

# 6. Export and independently verify the evidence bundle
.venv/bin/proofbench export <RUN_ID>
.venv/bin/proofbench verify-bundle proofbench-bundle-<RUN_ID>
```

The first run writes to `proofbench_runs/<RUN_ID>/`. Exit code `0` from
`verify-bundle` means every integrity, recomputation, and outcome check
passed.

## The CLI

| Command | Purpose |
|---|---|
| `proofbench doctor` | Environment diagnosis (offline) |
| `proofbench list-tasks` | Built-in task families + difficulty parameters |
| `proofbench validate-experiment SPEC` | Strict spec validation; rejects malformed input (exit 3) |
| `proofbench run SPEC` | Execute / resume an experiment |
| `proofbench resume RUN_ID` | Resume from the last atomic checkpoint |
| `proofbench inspect RUN_ID` | Phase, lineage, quarantine, resources, event-chain status |
| `proofbench compare A B` | Two runs' certificates side by side |
| `proofbench verify-bundle PATH` | Offline independent verification (exit 4 on failure) |
| `proofbench report RUN_ID` | Markdown report incl. negative/inconclusive outcomes |
| `proofbench export RUN_ID` | Self-contained checksummed evidence bundle |

Exit codes are a documented contract: see `docs/cli.md`.

## How an experiment works

1. A **preregistered specification** (`experiments/*.json`, strictly
   validated) fixes the hypothesis, task suite, candidate, baseline, budgets,
   seeds, action bounds, acceptance rule, and analysis procedure *before* any
   held-out evaluation.
2. The **long-horizon loop** runs the candidate on training instances, allows
   **one bounded parameter change per round** (validated against the declared
   action bounds; violations are audited and quarantined, never applied),
   evaluates the patched candidate on **validation** instances, and accepts or
   rejects per the preregistered policy. Checkpoints are atomic; runs resume.
3. The **final evaluation** runs the final candidate, the candidate's *initial*
   parameters, and the **immutable baseline** (hash-verified) on
   **held-out test instances** neither method saw.
4. The **primary outcome** is a paired comparison with a bootstrap CI and a
   sign-flip permutation test. One of three outcomes is certified:
   `improvement_demonstrated`, `improvement_not_demonstrated`, or
   `inconclusive`.

## Repository layout

```
proofbench/            the platform (spec, tasks, agents, loop, evidence, stats, CLI)
experiments/           preregistered experiment specifications
tests/                 unit + integration + property tests (offline, deterministic)
docs/                  architecture, threat model, methodology, statistics, tutorials
docs/upstream/         research notes on Apple RSI-Inference-Bench and Perplexity SPACE
```

## Model-backed agents (optional, never required)

Core experiments run fully offline. An OpenAI-compatible adapter exists for
explicitly configured use; without `PROOFBENCH_MODEL_ID`,
`PROOFBENCH_MODEL_API_BASE`, and `PROOFBENCH_MODEL_API_KEY` it refuses to run
(exit code 10). Credentials are never logged or written to evidence. See
`docs/agent-adapters.md`.

## Execution & isolation honesty

ProofBench v0.1 does **not** execute candidate-supplied code: candidates
propose bounded parameter patches, which keeps the trusted computing base
small. A `ContainerExecutor` exists for future untrusted-code experiments; on
a host without a configured container runtime it **refuses** rather than
falling back to host execution. A Python subprocess or a timeout is *not* a
security sandbox. See `docs/threat-model.md`.

## Relationship to upstream work

ProofBench was designed after studying two upstream projects; research notes
with license analysis are in `docs/upstream/`. No source code is vendored from
either project; design ideas are attributed there.

- **Apple RSI-Inference-Bench** (Apple Sample Code License): verifier/agent
  separation, paired same-session baseline measurement, correctness gates
  before improvement credit, category gates against trivial changes, guard
  conditions, and "score the final artifact" discipline.
- **Perplexity SPACE** (Apache-2.0): management/execution/output plane
  separation, explicit trust boundaries, requested-vs-observed resource
  reporting, pollable asynchronous operations, and content-addressed
  execution-environment identity.

## Development

```bash
.venv/bin/pytest                      # full offline test suite
.venv/bin/ruff check proofbench/ tests/
.venv/bin/mypy proofbench/
```

CI runs the offline suite with no network, no models, and no privileged
virtualization (`.github/workflows/ci.yml`).

## License

MIT — see `LICENSE`. This project incorporates no code from the upstream
projects above (their licenses and obligations are analyzed in
`docs/upstream/`).

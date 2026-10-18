# ProofBench recorded results

This file records **actual executed results** with their evidence bundles.
Negative and null results are recorded exactly like positive ones — that is
the point of the platform.

All runs below were executed offline on CPU with the deterministic task
families shipped in `proofbench/`. Every claim is reproducible from the
exported bundle with `proofbench verify-bundle`, which recomputes the
analysis from the raw per-seed trial records.

## v0.1 first runs (2026-10-18)

### `adaptive-vs-fixed-v1` — preregistered primary experiment

Spec: `experiments/adaptive-vs-fixed-v1.json`
(spec hash `3e104b21305105bddecbf94aaad7e1feb7a38c5e8b9fa6b1197c2aa1960d0d96`)

Preregistered hypothesis: *feedback-driven adaptive search beats a
fixed-policy baseline on held-out deterministic tasks under a matched
evaluation budget.*

| quantity | value |
| --- | --- |
| **certified outcome** | **`improvement_not_demonstrated`** |
| primary mean improvement | +0.1302 |
| 95% bootstrap CI | [-2.866, +2.966] |
| exact sign-flip p | 0.9345 (n=32 pairs) |
| strategy improvement p (candidate initial → final) | 0.5060 |
| accepted proposals | 1 (5 consecutive rounds without accept) |
| resource | 416 episodes, 2.9 CPU-s, 2.6 wall-s |

**Interpretation (honest):** on this task suite and budget, the adaptive
search agent did *not* demonstrate improvement over the fixed random
baseline. The CI comfortably includes zero and the p-value is far from
the preregistered alpha. This is a negative result for the hypothesis as
stated, and the platform reports it as such.

Bundle: `proofbench verify-bundle bundles/adaptive-vs-fixed-v1` → PASSED
(analysis recomputed from raw trials; spec hash, event chain, manifest,
baseline identity all checked).

### `negative-control-v1` — preregistered null control

Spec: `experiments/negative-control-v1.json`
(spec hash `29457aeac92210f30b66f82a0bb0bd2160b19dab88cea148c607fdfeb42fc873`)

| quantity | value |
| --- | --- |
| **certified outcome** | **`improvement_not_demonstrated`** (correct for a null control) |
| primary mean improvement | +1.5929 |
| 95% bootstrap CI | [-5.724, +9.993] |
| exact sign-flip p | 0.7422 (n=8 pairs) |
| resource | 54 episodes, 0.4 CPU-s |

**Interpretation:** the control is constructed so that no true advantage
exists; the platform correctly refuses to certify an improvement.

Bundle: `proofbench verify-bundle bundles/negative-control-v1` → PASSED.

## What these results do and do not show

* They do **not** show that adaptive search is useless in general — only
  that no improvement was demonstrated for these agents, these task
  families, these budgets, and these seeds, under the preregistered
  acceptance rule.
* They **do** show the platform exercising its full path: long-horizon loop
  with checkpoints, quarantined proposals, append-only evidence,
  content-addressed artifacts, three-way outcome, and independent bundle
  verification that recomputes every certified number.

## Reproducing

```sh
.venv/bin/proofbench run experiments/adaptive-vs-fixed-v1.json --run-id adaptive-vs-fixed-v1
.venv/bin/proofbench export proofbench_runs/adaptive-vs-fixed-v1 --out bundles/adaptive-vs-fixed-v1
.venv/bin/proofbench verify-bundle bundles/adaptive-vs-fixed-v1
```

Runs are deterministic given the spec (seeds are fixed in the spec and in
the derived run seed), so re-execution reproduces identical numbers.

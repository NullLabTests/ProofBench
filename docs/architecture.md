# Architecture

ProofBench separates **protocol definitions** (versioned, machine-readable)
from **execution code** (the runner) from **evidence** (append-only,
content-addressed). Changing scoring or task definitions requires a visible
version bump; runs record the exact protocol and task versions they used.

## Components

```
spec.py        ExperimentSpec (pydantic, strict): hypothesis, primary outcome,
               task suite, candidate, baselines, seeds, budget, action bounds,
               acceptance policy, analysis procedure, stopping conditions.
               load_spec() rejects anything malformed or semantically invalid
               (disjoint seeds, unknown versions, out-of-range values...).

tasks/         TaskFamily protocol: sample(seed, difficulty) -> instance and
               begin(instance, budget) -> Episode. Episodes expose only
               observe()/step() to agents; finalize() (the hidden score) is
               called exclusively by the independent Evaluator.
               Four built-in families: quadratic_opt, noisy_blackbox,
               allocation, transform. New families register in
               tasks/families.py FAMILIES without touching the runner.

agents.py      Agent protocol (reset/act/observe_feedback). FixedRandomSearch
               (immutable baseline), AdaptiveSearch (feedback-driven candidate
               over a bounded parameter surface), ScriptedAgent (tests).

evaluator.py   The only code allowed to call Episode.finalize(). Accounts wall
               and CPU time per episode; agent exceptions become recorded
               invalid trials, never silently dropped.

actions.py     validate_patch(): the permitted-action policy. Patches may only
               touch parameters listed in the spec's action_bounds, within
               declared ranges. Protected surfaces (evaluator, budget,
               acceptance, baseline, seeds, evidence) are always forbidden.

loop.py        The long-horizon loop: rounds of (train evaluation -> bounded
               proposal -> policy validation -> validation evaluation ->
               accept/reject/quarantine), atomic checkpoints, resumability,
               final held-out evaluation of final-candidate / initial-candidate
               / baseline, and certificate issuance.

events.py      Append-only hash-chained JSONL event log (fsync'd). Any edit,
               deletion, or reorder is detectable.

store.py       Content-addressed artifact store (sha256), atomic writes
               (tmp + fsync + rename).

stats.py       analysis.v1: paired comparisons, seeded percentile bootstrap CI,
               exact/Monte-Carlo sign-flip permutation test, paired Cohen's dz,
               Holm-Bonferroni correction, explicit missing-trial accounting,
               and synthetic-case self-tests.

bundle.py      Export a self-contained evidence bundle (MANIFEST.json with
               sha256 per file + VERIFY.md) and verify it independently:
               manifest integrity, event chain, spec identity, analysis
               recomputation from raw trials, outcome recomputation from the
               preregistered rule, baseline identity.

report.py      Markdown report for humans, negative results included.

executors.py   Pluggable execution: LocalExecutor (trusted built-ins, bounded)
               and ContainerExecutor (untrusted code; refuses without a
               configured runtime — never falls back to host execution).

model_adapter.py  Optional OpenAI-compatible adapter. Refuses without explicit
               environment configuration; records usage; never touches
               scoring or acceptance.

cli.py         doctor, list-tasks, validate-experiment, run, resume, inspect,
               compare, verify-bundle, report, export. Documented exit codes.
```

## Data flow of one run

```
spec.json (validated, hashed)
   |
   v
run_initialized event  -->  events.jsonl (hash chain, fsync per append)
   |
   +-- round 1..N: train episodes -> proposal -> validate_patch ->
   |       validation episodes -> accept|reject|quarantine ->
   |       state.json (atomic checkpoint) -> checkpoint event
   |
   +-- final: baseline hash re-verified -> test episodes for final candidate,
   |       initial candidate, and baseline -> raw results content-addressed
   |
   +-- certificate issued (artifact) -> report / export / verify
```

## Identity & integrity model

- **spec_hash** — sha256 of the canonical (sorted, compact) JSON of the
  validated spec. A run refuses to resume under a different spec hash.
- **baseline params hash** — recorded at initialization, re-verified before
  final scoring; mismatch aborts.
- **artifact addresses** — every stored object is keyed by its sha256.
- **event chain** — each event embeds the sha256 of its canonical payload and
  the previous event's chain hash.

These establish identity and integrity of the record only. They do not
establish scientific validity — see `methodology.md` and `limitations.md`.

## Versioning

- `spec.schema_version` / `protocol_version` — MAJOR.MINOR; a validator
  rejects specs whose MAJOR it does not implement.
- Task families carry their own `version`; a spec must name the exact version
  it was written against.
- `analysis_procedure` (`analysis.v1`) is stamped into every certificate; the
  verifier recomputes with the recorded procedure version.
- Protocol changes create new versions; they never retroactively change an
  existing run's outcome (the run's spec is frozen inside its bundle).

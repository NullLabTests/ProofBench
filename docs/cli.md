# CLI reference

All commands are offline and CPU-only unless explicitly documented otherwise.
Exit codes are a stable contract:

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | generic failure |
| 2 | usage error (bad flags/arguments) |
| 3 | specification validation error |
| 4 | integrity or bundle-verification failure |
| 6 | policy violation |
| 7 | budget exhausted |
| 8 | required execution backend unavailable |
| 9 | run not found |
| 10 | model adapter not configured |

## Commands

### `proofbench doctor`
Environment diagnosis: Python version, imports, runs-dir writability, free
disk, container runtime (optional). Never touches the network.

### `proofbench list-tasks`
Built-in task families with their documented difficulty parameters.

### `proofbench cite [--json]`
Citations, licenses, and upstream attribution. `--json` emits a stable
machine-readable shape. Upstream listings are ideas-only attribution; no
upstream code is redistributed by ProofBench.

### `proofbench validate-experiment SPEC`
Strictly validates a specification. Prints the experiment id and the
**spec hash** (sha256 over the canonical spec JSON). Exits 3 with a
field-naming error on any problem.

### `proofbench run SPEC [--run-id ID] [--runs-dir DIR]`
Executes the experiment. If the run directory already holds a checkpoint for
the *same* spec hash, it resumes instead of restarting (idempotent
initialization). Prints run id, certified outcome, primary statistics, and the
certificate artifact hash on completion.

### `proofbench resume RUN_ID`
Resumes an interrupted or incomplete run from `state.json`. Accepts a run id
(resolved under the runs dir) or a run directory path.

### `proofbench inspect RUN_ID`
JSON summary: phase, round, accepted params, lineage length, quarantine count,
resource accounting, event counts by kind, and whether the event hash chain
verifies.

### `proofbench compare RUN_A RUN_B`
Side-by-side certificate summary of two runs (outcome, mean improvement, CI,
p-value, spec hashes, same-protocol flag).

### `proofbench verify-bundle PATH`
Offline verification of an exported evidence bundle. Prints one PASS/FAIL line
per check; any failure exits 4 with details. See `bundle.py` for the exact
check list.

### `proofbench report RUN_ID`
Human-readable markdown report (also written into exports).

### `proofbench export RUN_ID [--out DIR]`
Writes a self-contained bundle: `MANIFEST.json` (sha256 per file),
`VERIFY.md`, `spec.json`, `events.jsonl`, `state.json`, `artifacts/`.
Refuses to write into a non-empty directory.

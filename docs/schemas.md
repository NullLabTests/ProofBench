# Protocol and evidence schemas

## Experiment specification (`spec.schema_version = "1.0"`)

Strictly validated (`proofbench/spec.py`); unknown fields are rejected.

| Field | Meaning |
|---|---|
| `experiment_id` | lowercase id, unique per experiment family |
| `protocol_id` / `protocol_version` | which protocol definition produced this spec |
| `run_seed` | master seed (optional; CLI derives one deterministically if absent) |
| `hypothesis` | the falsifiable statement (min 10 chars, stored verbatim) |
| `primary_outcome` | `{metric, direction, acceptance_margin}` — the single preregistered test |
| `tasks[]` | `{family, version, difficulty{...}}`; families validate their own difficulty keys |
| `candidate` | `{name, agent, params}` |
| `baselines[]` | same shape; the first baseline is the primary comparator |
| `seeds` | `{train_seeds, validation_seeds, test_seeds}`, pairwise disjoint |
| `budget` | `{evaluations_per_instance, max_rounds, wall_clock_seconds_per_instance?}` |
| `action_bounds[]` | the candidate's permitted modification surface: `{name, kind: float\|int\|categorical, low, high \| choices}` |
| `acceptance` | `{validation_margin, min_valid_trial_fraction, quarantine_proposals}` |
| `analysis` | `{bootstrap_resamples, bootstrap_seed, alpha, multiple_comparison}` |
| `stopping` | `{stop_if_no_accepts_for_rounds?}` |

`spec_hash` = sha256 over canonical JSON of the validated spec. A run
directory is bound to one spec hash; resume refuses to mix.

## Event log (`events.jsonl`)

One JSON object per line, append-only, fsync'd:

```json
{"seq": 12, "ts": 1760712345.67, "kind": "candidate_accepted",
 "payload": {...}, "prev": "<chain_hash of event 11>",
 "chain_hash": "sha256(prev + canonical_json(payload))"}
```

Event kinds emitted by v0.1: `run_initialized`, `run_resumed`,
`checkpoint`, `candidate_accepted`, `candidate_rejected_quarantined`,
`modification_rejected`, `policy_violation`, `budget_exhausted`,
`stopping_condition_met`, `baseline_verified`, `test_results_recorded`,
`certificate_issued`, `run_interrupted`.

## State checkpoint (`state.json`)

Written atomically after every round: phase, round counter, accepted and
initial parameters, full parameter lineage, quarantined proposals, proposer
state, learning curve, resource totals, test-results artifact reference.

## Certificate (`certificate_version = "1.0"`)

Content-addressed in the run's artifact store; includes: protocol identity,
spec hash, hypothesis, primary outcome + acceptance rule, three-way outcome
with reasons, primary and strategy analyses (n, means, CI, dz, p, pair
counts), per-family regression checks, budget and measured resources,
candidate lineage, baseline identity with params hash, test-results artifact
address, and the verification recipe (`verifier` version + recomputation
source).

## Evidence bundle

```
bundle/
  MANIFEST.json    {"bundle_format": "proofbench-evidence-bundle/1",
                    "files": {relpath: sha256}, ...}
  VERIFY.md        human verification instructions
  spec.json        {"spec": {...}, "spec_hash": "...", ...}
  events.jsonl     full hash-chained record
  state.json       final checkpoint
  artifacts/<sha256-prefix>/<sha256>   raw trials, certificate
```

`verify-bundle` re-derives everything: file hashes, the event chain, the
spec hash, the statistics (from raw per-trial records, seeded identically),
the outcome (by re-applying the recorded acceptance rule), and the baseline
hash. Mismatch anywhere → exit 4.

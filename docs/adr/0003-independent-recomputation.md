# ADR-0003: Independent recomputation as the verification core

## Status

Accepted for v0.1.

## Context

Hashes prove a record was not altered; they do not prove the numbers follow
from the record. A certificate whose statistics cannot be re-derived from the
raw trials is an article of faith, not evidence.

## Decision

`proofbench verify-bundle` re-runs the analysis pipeline on the raw
per-trial results stored in the bundle, using the recorded procedure version
and seeds, and compares field-by-field against the certificate. It also
re-applies the preregistered acceptance rule to the recomputed numbers and
checks the outcome class, the spec hash, the event hash chain, and the
baseline hash.

## Consequences

- A verifier needs only the bundle and a compatible ProofBench build — no
  network, no models, no trust in the original run's summaries.
- Any change to the analysis procedure must bump `analysis_procedure`; old
  bundles verify against their recorded procedure version.

# ProofBench — Intent

## Problem

It is currently easy to claim an AI system "improved itself" and hard to verify it.
Improvement claims routinely conflate inference-time gains (more tokens, lucky
sampling), benchmark overfitting, and genuine persistent strategy improvement.

## Desired outcome

A research-grade, offline-first, CPU-only platform that runs preregistered
long-horizon improvement experiments and produces **independently verifiable
evidence bundles** with an improvement certificate. The platform must make weak
claims hard to support: candidates cannot touch the evaluator, the baseline, the
acceptance policy, or the evidence history.

## Users

1. Researchers running improvement experiments (CLI-first, reproducible).
2. Reviewers verifying someone else's evidence bundle offline (no network, no API key).
3. Agent developers implementing new task families or candidate adapters.

## Constraints

- Linux x86-64, CPU-only, 8 cores, ~14 GiB RAM, no Docker on this host.
- No GPU, no paid API, no Kubernetes/Firecracker required for the core platform.
- Deterministic baseline suite runs offline after deps are installed.
- Model-backed experiments are explicit opt-in adapters only.
- Dependencies kept minimal: pydantic (spec validation), numpy (stats), typer (CLI).
- Never destructive to the surrounding home-directory repository.

## Success criteria (v0.1)

1. End-to-end preregistered experiment: adaptive search vs fixed-policy baseline,
   matched evaluation budget, disjoint train/validation/test instance seeds.
2. Improvement certificate with three outcomes (demonstrated / not demonstrated /
   inconclusive), independently recomputable from the evidence bundle.
3. Checkpoint/resume, append-only hash-chained event log, content-addressed artifacts.
4. Candidates restricted to bounded parameter patches; unauthorized modifications
   rejected and audited.
5. Offline CLI workflow: doctor, validate, run, resume, inspect, compare, report,
   export, verify-bundle — all functional and tested.
6. Full unit + integration test suite passing; ruff, mypy clean.
7. Honest statistical reporting including negative/inconclusive outcomes.

## Operator decision

The operator instructed immediate execution ("please go now"), so implementation
proceeds without a separate confirmation gate on this document. Design changes
that alter the scientific claims above will be recorded in `docs/adr/`.

## Status (2026-10-18): v0.1 complete

All seven success criteria met and verified by execution:

1. Preregistered experiment `experiments/adaptive-vs-fixed-v1.json` executed;
   certified outcome `improvement_not_demonstrated` (an honest negative — the
   platform is capable of negative results). Control
   `experiments/negative-control-v1.json` also correctly null.
2. Certificates carry the three-way outcome; both exported bundles pass
   `proofbench verify-bundle`, which recomputes the analysis from raw trials.
3. 8 checkpoints on the main run; hash-chained events (20 events, chain
   verifies); content-addressed artifacts throughout.
4. Bounded-patch enforcement tested, including forged-certificate and
   out-of-bounds attack paths (`tests/test_security.py`, `tests/test_property.py`).
5. Every listed CLI command is functional and tested; `cite` added for
   machine-readable upstream attribution.
6. 126 tests pass; `ruff check` and strict `mypy` clean; the exact CI steps
   pass in a clean throwaway venv (`pip install -e ".[dev]"` path via uv).
7. Results recorded in `RESULTS.md` with exact spec hashes and CIs.

Known limits: model-adapter integration is tested only offline (not-configured
behavior, usage-record hygiene); the container executor asserts refusal because
no runtime exists on the build host (by design, never a silent fallback).

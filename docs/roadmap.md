# Roadmap

## Implemented (v0.1) — verified in this repository

- Strict, versioned experiment specifications with semantic validation.
- Four deterministic task families behind a pluggable family protocol.
- Baseline suite: fixed random search, adaptive search, scripted (tests).
- Long-horizon loop: bounded proposals, policy validation, accept/reject/
  quarantine, atomic checkpoints, resume, held-out final evaluation.
- Append-only hash-chained evidence; content-addressed artifacts.
- Improvement certificates with three-way outcomes and independent
  recomputation from raw trials (`verify-bundle`).
- Honest statistics (paired bootstrap CI, sign-flip permutation test, effect
  sizes, Holm correction, missing-trial accounting, synthetic self-tests).
- CLI: doctor, list-tasks, validate-experiment, run, resume, inspect,
  compare, verify-bundle, report, export — all functional and tested.
- Preregistered experiments: the adaptive-vs-fixed comparison and a
  negative control.
- Optional OpenAI-compatible model adapter (opt-in, refuses without config).
- Container executor interface with refusal semantics (no runtime available
  in this environment; blocked tests marked as such).

## Near-term (engineering)

1. **Container-backed untrusted execution** — validate the `ContainerExecutor`
   against a real docker/podman host; add seccomp/AppArmor profiles; measure
   overhead. (Requires a host with a container runtime; tests currently
   blocked.)
2. **SPACE adapter** — an optional client for a separately deployed SPACE
   instance, written against its documented HTTP API (see
   `docs/upstream/perplexity-space.md` §6). Must remain optional and
   offline-safe.
3. **Schema migration tooling** — explicit upgraders when `spec.schema_version`
   bumps, plus a compatibility matrix.
4. **Aggregate reporting** — `proofbench aggregate BUNDLE...` for
   multi-run/meta-analysis with publication-bias-aware summaries.

## Research directions (proposals — not implemented, not claimed)

1. **Compute-scaling control experiments** — same candidate at multiple
   budgets to separate "adaptation" from "more compute".
2. **Cross-family generalization** — tune on one family, test transfer to an
   unseen family; distinguishes family-specific fitting from general search
   improvements.
3. **Memorization probes** — inject duplicate instances across splits to
   measure and bound instance memorization directly.
4. **Regression batteries** — measure whether improvement on the primary
   metric degrades performance on adjacent capability probes.
5. **Model-backed long-horizon proposals** — LLMs proposing parameter patches
   or constrained code artifacts through the same validation gate, compared
   against the deterministic proposer under matched budgets.
6. **Code-artifact improvement** — the Apple-benchmark-style "repair /
   optimize an executable artifact" track, executable only once the container
   backend exists; grade by running the artifact against withheld tests.
7. **Population-based candidates** — evolutionary strategies as candidates,
   with the acceptance policy extended to population lineages.

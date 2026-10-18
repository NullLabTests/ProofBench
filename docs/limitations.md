# Limitations and non-claims

## What ProofBench is not

- **Not evidence of AGI or recursive self-improvement.** The task families are
  small, deterministic, CPU-friendly benchmarks. A positive certificate means
  "this adaptive method beat this baseline on these held-out instances under
  this protocol" — nothing more.
- **Not a security sandbox for arbitrary code.** v0.1 executes no
  candidate-supplied code. The `ContainerExecutor` refuses without an
  explicitly configured container runtime; a subprocess with a timeout is not
  a sandbox and is never presented as one.
- **Not a leaderboard or model ranking.** It evaluates *methods* under
  *specific protocols*; results do not transfer to "model X is better".
- **Not proof of scientific validity.** Hashes and verification establish that
  the record is intact and internally consistent with the declared protocol.
  Whether the protocol was a *good test* is a judgment for human reviewers.

## Specific methodological limitations

1. **Generalization is within-family.** Test seeds are disjoint from
   train/validation seeds, so results rule out memorizing instances — but a
   parameter tuning that fits the *family's structure* will still show
   improvement. Cross-family transfer is future work.
2. **Small instance counts.** 16 held-out test instances per family in the
   shipped experiment give moderate power; wide CIs are expected and reported
   honestly. Do not over-interpret point estimates.
3. **Deterministic built-in agents only in shipped experiments.** The model
   adapter is implemented and tested at the interface level, but no
   model-backed experiment is claimed here (none was run).
4. **Seed shopping cannot be prevented.** A dishonest experimenter can run
   many seeds and publish the flattering one. ProofBench makes every run
   (including nulls) certify-able and comparable, which *enables* honest
   aggregate reporting but cannot enforce it. Mitigation: publish all runs
   and their bundles.
5. **The candidate's proposal strategy is fixed code.** The deterministic
   coordinate-search proposer is part of the controller, not modifiable by
   the candidate. This is a deliberate security/science trade-off: it bounds
   the self-modification surface to the declared parameter bounds. Richer
   proposal policies are future work behind the same validation gate.
6. **Wall-clock bounds are best-effort.** The local executor's watchdog bounds
   trusted calls; there is no hard preemption. Tasks are small enough that
   this is not currently a problem.
7. **No container-backed untrusted execution is claimed.** The executor
   interface and refusal semantics exist and are tested; an actual container
   runtime was not available in the development environment, so no container
   experiment was run. Tests covering container execution are marked
   **blocked**, never passed.
8. **The statistics assume i.i.d. seeds and symmetric errors** (see
   `statistics.md`); violations are the experimenter's responsibility to
   consider when choosing task suites.

## Resource honesty

All numbers in certificates come from measured wall/CPU accounting inside the
run (`resource` in `state.json`), not estimates. The shipped preregistered
experiment runs in minutes on a CPU-only laptop.

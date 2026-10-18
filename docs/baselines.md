# Baselines: definitions and fairness assumptions

Every shipped baseline is deterministic, independently verifiable, and
receives exactly the same evaluation opportunity as the candidate: same
instances, same per-instance budget, same feedback channel, same action space.

## `fixed_random_search`

Uniform random sampling over the declared action space, per family:

- **box** spaces (`quadratic_opt`, `noisy_blackbox`): uniform samples in the
  box; never consumes feedback.
- **subset** spaces (`allocation`): deterministic greedy on the public
  noisy value/weight ratio (the observation, not hidden values); never
  consumes step feedback.
- **op_chain** spaces (`transform`): uniformly random op chains.

Fairness assumption: for continuous box spaces with a fixed budget, uniform
random search is a strong non-adaptive reference — its expected best-of-N
improves as O(N^-1/d) and it cannot overfit to noise. A candidate that cannot
beat it under the same budget has not demonstrated useful adaptation.

## `adaptive_search` (candidate in the shipped experiments)

Feedback-driven: with probability `refine_fraction` it exploits the best point
seen so far (Gaussian local mutation scaled by `mutation_scale`, or a CEM
elite-fit when `exploit_mode=cem`); otherwise it explores uniformly. On
op_chain spaces it mutates the best-scoring chain; on subset spaces it
re-tilts the greedy allocation. Its parameter surface is exactly the
declared `action_bounds`, and it never sees hidden instance data.

Because the adaptive method's defaults are deliberately mediocre
(`refine_fraction=0.25`, `mutation_scale=0.3`), the long-horizon loop has
room to *adapt* them from validation feedback — that adaptation is the
phenomenon under test, not a rigged starting point.

## `scripted`

A canned-action agent used only in tests for determinism and for exercising
invalid-action handling.

## Anti-privilege guarantees (structural, not conventional)

- Agents receive only `Episode.observe()` output: the action space and
  declared public fields. Hidden instance payloads (quadratic matrices,
  true item values, hidden transform pairs) live in the evaluator's store.
- `Episode.finalize()` — the only path to a score — is called only by
  `Evaluator`, never by an agent.
- Noise in `noisy_blackbox` is derived deterministically from
  `(instance_seed, query_index)`, so no method can predict or replay it
  differently from another.
- The baseline's parameters are hashed at initialization and re-verified
  before final scoring.

## Compute matching

Both methods get exactly `budget.evaluations_per_instance` objective
evaluations per instance. There is no separate "thinking budget" for the
adaptive method: adaptation across rounds uses validation feedback, which is
part of the declared long-horizon protocol and is equally available to any
method (a fixed policy simply never uses it).

## What a baseline failure means

A more sophisticated method that fails to beat `fixed_random_search` is
reported as such (`improvement_not_demonstrated`), with the full statistics.
This is a feature: the platform is designed so that null results are as easy
to publish as positive ones.

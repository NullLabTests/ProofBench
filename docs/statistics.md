# Interpreting the statistics (analysis procedure `analysis.v1`)

## The primary comparison

For each method pair, per-instance scores are **paired by instance seed**.
The analysis reports:

- `n_pairs`, `n_missing_or_invalid` — invalid trials are counted and
  reported, never silently dropped. Analysis uses complete pairs.
- `mean_improvement` — mean of the paired differences in the preregistered
  direction (positive = candidate better).
- `ci_low` / `ci_high` — percentile bootstrap CI (95% by default) of the mean
  improvement, `bootstrap_resamples` resamples, seeded from
  `derive_seed(analysis.bootstrap_seed, tag)` so verification reproduces it
  exactly.
- `p_value` — two-sided paired **sign-flip permutation test**: exact over all
  2^n sign assignments when n ≤ 14, otherwise Monte Carlo with 20,000 seeded
  draws and a plus-one correction. Assumption: under the null, paired
  differences are symmetric about zero.
- `effect_size_dz` — paired Cohen's dz (mean/SD of differences); `None` when
  the variance is zero (reported explicitly, never faked).
- `improved_pairs` / `tied_pairs` / `regressed_pairs` — the direction story
  behind the mean.

## Assumptions (documented, not tested)

1. Instance seeds are independent draws from the task generator, so paired
   differences are independent across pairs.
2. Within a task suite, pairs are treated as identically distributed for the
   bootstrap. Heterogeneous task suites should be analyzed per family (the
   certificate's regression checks do exactly this).
3. The sign-flip test assumes symmetric errors; with very small n the test is
   conservative.

## Multiple comparisons

The primary outcome is a **single preregistered test** and is *not*
corrected. Exploratory secondary analyses (per-family checks, strategy
comparison) are flagged as exploratory in the certificate; when
`multiple_comparison = "holm-bonferroni"`, `stats.holm_bonferroni` provides
adjusted p-values for families of tests run together.

## Significance vs. practical significance

A certificate requires **all** of: mean improvement ≥ the preregistered
`acceptance_margin`, CI excluding zero, and p ≤ alpha. A tiny-but-significant
improvement below the practical margin is certified as
`improvement_not_demonstrated` with the numbers visible. Choose margins
before running, from task-scale reasoning, not from results.

## Three-way outcome

- `improvement_demonstrated` — all acceptance criteria met on held-out tests.
- `improvement_not_demonstrated` — enough valid data; at least one criterion
  failed. This includes "candidate was worse".
- `inconclusive` — too few valid held-out pairs
  (`n_pairs / n_total < min_valid_trial_fraction`): the evaluation itself
  failed (e.g., widespread agent crashes). Never presented as a null result.

## Self-tests

`stats.synthetic_self_test()` checks the analysis against synthetic cases
with known outcomes (consistent improvement detected; identical methods give
zero + p=1; direction flips correctly; missing pairs counted; Holm
monotonicity; dz undefined under zero variance; bootstrap reproducibility;
large-n Monte Carlo path bounded). It runs inside the unit test suite; the
CLI-independent recomputation path is exercised again by `verify-bundle`.

"""Honest statistical analysis (procedure version ``analysis.v1``).

Design commitments:

* Comparisons are **paired** by (instance seed): candidate and baseline are run
  on identical instances under identical budgets.
* Uncertainty: percentile bootstrap CI over paired differences (seeded,
  reproducible) plus an exact or sampled sign-flip permutation test.
* Effect sizes: paired Cohen's dz (undefined under zero variance → ``None``).
* Missing / failed trials are counted and reported, never silently dropped;
  analysis uses complete pairs and flags runs below the validity threshold.
* The primary outcome is evaluated once against the preregistered acceptance
  rule; secondary comparisons are exploratory and get Holm-Bonferroni
  correction when declared.

Assumptions (documented, not tested): paired differences are independent
across instance seeds; the bootstrap CI assumes pairs are identically
distributed within a task suite.  See docs/statistics.md.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Any, Literal

import numpy as np

from proofbench import ANALYSIS_PROCEDURE_VERSION

Direction = Literal["higher_is_better", "lower_is_better"]


def _improvement(cand: np.ndarray, base: np.ndarray, direction: Direction) -> np.ndarray:
    diff: np.ndarray = cand - base
    return diff if direction == "higher_is_better" else -diff


def paired_comparison(
    candidate: Sequence[float | None],
    baseline: Sequence[float | None],
    direction: Direction = "higher_is_better",
    alpha: float = 0.05,
    bootstrap_resamples: int = 5000,
    bootstrap_seed: int = 0,
) -> dict[str, Any]:
    """Paired candidate-vs-baseline comparison with uncertainty quantification."""
    if len(candidate) != len(baseline):
        raise ValueError("candidate and baseline result lists must be paired and equal length")
    n_total = len(candidate)
    pairs = [
        (c, b) for c, b in zip(candidate, baseline, strict=True) if c is not None and b is not None
    ]
    n_pairs = len(pairs)
    missing = n_total - n_pairs
    result: dict[str, Any] = {
        "analysis_procedure": ANALYSIS_PROCEDURE_VERSION,
        "direction": direction,
        "alpha": alpha,
        "n_total": n_total,
        "n_pairs": n_pairs,
        "n_missing_or_invalid": missing,
    }
    if n_pairs == 0:
        result.update({"status": "no_valid_pairs"})
        return result

    cand = np.asarray([p[0] for p in pairs], dtype=float)
    base = np.asarray([p[1] for p in pairs], dtype=float)
    imp = _improvement(cand, base, direction)
    mean_imp = float(imp.mean())
    std_imp = float(imp.std(ddof=1)) if n_pairs > 1 else 0.0

    rng = np.random.default_rng(bootstrap_seed)
    idx = rng.integers(0, n_pairs, size=(bootstrap_resamples, n_pairs))
    boot_means = imp[idx].mean(axis=1)
    lo, hi = np.percentile(boot_means, [100 * alpha / 2, 100 * (1 - alpha / 2)])

    p_value = _sign_flip_p(imp, rng)

    dz: float | None = mean_imp / std_imp if std_imp > 0.0 else None

    result.update(
        {
            "status": "ok",
            "candidate_mean": float(cand.mean()),
            "baseline_mean": float(base.mean()),
            "mean_improvement": mean_imp,
            "std_improvement": std_imp,
            "median_improvement": float(np.median(imp)),
            "ci_low": float(lo),
            "ci_high": float(hi),
            "effect_size_dz": dz,
            "effect_size_note": None if dz is not None else "undefined (zero variance)",
            "p_value": p_value,
            "improved_pairs": int((imp > 0).sum()),
            "tied_pairs": int((imp == 0).sum()),
            "regressed_pairs": int((imp < 0).sum()),
        }
    )
    return result


def _sign_flip_p(imp: np.ndarray, rng: np.random.Generator) -> float:
    """Two-sided paired sign-flip permutation test (exact when n_pairs <= 14)."""
    n = len(imp)
    observed = abs(float(imp.mean()))
    if n == 0:
        return 1.0
    if n <= 14:
        count = 0
        total = 0
        for signs in itertools.product((-1.0, 1.0), repeat=n):
            total += 1
            if abs(float((imp * np.asarray(signs)).mean())) >= observed - 1e-15:
                count += 1
        return count / total
    # Monte Carlo sign-flip for larger n
    n_perm = 20_000
    sign_matrix = rng.choice((-1.0, 1.0), size=(n_perm, n))
    means = np.abs((imp[None, :] * sign_matrix).mean(axis=1))
    count = int((means >= observed - 1e-15).sum())
    return (count + 1) / (n_perm + 1)


def holm_bonferroni(p_values: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """Holm-Bonferroni step-down correction; returns adjusted p-values + rejection."""
    m = len(p_values)
    if m == 0:
        return {"adjusted_p": [], "reject": [], "alpha": alpha, "method": "holm-bonferroni"}
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running_max = 0.0
    reject = [False] * m
    all_rejected_so_far = True
    for rank, idx in enumerate(order):
        adj = min(1.0, (m - rank) * p_values[idx])
        running_max = max(running_max, adj)
        adjusted[idx] = running_max
        if all_rejected_so_far and running_max <= alpha:
            reject[idx] = True
        else:
            all_rejected_so_far = False
    return {
        "method": "holm-bonferroni",
        "alpha": alpha,
        "adjusted_p": adjusted,
        "reject": reject,
    }


def bootstrap_mean_ci(
    values: list[float], resamples: int = 5000, seed: int = 0, alpha: float = 0.05
) -> dict[str, Any]:
    """One-sample percentile bootstrap CI (used for per-method descriptive stats)."""
    if not values:
        return {"n": 0, "mean": None, "ci_low": None, "ci_high": None}
    arr = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(resamples, len(arr)))
    means = arr[idx].mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {
        "n": len(arr),
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        "ci_low": float(lo),
        "ci_high": float(hi),
    }


def synthetic_self_test() -> list[str]:
    """Run analysis checks against synthetic cases with known outcomes.

    Returns a list of failure descriptions (empty = all checks passed).
    """
    failures: list[str] = []

    # Case 1: consistent improvement must be detected. Note: with n=6 pairs
    # the exact two-sided sign-flip test has minimum attainable p = 2/64 =
    # 0.03125, which is below alpha=0.05 (with n=5 it would be 0.0625 and
    # the test could not reject at 0.05 regardless of the effect).
    cand = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    base = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    r = paired_comparison(cand, base, "higher_is_better", bootstrap_seed=7)
    if not (r["mean_improvement"] == 1.0 and r["ci_low"] > 0 and r["p_value"] < 0.05):
        failures.append(f"case1 consistent improvement not detected: {r}")

    # Case 2: identical methods → zero improvement, CI spans 0, p = 1.
    r = paired_comparison(cand, cand, "higher_is_better", bootstrap_seed=7)
    if not (r["mean_improvement"] == 0.0 and r["ci_low"] <= 0 <= r["ci_high"]):
        failures.append(f"case2 identical methods should give zero improvement: {r}")
    if r["p_value"] != 1.0:
        failures.append(f"case2 p-value should be 1.0, got {r['p_value']}")

    # Case 3: direction handling — lower_is_better flips sign.
    r = paired_comparison([1.0, 2.0], [2.0, 3.0], "lower_is_better", bootstrap_seed=7)
    if r["mean_improvement"] != 1.0:
        failures.append(f"case3 direction handling wrong: {r}")

    # Case 4: missing pairs counted, not dropped silently.
    r = paired_comparison([1.0, None, 3.0], [0.0, 1.0, None], bootstrap_seed=7)
    if not (r["n_pairs"] == 1 and r["n_missing_or_invalid"] == 2):
        failures.append(f"case4 missing-pair accounting wrong: {r}")

    # Case 5: Holm-Bonferroni monotonicity and family-wise control.
    hb = holm_bonferroni([0.01, 0.03, 0.04])
    if hb["adjusted_p"][0] > hb["adjusted_p"][1] or hb["adjusted_p"][1] > hb["adjusted_p"][2]:
        failures.append(f"case5 holm adjusted p not monotone: {hb}")
    if not hb["reject"][0]:
        failures.append(f"case5 smallest p should be rejected: {hb}")

    # Case 6: effect size undefined under zero variance.
    r = paired_comparison([1.0, 1.0], [0.0, 0.0], bootstrap_seed=7)
    if r["effect_size_dz"] is not None:
        failures.append(f"case6 dz should be None under zero variance: {r}")

    # Case 7: bootstrap CI reproducibility for a fixed seed.
    a = paired_comparison([1.0, 2.0, 3.0], [0.5, 1.5, 2.5], bootstrap_seed=42)
    b = paired_comparison([1.0, 2.0, 3.0], [0.5, 1.5, 2.5], bootstrap_seed=42)
    if a["ci_low"] != b["ci_low"] or a["ci_high"] != b["ci_high"]:
        failures.append("case7 bootstrap CI not reproducible for fixed seed")

    # Case 8: larger n uses Monte Carlo path and stays within [0, 1].
    big_c = [float(i % 3) for i in range(40)]
    big_b = [float(i % 3) - 1.0 for i in range(40)]
    r = paired_comparison(big_c, big_b, bootstrap_seed=1)
    if not (0.0 <= r["p_value"] <= 1.0 and math.isfinite(r["mean_improvement"])):
        failures.append(f"case8 large-n path broken: {r}")

    return failures

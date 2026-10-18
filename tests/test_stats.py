"""Statistical analysis: known-outcome synthetic checks."""

from proofbench.stats import (
    bootstrap_mean_ci,
    holm_bonferroni,
    paired_comparison,
    synthetic_self_test,
)


def test_synthetic_self_test_passes() -> None:
    assert synthetic_self_test() == []


def test_holm_controls_family_wise_error() -> None:
    # Under the global null with uniform p-values, Holm should reject none.
    pvals = [0.5, 0.6, 0.7, 0.8, 0.9]
    hb = holm_bonferroni(pvals)
    assert not any(hb["reject"])


def test_holm_detects_strong_signal() -> None:
    hb = holm_bonferroni([0.0001, 0.5, 0.8])
    assert hb["reject"][0]
    assert not hb["reject"][1]


def test_bootstrap_mean_ci_sane() -> None:
    ci = bootstrap_mean_ci([1.0, 2.0, 3.0, 4.0], resamples=1000, seed=3)
    assert ci["n"] == 4
    assert ci["ci_low"] <= ci["mean"] <= ci["ci_high"]


def test_paired_comparison_rejects_length_mismatch() -> None:
    import pytest

    with pytest.raises(ValueError, match="paired"):
        paired_comparison([1.0], [1.0, 2.0])


def test_empty_comparison_is_flagged() -> None:
    r = paired_comparison([None, None], [1.0, 2.0])
    assert r["status"] == "no_valid_pairs"

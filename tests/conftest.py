"""Shared fixtures for ProofBench tests.

All fixtures are deterministic and offline.  No test may access the network,
a model API, a GPU, or a container runtime (container tests are explicitly
marked blocked when a runtime is absent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from proofbench.spec import ExperimentSpec, load_spec


def make_spec_dict(**overrides: Any) -> dict[str, Any]:
    """A small, fast, fully deterministic experiment spec for tests."""
    base: dict[str, Any] = {
        "schema_version": "1.0",
        "experiment_id": "test-experiment",
        "protocol_id": "proofbench-adaptive-improvement",
        "protocol_version": "1.0",
        "run_seed": 99,
        "hypothesis": (
            "An adaptive search policy improves held-out performance over a "
            "fixed random policy under a matched evaluation budget."
        ),
        "primary_outcome": {
            "metric": "mean_score",
            "direction": "higher_is_better",
            "acceptance_margin": 0.5,
        },
        "tasks": [
            {
                "family": "noisy_blackbox",
                "version": "1",
                "difficulty": {"dim": 2, "noise_sigma": 1.0, "modality": 5.0},
            }
        ],
        "candidate": {
            "name": "adaptive",
            "agent": "adaptive_search",
            "params": {
                "refine_fraction": 0.3,
                "mutation_scale": 0.2,
                "elite_fraction": 0.2,
                "exploit_mode": "local_refine",
            },
        },
        "baselines": [{"name": "fixed", "agent": "fixed_random_search", "params": {}}],
        "seeds": {
            "train_seeds": [1, 2, 3],
            "validation_seeds": [50, 51],
            "test_seeds": [500, 501, 502, 503],
        },
        "budget": {"evaluations_per_instance": 30, "max_rounds": 2},
        "action_bounds": [
            {"name": "refine_fraction", "kind": "float", "low": 0.0, "high": 1.0},
            {"name": "mutation_scale", "kind": "float", "low": 0.001, "high": 1.0},
            {
                "name": "exploit_mode",
                "kind": "categorical",
                "choices": ["none", "local_refine", "cem"],
            },
        ],
        "acceptance": {
            "validation_margin": 0.0,
            "min_valid_trial_fraction": 0.5,
            "quarantine_proposals": True,
        },
        "analysis": {
            "bootstrap_resamples": 500,
            "bootstrap_seed": 11,
            "alpha": 0.05,
            "multiple_comparison": "holm-bonferroni",
        },
        "stopping": {"stop_if_no_accepts_for_rounds": None},
    }
    base.update(overrides)
    return base


@pytest.fixture()
def spec() -> ExperimentSpec:
    return load_spec(make_spec_dict())


@pytest.fixture()
def tiny_spec() -> ExperimentSpec:
    """Even smaller spec for fast end-to-end runs."""
    return load_spec(
        make_spec_dict(
            budget={"evaluations_per_instance": 15, "max_rounds": 1},
            analysis={
                "bootstrap_resamples": 300,
                "bootstrap_seed": 5,
                "alpha": 0.05,
                "multiple_comparison": "holm-bonferroni",
            },
        )
    )


@pytest.fixture()
def spec_file(tmp_path: Path) -> Path:
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(make_spec_dict()), encoding="utf-8")
    return p

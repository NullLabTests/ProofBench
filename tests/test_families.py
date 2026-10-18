"""Task families: determinism, budget enforcement, and information hiding."""

import pytest

from proofbench.tasks.base import InvalidAction
from proofbench.tasks.families import FAMILIES, apply_ops

ALL_FAMILIES = sorted(FAMILIES.values(), key=lambda f: f.name)


@pytest.mark.parametrize("fam", ALL_FAMILIES, ids=lambda f: f.name)
def test_instances_are_deterministic(fam) -> None:  # type: ignore[no-untyped-def]
    a = fam.sample(7, {"dim": 2} if fam.name != "allocation" else {"n_items": 6})
    b = fam.sample(7, {"dim": 2} if fam.name != "allocation" else {"n_items": 6})
    assert a == b


@pytest.mark.parametrize("fam", ALL_FAMILIES, ids=lambda f: f.name)
def test_different_seeds_different_instances(fam) -> None:  # type: ignore[no-untyped-def]
    diff = {"dim": 2, "n_items": 6, "noise_sigma": 1.0}
    a = fam.sample(1, diff)
    b = fam.sample(2, diff)
    assert a != b or fam.name == "transform"


@pytest.mark.parametrize("fam", ALL_FAMILIES, ids=lambda f: f.name)
def test_observe_leaks_no_hidden_data(fam) -> None:  # type: ignore[no-untyped-def]
    diff = {"dim": 2, "n_items": 6, "noise_sigma": 1.0}
    instance = fam.sample(3, diff)
    obs = fam.begin(instance, budget=5).observe()
    obs_str = str(obs)
    # Hidden payload values must never appear in the public observation.
    hidden = instance["hidden"]
    if fam.name == "quadratic_opt":
        # observed=True publishes the quadratic deliberately (algorithm
        # selection variant); check the unobserved variant instead.
        unobserved = fam.sample(4, {"dim": 2, "observed": False})
        unobserved_obs = str(fam.begin(unobserved, budget=5).observe())
        center = unobserved["hidden"]["center"][0]
        assert f"{center:.10f}" not in unobserved_obs
        assert "quadratic" not in unobserved_obs
    elif fam.name == "allocation":
        assert "true_value_feedback_delayed_only" not in obs_str
        assert str(round(hidden["values"][0], 10)) not in obs_str
    elif fam.name == "transform":
        pairs = hidden["pairs"]
        # No hidden pair input may appear among the public examples.
        public_inputs = {ex["input"] for ex in obs["examples"]}
        hidden_inputs = {p[0] for p in pairs[len(obs["examples"]) :]}
        assert public_inputs.isdisjoint(hidden_inputs)


@pytest.mark.parametrize("fam", ALL_FAMILIES, ids=lambda f: f.name)
def test_budget_is_hard_enforced(fam) -> None:  # type: ignore[no-untyped-def]
    diff = {"dim": 2, "n_items": 6, "noise_sigma": 1.0}
    instance = fam.sample(5, diff)
    episode = fam.begin(instance, budget=3)
    for _ in range(3):
        episode.step(_valid_action(fam, instance))
    with pytest.raises(InvalidAction, match="budget exhausted"):
        episode.step(_valid_action(fam, instance))


@pytest.mark.parametrize("fam", ALL_FAMILIES, ids=lambda f: f.name)
def test_invalid_actions_consume_budget(fam) -> None:  # type: ignore[no-untyped-def]
    diff = {"dim": 2, "n_items": 6, "noise_sigma": 1.0}
    instance = fam.sample(6, diff)
    episode = fam.begin(instance, budget=2)
    fb = episode.step({"garbage": True})
    assert fb.get("valid") is False
    assert episode.steps == 1  # the malformed action still consumed budget


def _valid_action(fam, instance: dict) -> dict:  # type: ignore[no-untyped-def]
    if fam.name in ("quadratic_opt", "noisy_blackbox"):
        return {"x": [0.1] * instance["difficulty"]["dim"]}
    if fam.name == "allocation":
        return {"mask": [1] + [0] * (instance["difficulty"]["n_items"] - 1)}
    return {"ops": ["upper"]}


def test_quadratic_oracle_and_score() -> None:
    fam = FAMILIES["quadratic_opt"]
    instance = fam.sample(10, {"dim": 3, "condition_number": 5.0, "observed": True})
    episode = fam.begin(instance, budget=10)
    # At the true center the loss (and thus negative loss) is ~0.
    center = instance["hidden"]["center"]
    episode.step({"x": center})
    assert abs(episode.finalize()) < 1e-9
    # A far point scores worse.
    episode2 = fam.begin(instance, budget=10)
    episode2.step({"x": [2.0] * 3})
    assert episode2.finalize() < 0.0


def test_noisy_feedback_is_deterministic_per_query() -> None:
    fam = FAMILIES["noisy_blackbox"]
    instance = fam.sample(11, {"dim": 2, "noise_sigma": 3.0, "modality": 5.0})
    e1 = fam.begin(instance, budget=5)
    e2 = fam.begin(instance, budget=5)
    f1 = e1.step({"x": [0.5, 0.5]})
    f2 = e2.step({"x": [0.5, 0.5]})
    assert f1["feedback_value"] == f2["feedback_value"]  # same query index -> same noise
    # A different query index gives a different noise draw.
    f1b = e1.step({"x": [0.5, 0.5]})
    assert f1b["feedback_value"] != f1["feedback_value"]


def test_allocation_respects_capacity() -> None:
    fam = FAMILIES["allocation"]
    instance = fam.sample(12, {"n_items": 8, "capacity_fraction": 0.3, "noise_sigma": 1.0})
    episode = fam.begin(instance, budget=5)
    overfull = {"mask": [1] * 8}
    fb = episode.step(overfull)
    capacity = instance["hidden"]["capacity"]
    if fb["total_weight"] > capacity:
        assert fb["feasible"] is False
        # An infeasible submission never sets the score.
        assert episode.finalize() == 0.0


def test_allocation_delayed_feedback_hides_value() -> None:
    fam = FAMILIES["allocation"]
    instance = fam.sample(
        13,
        {"n_items": 6, "capacity_fraction": 0.5, "noise_sigma": 1.0, "feedback": "delayed"},
    )
    episode = fam.begin(instance, budget=3)
    obs = episode.observe()
    assert obs["true_value_feedback"] is False
    fb = episode.step({"mask": [1, 1, 0, 0, 0, 0]})
    assert "total_value" not in fb


def test_transform_ops() -> None:
    assert apply_ops("hello world", ["upper"]) == "HELLO WORLD"
    assert apply_ops("abc", ["reverse"]) == "cba"
    assert apply_ops("a-b", ["replace:-:_"]) == "a_b"
    assert apply_ops("hello", ["strip_vowels", "upper"]) == "HLL"


def test_transform_hidden_score_needs_generalization() -> None:
    fam = FAMILIES["transform"]
    instance = fam.sample(14, {"n_public": 3, "n_hidden": 6, "max_chain": 2})
    chain = instance["hidden"]["chain"]
    episode = fam.begin(instance, budget=5)
    episode.observe()
    fb = episode.step({"ops": list(chain)})  # the true chain
    assert fb["public_passed"] == 3
    assert episode.finalize() == 100.0


def test_transform_wrong_chain_scores_below_full() -> None:
    fam = FAMILIES["transform"]
    instance = fam.sample(15, {"n_public": 3, "n_hidden": 6, "max_chain": 1})
    episode = fam.begin(instance, budget=5)
    episode.observe()
    episode.step({"ops": ["upper"]})  # likely wrong
    assert episode.finalize() < 100.0


def test_unknown_family_rejected_at_registry() -> None:
    assert "does_not_exist" not in FAMILIES

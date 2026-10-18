"""Agents and the independent evaluator."""

import numpy as np

from proofbench.agents import AdaptiveSearch, FixedRandomSearch, ScriptedAgent
from proofbench.evaluator import Evaluator
from proofbench.tasks.families import FAMILIES


def _episode_seeds(seed: int = 42):  # type: ignore[no-untyped-def]
    fam = FAMILIES["quadratic_opt"]
    instance = fam.sample(seed, {"dim": 3, "condition_number": 10.0, "observed": True})
    return fam, instance


def test_fixed_random_search_is_deterministic_given_seed() -> None:
    fam, instance = _episode_seeds()
    scores = []
    for _ in range(2):
        agent = FixedRandomSearch({})
        result = Evaluator().run_episode(
            fam, instance, agent, budget=20, rng_seed=7, instance_id="i"
        )
        scores.append(result.score)
    assert scores[0] == scores[1]


def test_fixed_random_search_never_consumes_feedback() -> None:
    agent = FixedRandomSearch({})
    fam, instance = _episode_seeds()
    Evaluator().run_episode(fam, instance, agent, budget=15, rng_seed=3, instance_id="i")
    for _action, feedback in agent.history:
        # The policy ignores feedback; history is still recorded for audit.
        assert isinstance(feedback, dict)


def test_adaptive_beats_random_on_observed_quadratic() -> None:
    # Sanity check of the intended contrast under a matched budget. This is a
    # pipeline sanity test, not a scientific claim: it uses the observed
    # quadratic family where local refinement has a clear advantage.
    fam, instance = _episode_seeds(seed=99)
    fixed = Evaluator().run_episode(
        fam, instance, FixedRandomSearch({}), budget=60, rng_seed=5, instance_id="i"
    )
    adaptive = Evaluator().run_episode(
        fam,
        instance,
        AdaptiveSearch({"refine_fraction": 0.6, "mutation_scale": 0.15}),
        budget=60,
        rng_seed=5,
        instance_id="i",
    )
    assert adaptive.score > fixed.score


def test_agent_failure_is_recorded_not_hidden() -> None:
    agent = ScriptedAgent({"actions": [{"x": [0.0, 0.0]}]})  # runs out of actions
    fam, instance = _episode_seeds()
    result = Evaluator().run_episode(fam, instance, agent, budget=10, rng_seed=1, instance_id="i")
    assert result.valid is False
    assert result.error is not None and "exhausted" in result.error


def test_evaluator_accounts_resources() -> None:
    fam, instance = _episode_seeds()
    result = Evaluator().run_episode(
        fam, instance, FixedRandomSearch({}), budget=10, rng_seed=1, instance_id="i"
    )
    assert result.wall_seconds >= 0.0
    assert result.cpu_seconds >= 0.0
    assert result.steps_used == 10


def test_adaptive_is_deterministic_given_seed() -> None:
    fam, instance = _episode_seeds(seed=5)
    scores = []
    for _ in range(2):
        agent = AdaptiveSearch({"refine_fraction": 0.5, "mutation_scale": 0.2})
        result = Evaluator().run_episode(
            fam, instance, agent, budget=25, rng_seed=11, instance_id="i"
        )
        scores.append(result.score)
    assert scores[0] == scores[1]
    assert np.isfinite(scores[0])

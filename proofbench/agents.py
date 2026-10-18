"""Agent protocol and the deterministic agent suite.

Agents act only inside an episode's declared action space and receive only the
feedback the task family exposes.  They never see hidden instance data, never
see the evaluator, and never compute their own authoritative scores.

Determinism: every agent is seeded per episode by the runner with a seed
derived from (run seed, method name, instance id), so runs replay exactly.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import numpy as np

from proofbench.tasks.base import Action, Feedback, InvalidAction

Params = dict[str, Any]


class Agent(ABC):
    """A search/decision policy for one episode."""

    agent_type: str = "abstract"

    def __init__(self, params: Params | None = None) -> None:
        self.params: Params = dict(params or {})

    def reset(self, observation: dict[str, Any], rng_seed: int) -> None:
        """Bind to one episode. ``observation`` is the family's public view."""
        self.observation = observation
        self.rng = np.random.default_rng(rng_seed)
        self.history: list[tuple[Action, Feedback]] = []

    @abstractmethod
    def act(self) -> Action:
        """Choose the next action given accumulated feedback history."""

    def observe_feedback(self, action: Action, feedback: Feedback) -> None:
        self.history.append((action, feedback))


class FixedRandomSearch(Agent):
    """Uniform random search over the declared action space.

    This is the immutable baseline: it never adapts, never uses feedback, and
    its parameter set is fixed in the experiment specification.
    """

    agent_type = "fixed_random_search"

    def act(self) -> Action:
        space = self.observation["action_space"]
        kind = space["kind"]
        if kind == "box":
            low = np.asarray(space["low"], dtype=float)
            high = np.asarray(space["high"], dtype=float)
            return {"x": [float(v) for v in self.rng.uniform(low, high)]}
        if kind == "subset":
            # Greedy on the public value/weight ratio is still "fixed": the
            # policy is deterministic given the observation, with a fixed
            # tie-break noise level of zero, and never consumes feedback.
            weights = np.asarray(space["weights"], dtype=float)
            estimates = np.asarray(space["value_estimates"], dtype=float)
            capacity = float(space["capacity"])
            ratio = estimates / np.maximum(weights, 1e-9)
            order = np.argsort(-ratio)
            mask = np.zeros_like(weights)
            used = 0.0
            for i in order:
                if used + weights[i] <= capacity:
                    mask[i] = 1.0
                    used += weights[i]
            return {"mask": [int(v) for v in mask]}
        if kind == "op_chain":
            vocab = list(space["vocabulary"])
            max_len = int(space["max_len"])
            length = int(self.rng.integers(1, max_len + 1))
            return {"ops": [str(self.rng.choice(vocab)) for _ in range(length)]}
        raise InvalidAction(f"fixed_random_search cannot act in space {kind!r}")


class AdaptiveSearch(Agent):
    """Feedback-driven adaptive search (the preregistered candidate).

    Parameter surface (bounded by the experiment's ``action_bounds``):

    * ``refine_fraction`` in [0, 1] — probability of exploiting the best point
      seen so far instead of exploring uniformly.
    * ``mutation_scale`` in (0, 1] — Gaussian step size around the best point,
      relative to box width.
    * ``elite_fraction`` in (0, 1] — elite set size for CEM-style sampling.
    * ``exploit_mode`` — ``local_refine``, ``cem``, or ``none``.

    On ``op_chain`` spaces, exploitation re-samples around the best-scoring
    chain seen so far (single-op mutations).  On ``subset`` spaces, exploitation
    flips the lowest-value/weight-ratio items in the current best feasible mask.

    The policy is fully determined by (params, observation, feedback history,
    rng seed): no hidden information, no evaluator access.
    """

    agent_type = "adaptive_search"

    DEFAULTS: ClassVar[Params] = {
        "refine_fraction": 0.5,
        "mutation_scale": 0.1,
        "elite_fraction": 0.2,
        "exploit_mode": "local_refine",
    }

    def __init__(self, params: Params | None = None) -> None:
        merged = {**self.DEFAULTS, **(params or {})}
        super().__init__(merged)
        self._best_action: Action | None = None
        self._best_value = -math.inf
        self._best_public = -math.inf

    def reset(self, observation: dict[str, Any], rng_seed: int) -> None:
        super().reset(observation, rng_seed)
        self._best_action = None
        self._best_value = -math.inf

    def observe_feedback(self, action: Action, feedback: Feedback) -> None:
        # Track the best point seen so far from *public feedback only*; this is
        # what makes the policy genuinely feedback-driven.
        self._track(action, feedback)
        super().observe_feedback(action, feedback)

    # -- helpers ------------------------------------------------------------

    def _p(self, name: str) -> Any:
        return self.params[name]

    def _track(self, action: Action, feedback: Feedback) -> None:
        # Pick a scalar "quality" signal available in the public feedback only.
        for key in ("feedback_value", "total_value", "public_passed"):
            if key in feedback:
                val = float(feedback[key])
                if val > self._best_value:
                    self._best_value = val
                    self._best_action = action
                return
        if feedback.get("feasible") is True and (
            self._best_action is None or self._best_value == -math.inf
        ):
            # allocation + delayed feedback: keep the last feasible mask as an
            # anchor; no value signal is available.
            self._best_action = action
            self._best_value = 0.0

    # -- policy -------------------------------------------------------------

    def act(self) -> Action:
        space = self.observation["action_space"]
        kind = space["kind"]
        mode = str(self._p("exploit_mode"))
        explore = (
            mode == "none"
            or self._best_action is None
            or self.rng.random() >= float(self._p("refine_fraction"))
        )
        if kind == "box":
            return self._act_box(space, explore)
        if kind == "op_chain":
            return self._act_chain(space, explore)
        if kind == "subset":
            return self._act_subset(space, explore)
        raise InvalidAction(f"adaptive_search cannot act in space {kind!r}")

    def _act_box(self, space: dict[str, Any], explore: bool) -> Action:
        low = np.asarray(space["low"], dtype=float)
        high = np.asarray(space["high"], dtype=float)
        width = high - low
        if explore:
            return {"x": [float(v) for v in self.rng.uniform(low, high)]}
        mode = str(self._p("exploit_mode"))
        if mode == "local_refine":
            if self._best_action is None:  # unreachable when explore=False, but guarded
                raise InvalidAction("adaptive_search has no accepted point to refine yet")
            best = np.asarray(self._best_action["x"], dtype=float)
            step = float(self._p("mutation_scale")) * width
            x = best + self.rng.normal(0.0, 1.0, best.shape) * step
            return {"x": [float(v) for v in np.clip(x, low, high)]}
        if mode == "cem":
            # Sample from a Gaussian fit to elite points seen so far.
            pts = [
                np.asarray(a["x"], dtype=float)
                for a, fb in self.history
                if "x" in a and fb.get("valid", False)
            ]
            vals = [
                float(fb["feedback_value"])
                for a, fb in self.history
                if "x" in a and fb.get("valid", False)
            ]
            if len(pts) < 2:
                return {"x": [float(v) for v in self.rng.uniform(low, high)]}
            k = max(2, math.ceil(float(self._p("elite_fraction")) * len(pts)))
            elite_idx = np.argsort(vals)[-k:]
            elite = np.stack([pts[i] for i in elite_idx])
            mean = elite.mean(axis=0)
            std = elite.std(axis=0) + 1e-9
            x = self.rng.normal(mean, std)
            return {"x": [float(v) for v in np.clip(x, low, high)]}
        # mode == "none" behaves as uniform exploration
        return {"x": [float(v) for v in self.rng.uniform(low, high)]}

    def _act_chain(self, space: dict[str, Any], explore: bool) -> Action:
        vocab = list(space["vocabulary"])
        max_len = int(space["max_len"])
        if explore or self._best_action is None:
            length = int(self.rng.integers(1, max_len + 1))
            return {"ops": [str(self.rng.choice(vocab)) for _ in range(length)]}
        chain = list(self._best_action.get("ops", []))
        if not chain:
            chain = [str(self.rng.choice(vocab))]
        pos = int(self.rng.integers(0, len(chain)))
        choice = self.rng.random()
        if choice < 0.6 or len(chain) >= max_len:
            chain[pos] = str(self.rng.choice(vocab))
        elif choice < 0.8 and len(chain) > 1:
            chain.pop(pos)
        else:
            chain.insert(pos, str(self.rng.choice(vocab)))
        return {"ops": chain}

    def _act_subset(self, space: dict[str, Any], explore: bool) -> Action:
        weights = np.asarray(space["weights"], dtype=float)
        estimates = np.asarray(space["value_estimates"], dtype=float)
        capacity = float(space["capacity"])
        if explore or self._best_action is None:
            # Exploratory action: randomized greedy on noisy estimates with a
            # random ratio tilt, so exploration actually differs per step.
            tilt = self.rng.uniform(0.5, 1.5)
            ratio = (estimates * tilt) / np.maximum(weights, 1e-9)
            order = np.argsort(-ratio)
        else:
            order = np.argsort(-(estimates / np.maximum(weights, 1e-9)))
        mask = np.zeros_like(weights)
        used = 0.0
        for i in order:
            if used + weights[i] <= capacity:
                mask[i] = 1.0
                used += weights[i]
        return {"mask": [int(v) for v in mask]}


class ScriptedAgent(Agent):
    """Deterministic canned-action agent for tests."""

    agent_type = "scripted"

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self._i = 0

    def act(self) -> Action:
        actions: list[Action] = self.params.get("actions", [])
        if self._i >= len(actions):
            raise InvalidAction("scripted agent exhausted its action list")
        action: Action = actions[self._i]
        self._i += 1
        return action


AGENTS: dict[str, type[Agent]] = {
    a.agent_type: a for a in (FixedRandomSearch, AdaptiveSearch, ScriptedAgent)
}

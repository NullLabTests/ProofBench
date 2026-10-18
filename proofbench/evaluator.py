"""Independent evaluator and budget accounting.

The evaluator is the only component allowed to call ``Episode.finalize()``.
Agents receive feedback through ``Episode.step()`` and nothing else.  The
evaluator records wall-clock and CPU time per episode and enforces the
declared per-instance step budget.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from proofbench.agents import Agent
from proofbench.tasks.base import Episode, TaskFamily


@dataclass
class EpisodeResult:
    instance_id: str
    family: str
    score: float  # hidden score, higher is better
    steps_used: int
    budget: int
    invalid_actions: int
    wall_seconds: float
    cpu_seconds: float
    error: str | None = None
    valid: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


class Evaluator:
    """Runs one agent on one instance inside a bounded episode."""

    def run_episode(
        self,
        family: TaskFamily,
        instance: dict[str, Any],
        agent: Agent,
        budget: int,
        rng_seed: int,
        instance_id: str,
    ) -> EpisodeResult:
        episode: Episode = family.begin(instance, budget)
        agent.reset(episode.observe(), rng_seed)
        invalid = 0
        error: str | None = None
        wall0, cpu0 = time.perf_counter(), time.process_time()
        try:
            while episode.steps < budget:
                action = agent.act()
                feedback = episode.step(action)
                agent.observe_feedback(action, feedback)
                if not feedback.get("valid", True):
                    invalid += 1
                    if "budget exhausted" in str(feedback.get("error", "")):
                        break
        except Exception as exc:  # agent-side failure: recorded, never hidden
            error = f"{type(exc).__name__}: {exc}"
        wall = time.perf_counter() - wall0
        cpu = time.process_time() - cpu0
        try:
            score = float(episode.finalize())
        except Exception as exc:  # evaluator-side failure on finalize
            return EpisodeResult(
                instance_id=instance_id,
                family=family.name,
                score=float("-inf"),
                steps_used=episode.steps,
                budget=budget,
                invalid_actions=invalid,
                wall_seconds=wall,
                cpu_seconds=cpu,
                error=f"finalize failed: {type(exc).__name__}: {exc}",
                valid=False,
            )
        valid = error is None
        return EpisodeResult(
            instance_id=instance_id,
            family=family.name,
            score=score,
            steps_used=episode.steps,
            budget=budget,
            invalid_actions=invalid,
            wall_seconds=wall,
            cpu_seconds=cpu,
            error=error,
            valid=valid,
        )

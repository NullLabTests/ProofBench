"""Task environment protocol.

A task family produces deterministic instances from a seed and exposes an
*episode* interface: the agent submits actions and receives only declared
feedback; the hidden evaluation is computed by :meth:`Episode.finalize`, which
is called exclusively by the independent evaluator, never by the agent.

Scores are always **higher is better** inside ProofBench.  Metrics that are
naturally "lower is better" (e.g. regret) declare their direction in the
experiment specification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

Difficulty = dict[str, Any]
Action = dict[str, Any]
Feedback = dict[str, Any]


class InvalidAction(Exception):
    """Agent submitted a malformed or out-of-space action."""


class Episode(ABC):
    """One bounded agent episode on one instance."""

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.steps = 0

    @abstractmethod
    def observe(self) -> dict[str, Any]:
        """Initial public observation (action space + task info). No hidden data."""

    @abstractmethod
    def step(self, action: Action) -> Feedback:
        """Apply one action, consume one unit of budget, return declared feedback."""

    @abstractmethod
    def finalize(self) -> float:
        """Hidden score for this episode. Evaluator-only entry point."""


class TaskFamily(ABC):
    """A registry of deterministic instances with explicit I/O contracts."""

    name: str = "abstract"
    version: str = "1"
    #: families whose score may be compared under the adaptive-improvement loop
    supports_search_agents: bool = True

    @abstractmethod
    def sample(self, seed: int, difficulty: Difficulty) -> dict[str, Any]:
        """Deterministically build an instance. The full instance (incl. hidden
        data) is kept in the evaluator's store; agents never receive it."""

    @abstractmethod
    def begin(self, instance: dict[str, Any], budget: int) -> Episode:
        """Start an episode. ``budget`` bounds the number of steps."""

    def difficulty_keys(self) -> list[str]:
        """Documented difficulty parameter names, for ``list-tasks``."""
        return []

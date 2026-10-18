# Tutorial: adding a task family

Task families plug into the registry without touching the runner, evaluator,
loop, or CLI.

## 1. Implement the protocol

Create a class deriving `proofbench.tasks.base.TaskFamily` with a unique
`name` and a `version`. Two methods:

```python
from proofbench.tasks.base import Episode, TaskFamily, InvalidAction

class MyEpisode(Episode):
    def __init__(self, budget: int, hidden: dict) -> None:
        super().__init__(budget)
        self._hidden = hidden          # never exposed to agents
        self.best = float("-inf")

    def observe(self) -> dict:
        # ONLY public information + the action space descriptor.
        return {"action_space": {"kind": "box", "dim": 2,
                                 "low": [0.0, 0.0], "high": [1.0, 1.0]}}

    def step(self, action):
        if self.steps >= self.budget:
            raise InvalidAction("episode budget exhausted")
        self.steps += 1
        x = action.get("x")
        if not isinstance(x, (list, tuple)) or len(x) != 2:
            return {"valid": False, "error": "need x of length 2"}
        score = self._hidden_score(x)          # evaluator-side computation
        self.best = max(self.best, score)
        return {"valid": True, "feedback_value": score}  # declared feedback only

    def finalize(self) -> float:
        # Called ONLY by the Evaluator. Return the hidden score.
        return self.best

class MyFamily(TaskFamily):
    name = "my_family"
    version = "1"

    def difficulty_keys(self) -> list[str]:
        return ["scale"]

    def sample(self, seed: int, difficulty: dict) -> dict:
        # Fully deterministic given (seed, difficulty).
        return {"family": self.name, "version": self.version, "seed": seed,
                "difficulty": dict(difficulty), "hidden": {...},
                "oracle_score": None}

    def begin(self, instance: dict, budget: int) -> Episode:
        return MyEpisode(budget, instance["hidden"])
```

Register it in `proofbench/tasks/families.py`:

```python
FAMILIES: dict[str, TaskFamily] = {
    f.name: f for f in (QuadraticOpt(), NoisyBlackbox(), Allocation(),
                        Transform(), MyFamily())
}
```

Add its difficulty keys to `_DIFF_KEYS` so `list-tasks` documents them.

## 2. Rules that keep the science honest

- **Determinism**: `sample()` and `finalize()` must be pure functions of
  (seed, difficulty, action sequence). Use `numpy.random.default_rng(seed)`;
  never module-level RNG or wall-clock time.
- **No leakage**: anything an agent may see goes in `observe()` or in step
  *feedback*. Hidden data stays in the instance dict, which the runner never
  hands to agents.
- **Budget honesty**: `step()` must charge one budget unit per call,
  including invalid actions. Never grant free retries.
- **Action-space descriptors**: declare `kind` so built-in agents can act:
  `box` (continuous, `low`/`high` lists), `subset` (0/1 mask over `weights`
  with `capacity` and `value_estimates`), `op_chain` (`vocabulary`,
  `max_len`). New kinds need new agent support.
- **Versioning**: changing scoring semantics = new `version`; specs pin the
  exact version.

## 3. Add a test

Copy the pattern in `tests/test_families.py`: determinism (same seed →
identical instance), budget enforcement, invalid-action handling, and a
no-leakage assertion that `observe()` output contains no hidden keys.

## 4. Reference it from a spec

```json
{"tasks": [{"family": "my_family", "version": "1", "difficulty": {"scale": 1.0}}]}
```

`proofbench validate-experiment` will reject unknown families, version
mismatches, and out-of-range difficulty values before any evaluation runs.

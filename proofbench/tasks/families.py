"""Built-in deterministic task families.

Four families, all CPU-only and deterministic given (instance seed, action
sequence):

* ``quadratic_opt``   — algorithm selection & optimization (observed or black-box
  convex quadratic minimization over a box).
* ``noisy_blackbox``  — noisy multimodal black-box optimization; repeated
  queries at the same point return independent, reproducible noise draws, so a
  feedback-using strategy can average while a fixed strategy cannot.
* ``allocation``      — resource allocation under a knapsack constraint with
  noisy value estimates and full or delayed true-value feedback.
* ``transform``       — small program-transformation task: infer a declarative
  op chain from public I/O examples; scored on held-out pairs.  Actions are
  constrained JSON (never executed code).

Difficulty parameters are documented in :meth:`TaskFamily.difficulty_keys` and
validated at instance sampling time.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from proofbench.tasks.base import Action, Difficulty, Episode, Feedback, InvalidAction, TaskFamily

# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

_DIFF_KEYS: dict[str, list[str]] = {
    "quadratic_opt": ["dim", "condition_number", "observed"],
    "noisy_blackbox": ["dim", "noise_sigma", "modality"],
    "allocation": ["n_items", "capacity_fraction", "noise_sigma", "feedback"],
    "transform": ["n_public", "n_hidden", "max_chain"],
}


def _as_int(difficulty: Difficulty, key: str, default: int, lo: int, hi: int) -> int:
    val = int(difficulty.get(key, default))
    if not lo <= val <= hi:
        raise ValueError(f"difficulty {key}={val} outside [{lo}, {hi}]")
    return val


def _as_float(difficulty: Difficulty, key: str, default: float, lo: float, hi: float) -> float:
    val = float(difficulty.get(key, default))
    if not lo <= val <= hi:
        raise ValueError(f"difficulty {key}={val} outside [{lo}, {hi}]")
    return val


class _BoxSearchEpisode(Episode):
    """Shared machinery for continuous box-space search episodes."""

    kind = "box"

    def __init__(self, budget: int, dim: int, low: float, high: float) -> None:
        super().__init__(budget)
        self.dim = dim
        self.low = low
        self.high = high
        self.best_score: float = -float("inf")

    def observe(self) -> dict[str, Any]:
        return {
            "action_space": {
                "kind": self.kind,
                "dim": self.dim,
                "low": [self.low] * self.dim,
                "high": [self.high] * self.dim,
            },
            **self._public(),
        }

    def _public(self) -> dict[str, Any]:
        return {}

    def _check_point(self, action: Action) -> np.ndarray:
        x = action.get("x")
        if not isinstance(x, (list, tuple)) or len(x) != self.dim:
            raise InvalidAction(f"action 'x' must be a list of {self.dim} numbers")
        try:
            point = np.asarray(x, dtype=float)
        except (TypeError, ValueError) as exc:
            raise InvalidAction(f"action 'x' must contain numbers: {exc}") from exc
        if not np.all(np.isfinite(point)):
            raise InvalidAction("action 'x' contains non-finite values")
        return point

    def step(self, action: Action) -> Feedback:
        if self.steps >= self.budget:
            raise InvalidAction("episode budget exhausted")
        self.steps += 1
        try:
            point = self._check_point(action)
        except InvalidAction as exc:
            # Malformed actions consume budget and return an explicit error
            # signal; they never grant extra attempts.
            return {"error": str(exc), "valid": False}
        value = self._true_score(point)
        noisy = value + self._noise(self.steps)
        self.best_score = max(self.best_score, value)
        return {"valid": True, "feedback_value": float(noisy)}

    def _noise(self, query_index: int) -> float:
        return 0.0

    def _true_score(self, point: np.ndarray) -> float:
        raise NotImplementedError

    def finalize(self) -> float:
        return self.best_score


# ---------------------------------------------------------------------------
# family 1: quadratic optimization
# ---------------------------------------------------------------------------


class QuadraticEpisode(_BoxSearchEpisode):
    def __init__(
        self, budget: int, q: np.ndarray, eig: np.ndarray, center: np.ndarray, observed: bool
    ) -> None:
        super().__init__(budget, dim=int(center.shape[0]), low=-2.0, high=2.0)
        self._q = q
        self._eig = eig
        self._center = center
        self._observed = observed

    def _public(self) -> dict[str, Any]:
        if not self._observed:
            return {"observed": False}
        return {
            "observed": True,
            "quadratic": {
                "eigenvalues": [float(v) for v in self._eig],
                "orthogonal": [[float(v) for v in row] for row in self._q],
                "center": [float(v) for v in self._center],
            },
        }

    def _true_score(self, point: np.ndarray) -> float:
        y = self._q.T @ (point - self._center)
        loss = float(np.sum(self._eig * y * y))
        return -loss  # higher is better


class QuadraticOpt(TaskFamily):
    name = "quadratic_opt"
    version = "1"

    def difficulty_keys(self) -> list[str]:
        return _DIFF_KEYS[self.name]

    def sample(self, seed: int, difficulty: Difficulty) -> dict[str, Any]:
        dim = _as_int(difficulty, "dim", 4, 1, 64)
        cond = _as_float(difficulty, "condition_number", 30.0, 1.0, 1e6)
        observed = bool(difficulty.get("observed", True))
        rng = np.random.default_rng(seed)
        q, _ = np.linalg.qr(rng.standard_normal((dim, dim)))
        eig = np.exp(np.linspace(0.0, np.log(cond), dim))
        center = rng.uniform(-1.0, 1.0, dim)
        return {
            "family": self.name,
            "version": self.version,
            "seed": seed,
            "difficulty": {"dim": dim, "condition_number": cond, "observed": observed},
            "hidden": {"q": q.tolist(), "eig": eig.tolist(), "center": center.tolist()},
            "oracle_score": 0.0,  # loss optimum is 0 => score optimum is -0.0
        }

    def begin(self, instance: dict[str, Any], budget: int) -> Episode:
        h = instance["hidden"]
        return QuadraticEpisode(
            budget,
            q=np.asarray(h["q"]),
            eig=np.asarray(h["eig"]),
            center=np.asarray(h["center"]),
            observed=bool(instance["difficulty"]["observed"]),
        )


# ---------------------------------------------------------------------------
# family 2: noisy black-box optimization (rastrigin)
# ---------------------------------------------------------------------------


class NoisyBlackboxEpisode(_BoxSearchEpisode):
    def __init__(
        self, budget: int, seed: int, dim: int, modality: float, noise_sigma: float
    ) -> None:
        super().__init__(budget, dim=dim, low=-5.12, high=5.12)
        self._seed = seed
        self._modality = modality
        self._sigma = noise_sigma

    def _noise(self, query_index: int) -> float:
        if self._sigma == 0.0:
            return 0.0
        # Deterministic given (instance seed, query index): independent of call
        # order, so repeated queries at a point give independent noise draws.
        rng = np.random.default_rng([self._seed, query_index])
        return float(rng.normal(0.0, self._sigma))

    def _true_score(self, point: np.ndarray) -> float:
        a = self._modality
        loss = float(a * self.dim - np.sum(point * point - a * np.cos(2.0 * np.pi * point)))
        return -loss  # higher is better; optimum 0 at the origin


class NoisyBlackbox(TaskFamily):
    name = "noisy_blackbox"
    version = "1"

    def difficulty_keys(self) -> list[str]:
        return _DIFF_KEYS[self.name]

    def sample(self, seed: int, difficulty: Difficulty) -> dict[str, Any]:
        dim = _as_int(difficulty, "dim", 3, 1, 32)
        sigma = _as_float(difficulty, "noise_sigma", 2.0, 0.0, 1e3)
        modality = _as_float(difficulty, "modality", 10.0, 0.0, 100.0)
        return {
            "family": self.name,
            "version": self.version,
            "seed": seed,
            "difficulty": {"dim": dim, "noise_sigma": sigma, "modality": modality},
            "hidden": {},
            "oracle_score": 0.0,
        }

    def begin(self, instance: dict[str, Any], budget: int) -> Episode:
        d = instance["difficulty"]
        return NoisyBlackboxEpisode(
            budget,
            seed=int(instance["seed"]),
            dim=int(d["dim"]),
            modality=float(d["modality"]),
            noise_sigma=float(d["noise_sigma"]),
        )


# ---------------------------------------------------------------------------
# family 3: resource allocation under a knapsack constraint
# ---------------------------------------------------------------------------


class AllocationEpisode(Episode):
    def __init__(
        self,
        budget: int,
        weights: np.ndarray,
        values: np.ndarray,
        estimates: np.ndarray,
        capacity: int,
        reveal_true_value: bool,
    ) -> None:
        super().__init__(budget)
        self._weights = weights
        self._values = values
        self._estimates = estimates
        self._capacity = capacity
        self._reveal = reveal_true_value
        self.best_feasible_value: float = 0.0

    def observe(self) -> dict[str, Any]:
        return {
            "action_space": {
                "kind": "subset",
                "n_items": int(self._weights.shape[0]),
            },
            "weights": [int(w) for w in self._weights],
            "value_estimates": [float(v) for v in self._estimates],
            "capacity": int(self._capacity),
            "true_value_feedback": self._reveal,
        }

    def step(self, action: Action) -> Feedback:
        if self.steps >= self.budget:
            raise InvalidAction("episode budget exhausted")
        self.steps += 1
        mask = action.get("mask")
        if not isinstance(mask, (list, tuple)) or len(mask) != self._weights.shape[0]:
            return {
                "valid": False,
                "error": f"action 'mask' must be a 0/1 list of length {self._weights.shape[0]}",
            }
        try:
            bits = np.asarray([int(bool(b)) for b in mask], dtype=float)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            return {"valid": False, "error": f"invalid mask: {exc}"}
        total_weight = float(bits @ self._weights)
        feasible = total_weight <= self._capacity
        true_value = float(bits @ self._values)
        if feasible:
            self.best_feasible_value = max(self.best_feasible_value, true_value)
        fb: dict[str, Any] = {
            "valid": True,
            "feasible": bool(feasible),
            "total_weight": total_weight,
        }
        if self._reveal:
            fb["total_value"] = true_value
        return fb

    def finalize(self) -> float:
        return self.best_feasible_value


class Allocation(TaskFamily):
    name = "allocation"
    version = "1"

    def difficulty_keys(self) -> list[str]:
        return _DIFF_KEYS[self.name]

    def sample(self, seed: int, difficulty: Difficulty) -> dict[str, Any]:
        n = _as_int(difficulty, "n_items", 12, 2, 200)
        cap_frac = _as_float(difficulty, "capacity_fraction", 0.4, 0.05, 1.0)
        sigma = _as_float(difficulty, "noise_sigma", 10.0, 0.0, 1e3)
        feedback = str(difficulty.get("feedback", "full"))
        if feedback not in ("full", "delayed"):
            raise ValueError("difficulty 'feedback' must be 'full' or 'delayed'")
        rng = np.random.default_rng(seed)
        weights = rng.integers(1, 21, n)
        values = rng.uniform(1.0, 100.0, n)
        estimates = values + rng.normal(0.0, sigma, n)
        capacity = int(np.ceil(float(weights.sum()) * cap_frac))
        return {
            "family": self.name,
            "version": self.version,
            "seed": seed,
            "difficulty": {
                "n_items": n,
                "capacity_fraction": cap_frac,
                "noise_sigma": sigma,
                "feedback": feedback,
            },
            "hidden": {
                "weights": weights.tolist(),
                "values": values.tolist(),
                "estimates": estimates.tolist(),
                "capacity": capacity,
            },
            "oracle_score": None,
        }

    def begin(self, instance: dict[str, Any], budget: int) -> Episode:
        h = instance["hidden"]
        return AllocationEpisode(
            budget,
            weights=np.asarray(h["weights"], dtype=float),
            values=np.asarray(h["values"]),
            estimates=np.asarray(h["estimates"]),
            capacity=int(h["capacity"]),
            reveal_true_value=instance["difficulty"]["feedback"] == "full",
        )


# ---------------------------------------------------------------------------
# family 4: declarative string transformation ("program repair" without code)
# ---------------------------------------------------------------------------

_OPS = (
    "upper",
    "lower",
    "reverse",
    "sort_chars",
    "reverse_words",
    "strip_vowels",
    "dedup_chars",
    "swapcase",
    "remove_digits",
    "replace: :_",
    "replace:a:e",
    "replace:-:_",
)


def apply_ops(text: str, ops: list[str]) -> str:
    out = text
    for op in ops:
        if op == "upper":
            out = out.upper()
        elif op == "lower":
            out = out.lower()
        elif op == "reverse":
            out = out[::-1]
        elif op == "sort_chars":
            out = "".join(sorted(out))
        elif op == "reverse_words":
            out = " ".join(reversed(out.split(" ")))
        elif op == "strip_vowels":
            out = "".join(c for c in out if c.lower() not in "aeiou")
        elif op == "dedup_chars":
            seen: set[str] = set()

            def _dedup_char(c: str, _seen: set[str] = seen) -> bool:
                if c in _seen:
                    return False
                _seen.add(c)
                return True

            out = "".join(c for c in out if _dedup_char(c))
        elif op == "swapcase":
            out = out.swapcase()
        elif op == "remove_digits":
            out = "".join(c for c in out if not c.isdigit())
        elif op.startswith("replace:"):
            _, old, new = op.split(":", 2)
            out = out.replace(old, new)
        else:
            raise InvalidAction(f"unknown op {op!r}")
    return out


class TransformEpisode(Episode):
    def __init__(
        self,
        budget: int,
        public_pairs: list[tuple[str, str]],
        hidden_pairs: list[tuple[str, str]],
        max_chain: int,
    ) -> None:
        super().__init__(budget)
        self._public = public_pairs
        self._hidden = hidden_pairs
        self._max_chain = max_chain
        self.best_public = 0

    def observe(self) -> dict[str, Any]:
        return {
            "action_space": {
                "kind": "op_chain",
                "vocabulary": list(_OPS),
                "max_len": self._max_chain,
            },
            "examples": [{"input": a, "expected": b} for a, b in self._public],
        }

    def _score_chain(self, ops: Any, pairs: list[tuple[str, str]]) -> int:
        if not isinstance(ops, (list, tuple)) or not (1 <= len(ops) <= self._max_chain):
            raise InvalidAction(f"'ops' must be a list of 1..{self._max_chain} op names")
        for op in ops:
            if not isinstance(op, str) or op not in _OPS:
                raise InvalidAction(f"unknown op {op!r}")
        return sum(1 for a, b in pairs if apply_ops(a, list(ops)) == b)

    def step(self, action: Action) -> Feedback:
        if self.steps >= self.budget:
            raise InvalidAction("episode budget exhausted")
        self.steps += 1
        try:
            passed = self._score_chain(action.get("ops"), self._public)
        except InvalidAction as exc:
            return {"valid": False, "error": str(exc), "public_passed": 0}
        self.best_public = max(self.best_public, passed)
        return {"valid": True, "public_passed": passed, "public_total": len(self._public)}

    def finalize(self) -> float:
        # Hidden score is only computable here; agents never see hidden pairs.
        best = 0
        return float(best)  # overridden by Transform.finalize wrapper below


class _TransformEpisodeWithHidden(TransformEpisode):
    """Episode whose finalize() scores the best *public-passing* chain on hidden pairs."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._best_full_chain: list[str] | None = None

    def step(self, action: Action) -> Feedback:
        fb = super().step(action)
        if fb.get("valid") and fb.get("public_passed") == len(self._public):
            self._best_full_chain = list(action["ops"])
        return fb

    def finalize(self) -> float:
        if self._best_full_chain is None:
            # No chain solved the public examples: score = fraction of public
            # progress (never above 100), so partial credit exists but full
            # credit requires generalizing to hidden pairs.
            frac = self.best_public / max(1, len(self._public))
            return frac * 50.0
        passed = self._score_chain(self._best_full_chain, self._hidden)
        return 100.0 * passed / max(1, len(self._hidden))


class Transform(TaskFamily):
    name = "transform"
    version = "1"

    def difficulty_keys(self) -> list[str]:
        return _DIFF_KEYS[self.name]

    def sample(self, seed: int, difficulty: Difficulty) -> dict[str, Any]:
        n_pub = _as_int(difficulty, "n_public", 4, 1, 50)
        n_hid = _as_int(difficulty, "n_hidden", 10, 1, 200)
        max_chain = _as_int(difficulty, "max_chain", 2, 1, 4)
        rng = np.random.default_rng(seed)
        chain_len = int(rng.integers(1, max_chain + 1))
        chain = [str(rng.choice(_OPS)) for _ in range(chain_len)]
        alphabet = "abc xyz-019"
        words = []

        def make_word() -> str:
            k = int(rng.integers(3, 9))
            return "".join(rng.choice(list(alphabet), k))

        for _ in range(n_pub + n_hid):
            words.append(make_word())
        pairs = [(w, apply_ops(w, chain)) for w in words]
        return {
            "family": self.name,
            "version": self.version,
            "seed": seed,
            "difficulty": {"n_public": n_pub, "n_hidden": n_hid, "max_chain": max_chain},
            "hidden": {"chain": chain, "pairs": pairs},
            "oracle_score": 100.0,
        }

    def begin(self, instance: dict[str, Any], budget: int) -> Episode:
        pairs = [tuple(p) for p in instance["hidden"]["pairs"]]
        n_pub = int(instance["difficulty"]["n_public"])
        return _TransformEpisodeWithHidden(
            budget,
            public_pairs=pairs[:n_pub],
            hidden_pairs=pairs[n_pub:],
            max_chain=int(instance["difficulty"]["max_chain"]),
        )


FAMILIES: dict[str, TaskFamily] = {
    f.name: f for f in (QuadraticOpt(), NoisyBlackbox(), Allocation(), Transform())
}

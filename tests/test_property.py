"""Property-style tests with seeded randomized inputs (no extra dependency).

Each property is checked over many random cases drawn from a fixed seed, so
failures are reproducible.
"""

import json
import re

import numpy as np

from proofbench.actions import validate_patch
from proofbench.canonical import canonical_json, hash_obj
from proofbench.events import verify_chain
from proofbench.spec import ParamBound, load_spec

RNG = np.random.default_rng(2026)


def _random_bounds(rng: np.random.Generator, n: int) -> list[ParamBound]:
    bounds = []
    for i in range(n):
        kind = str(rng.choice(["float", "int", "categorical"]))
        name = f"p{i}"
        if kind == "categorical":
            bounds.append(ParamBound(name=name, kind="categorical", choices=["x", "y", "z"]))
        else:
            low = float(rng.uniform(-10, 10))
            high = low + float(rng.uniform(0.1, 10))
            if kind == "int":
                import math

                # int bounds must contain at least one integer (platform rule);
                # widen high just past the next integer above low if needed.
                if math.ceil(low) > math.floor(high):
                    high = float(math.ceil(low)) + 0.5
            bounds.append(ParamBound(name=name, kind=kind, low=low, high=high))
    return bounds


def test_property_accepted_patches_always_within_bounds() -> None:
    rng = np.random.default_rng(1)
    for _ in range(300):
        bounds = _random_bounds(rng, int(rng.integers(1, 5)))
        current = {}
        for b in bounds:
            current[b.name] = 0.0 if b.kind != "categorical" else "x"
            if b.kind == "int":
                import math

                # current must itself be a valid accepted value within bounds.
                lo, hi = math.ceil(float(b.low)), math.floor(float(b.high))  # type: ignore[arg-type]
                current[b.name] = (lo + hi) // 2
            elif b.kind == "float":
                current[b.name] = (float(b.low) + float(b.high)) / 2  # type: ignore[arg-type]
        patch = {}
        for b in bounds:
            if rng.random() < 0.5:
                if b.kind == "categorical":
                    patch[b.name] = str(rng.choice(b.choices or []))
                elif b.kind == "int":
                    import math

                    # Valid ints satisfy low <= v <= high; with float edges
                    # that range is ceil(low)..floor(high).
                    lo, hi = math.ceil(float(b.low)), math.floor(float(b.high))
                    patch[b.name] = int(rng.integers(lo, hi + 1))
                else:
                    patch[b.name] = float(rng.uniform(float(b.low), float(b.high)))
        result = validate_patch(patch, bounds, current)
        assert result.accepted
        for key, value in result.normalized.items():
            b = next(x for x in bounds if x.name == key)
            if b.kind == "categorical":
                assert value in (b.choices or [])
            elif b.kind == "int":
                assert float(b.low) <= value <= float(b.high)  # type: ignore[operator]
            else:
                assert float(b.low) <= value <= float(b.high)  # type: ignore[operator]


def test_property_out_of_bounds_always_rejected() -> None:
    rng = np.random.default_rng(2)
    for _ in range(200):
        bounds = _random_bounds(rng, 1)
        b = bounds[0]
        if b.kind == "categorical":
            patch = {b.name: "not-a-choice"}
        elif b.kind == "int":
            patch = {b.name: int(float(b.high)) + 1}  # type: ignore[operator]
        else:
            patch = {b.name: float(b.high) + abs(float(rng.uniform(0.1, 5)))}  # type: ignore[operator]
        result = validate_patch(patch, bounds, {b.name: 0.0})
        assert not result.accepted


def test_property_canonical_json_roundtrips() -> None:
    rng = np.random.default_rng(3)
    for _ in range(100):
        obj = {
            "f": float(rng.normal()),
            "i": int(rng.integers(-1000, 1000)),
            "s": str(rng.choice(list("abcdefg"))),
            "nested": {
                "l": [int(rng.integers(0, 10)) for _ in range(3)],
                "b": bool(rng.integers(0, 2)),
            },
        }
        text = canonical_json(obj)
        assert json.loads(text) == obj
        assert hash_obj(json.loads(text)) == hash_obj(obj)


def test_property_event_chain_survives_random_appends(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from proofbench.events import EventLog

    rng = np.random.default_rng(4)
    log = EventLog(tmp_path / "events.jsonl")
    for i in range(50):
        log.append("rand", {"v": int(rng.integers(0, 1e6)), "i": i})
    events = EventLog(tmp_path / "events.jsonl").read_all()
    assert verify_chain(events) == []
    # Corrupt one random event; the chain must fail.
    victim = int(rng.integers(0, 50))
    events[victim]["payload"]["v"] += 1
    assert verify_chain(events)


def test_property_spec_json_files_in_repo_are_valid() -> None:
    from pathlib import Path

    for path in Path("experiments").glob("*.json"):
        spec = load_spec(json.loads(path.read_text(encoding="utf-8")))
        assert re.match(r"^[a-z0-9][a-z0-9_.-]+$", spec.experiment_id)
        assert spec.hypothesis

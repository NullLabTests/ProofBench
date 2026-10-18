"""Permitted-action policy for candidate self-modification.

The candidate may propose changes *only* to parameters listed in the
experiment's ``action_bounds``, and only within the declared ranges.  Anything
else — unknown parameters, out-of-range values, attempts to touch the
evaluator, budget, acceptance policy, or baseline — is a policy violation:
recorded as an audit event, never applied.

This module contains no execution side effects; the loop applies accepted
patches and the evidence layer records every decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from proofbench.spec import ParamBound


@dataclass(frozen=True)
class PatchValidation:
    accepted: bool
    normalized: dict[str, Any]
    reasons: list[str]


def validate_patch(
    patch: dict[str, Any], bounds: list[ParamBound], current: dict[str, Any]
) -> PatchValidation:
    """Validate a proposed parameter patch against declared bounds.

    ``current`` is the accepted parameter dict (used for context; patches are
    complete replacements of the listed keys, other keys are inherited
    unchanged and cannot be added).
    """
    reasons: list[str] = []
    normalized: dict[str, Any] = dict(current)
    bound_map = {b.name: b for b in bounds}
    for key, value in patch.items():
        bound = bound_map.get(key)
        if bound is None:
            reasons.append(f"parameter {key!r} is not in the permitted action bounds")
            continue
        if bound.kind == "categorical":
            if not isinstance(value, str) or value not in (bound.choices or []):
                reasons.append(f"{key!r}: {value!r} is not one of {bound.choices!r}")
            else:
                normalized[key] = value
        elif bound.kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                reasons.append(f"{key!r}: expected int, got {type(value).__name__}")
            elif not (float(bound.low) <= value <= float(bound.high)):  # type: ignore[arg-type]
                reasons.append(f"{key!r}: {value} outside [{bound.low}, {bound.high}]")
            else:
                normalized[key] = int(value)
        else:  # float
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                reasons.append(f"{key!r}: expected float, got {type(value).__name__}")
            elif not (float(bound.low) <= float(value) <= float(bound.high)):  # type: ignore[arg-type]
                reasons.append(f"{key!r}: {value} outside [{bound.low}, {bound.high}]")
            else:
                normalized[key] = float(value)
    return PatchValidation(accepted=not reasons, normalized=normalized, reasons=reasons)


# Parameters that are structurally forbidden regardless of action_bounds.
FORBIDDEN_KEYS = frozenset(
    {
        "evaluator",
        "score",
        "scores",
        "budget",
        "evaluations_per_instance",
        "acceptance",
        "validation_margin",
        "baseline",
        "seeds",
        "test_seeds",
        "oracle_score",
        "evidence",
    }
)


def audit_forbidden_keys(patch: dict[str, Any]) -> list[str]:
    """Return violation reasons for attempts to touch protected surfaces."""
    return [
        f"key {key!r} is a protected experiment surface and can never be modified"
        for key in patch
        if key in FORBIDDEN_KEYS
    ]

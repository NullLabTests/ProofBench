"""Permitted-action policy: bounded patches, protected surfaces."""

from proofbench.actions import audit_forbidden_keys, validate_patch
from proofbench.spec import ParamBound

BOUNDS = [
    ParamBound(name="refine_fraction", kind="float", low=0.0, high=1.0),
    ParamBound(name="rounds", kind="int", low=1, high=10),
    ParamBound(name="mode", kind="categorical", choices=["a", "b"]),
]
CURRENT = {"refine_fraction": 0.5, "rounds": 3, "mode": "a"}


def test_valid_patch_accepted_and_normalized() -> None:
    v = validate_patch({"refine_fraction": 0.9}, BOUNDS, CURRENT)
    assert v.accepted
    assert v.normalized["refine_fraction"] == 0.9
    assert v.normalized["rounds"] == 3  # untouched keys inherited


def test_unknown_parameter_rejected() -> None:
    v = validate_patch({"sneaky": 1.0}, BOUNDS, CURRENT)
    assert not v.accepted
    assert any("not in the permitted action bounds" in r for r in v.reasons)


def test_out_of_range_rejected() -> None:
    v = validate_patch({"refine_fraction": 1.5}, BOUNDS, CURRENT)
    assert not v.accepted
    v2 = validate_patch({"rounds": 0}, BOUNDS, CURRENT)
    assert not v2.accepted


def test_type_confusion_rejected() -> None:
    assert not validate_patch({"rounds": 3.7}, BOUNDS, CURRENT).accepted
    assert not validate_patch({"rounds": True}, BOUNDS, CURRENT).accepted
    assert not validate_patch({"refine_fraction": "0.5"}, BOUNDS, CURRENT).accepted
    assert not validate_patch({"mode": 3}, BOUNDS, CURRENT).accepted


def test_categorical_not_in_choices_rejected() -> None:
    assert not validate_patch({"mode": "z"}, BOUNDS, CURRENT).accepted


def test_protected_surfaces_always_flagged() -> None:
    for key in ("evaluator", "budget", "acceptance", "baseline", "seeds", "evidence", "score"):
        reasons = audit_forbidden_keys({key: 0})
        assert reasons, f"protected key {key} must be flagged"


def test_boundary_values_accepted() -> None:
    assert validate_patch({"refine_fraction": 0.0}, BOUNDS, CURRENT).accepted
    assert validate_patch({"refine_fraction": 1.0}, BOUNDS, CURRENT).accepted
    assert validate_patch({"rounds": 10}, BOUNDS, CURRENT).accepted

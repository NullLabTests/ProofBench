"""Strict experiment-specification validation."""

import json
from pathlib import Path

import pytest

from proofbench.errors import SpecValidationError
from proofbench.spec import ExperimentSpec, load_spec
from tests.conftest import make_spec_dict


def test_valid_spec_loads() -> None:
    spec = load_spec(make_spec_dict())
    assert spec.experiment_id == "test-experiment"
    assert spec.spec_hash()


def test_spec_hash_is_stable_and_sensitive() -> None:
    a = load_spec(make_spec_dict())
    b = load_spec(make_spec_dict())
    assert a.spec_hash() == b.spec_hash()
    c = load_spec(make_spec_dict(budget={"evaluations_per_instance": 31, "max_rounds": 2}))
    assert a.spec_hash() != c.spec_hash()


def test_rejects_unknown_fields() -> None:
    data = make_spec_dict(surprise_field="nope")
    with pytest.raises(SpecValidationError, match="surprise_field"):
        load_spec(data)


def test_rejects_overlapping_seeds() -> None:
    data = make_spec_dict(
        seeds={
            "train_seeds": [1, 2, 3],
            "validation_seeds": [3, 4],
            "test_seeds": [500],
        }
    )
    with pytest.raises(SpecValidationError, match="disjoint"):
        load_spec(data)


def test_rejects_short_hypothesis() -> None:
    with pytest.raises(SpecValidationError):
        load_spec(make_spec_dict(hypothesis="too short"))


def test_rejects_bad_primary_direction() -> None:
    data = make_spec_dict()
    data["primary_outcome"]["direction"] = "sideways"
    with pytest.raises(SpecValidationError):
        load_spec(data)


def test_rejects_bad_action_bound() -> None:
    data = make_spec_dict(action_bounds=[{"name": "p", "kind": "float", "low": 5.0, "high": 1.0}])
    with pytest.raises(SpecValidationError, match="low < high"):
        load_spec(data)


def test_rejects_categorical_without_choices() -> None:
    data = make_spec_dict(action_bounds=[{"name": "p", "kind": "categorical", "choices": ["only"]}])
    with pytest.raises(SpecValidationError, match="2 choices"):
        load_spec(data)


def test_rejects_duplicate_action_bounds() -> None:
    bound = {"name": "p", "kind": "float", "low": 0.0, "high": 1.0}
    with pytest.raises(SpecValidationError, match="duplicate"):
        load_spec(make_spec_dict(action_bounds=[bound, dict(bound)]))


def test_rejects_empty_task_list() -> None:
    with pytest.raises(SpecValidationError):
        load_spec(make_spec_dict(tasks=[]))


def test_rejects_future_schema_version() -> None:
    with pytest.raises(SpecValidationError, match="schema_version"):
        load_spec(make_spec_dict(schema_version="99.0"))


def test_rejects_bad_id_case() -> None:
    with pytest.raises(SpecValidationError, match="experiment_id"):
        load_spec(make_spec_dict(experiment_id="UpperCase"))


def test_cli_validate_rejects_malformed_json(tmp_path: Path) -> None:
    from proofbench.cli import main

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["validate-experiment", str(bad)])
    assert exc.value.code == 3


def test_cli_validate_accepts_good_spec(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from proofbench.cli import main

    good = tmp_path / "good.json"
    good.write_text(json.dumps(make_spec_dict()), encoding="utf-8")
    main(["validate-experiment", str(good)])
    out = capsys.readouterr().out
    assert "valid: test-experiment" in out
    assert "spec hash:" in out


def test_round_trip_through_model() -> None:
    spec = load_spec(make_spec_dict())
    again = ExperimentSpec.model_validate(spec.model_dump(mode="json"))
    assert again.spec_hash() == spec.spec_hash()

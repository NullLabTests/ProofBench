"""CLI behavior: exit codes, help, and functional commands."""

import json
from pathlib import Path

import pytest

from proofbench.cli import main
from tests.conftest import make_spec_dict


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "proofbench" in capsys.readouterr().out


def test_no_args_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
    assert "usage" in capsys.readouterr().out.lower()


def test_usage_error_exits_two() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["no-such-command"])
    assert exc.value.code == 2


def test_doctor_runs(capsys: pytest.CaptureFixture[str]) -> None:
    main(["doctor"])
    out = capsys.readouterr().out
    assert "python" in out.lower()


def test_list_tasks(capsys: pytest.CaptureFixture[str]) -> None:
    main(["list-tasks"])
    out = capsys.readouterr().out
    for family in ("quadratic_opt", "noisy_blackbox", "allocation", "transform"):
        assert family in out


def test_cite_lists_upstream_attribution(capsys: pytest.CaptureFixture[str]) -> None:
    main(["cite"])
    out = capsys.readouterr().out
    assert "ProofBench" in out
    assert "Apple Sample Code License" in out  # ideas-only upstream, non-OSI
    assert "Apache-2.0" in out  # SPACE
    assert "no code reused" in out
    assert "not endorsement" in out


def test_cite_json_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    main(["cite", "--json"])
    records = json.loads(capsys.readouterr().out)
    keys = {r["key"] for r in records}
    assert {"proofbench", "ml-rsi-inference-bench", "space"} <= keys
    for r in records:
        assert {"name", "license", "url", "relationship"} <= set(r)


def test_run_inspect_report_export_verify_cycle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs = tmp_path / "runs"
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(make_spec_dict()), encoding="utf-8")

    main(["run", str(spec_file), "--run-id", "cli-run", "--runs-dir", str(runs)])
    out = capsys.readouterr().out
    assert "outcome:" in out
    assert "run id: cli-run" in out

    main(["inspect", str(runs / "cli-run")])
    info = json.loads(capsys.readouterr().out)
    assert info["finalized"] is True
    assert info["event_chain_intact"] is True

    main(["report", str(runs / "cli-run")])
    report_out = capsys.readouterr().out
    assert "PREREGISTERED" not in report_out  # report shows hypothesis, not the label
    assert "Hypothesis (preregistered)" in report_out
    assert "OUTCOME" in report_out.upper()

    bundle_dir = tmp_path / "bundle"
    main(["export", str(runs / "cli-run"), "--out", str(bundle_dir)])
    capsys.readouterr()
    main(["verify-bundle", str(bundle_dir)])
    verify_out = capsys.readouterr().out
    assert "bundle verification PASSED" in verify_out


def test_verify_bundle_exit_code_on_failure(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(make_spec_dict()), encoding="utf-8")
    main(["run", str(spec_file), "--run-id", "r", "--runs-dir", str(runs)])
    bundle = tmp_path / "bundle"
    main(["export", str(runs / "r"), "--out", str(bundle)])
    (bundle / "VERIFY.md").unlink()
    with pytest.raises(SystemExit) as exc:
        main(["verify-bundle", str(bundle)])
    assert exc.value.code == 4


def test_run_missing_spec_exits_nonzero(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["run", str(tmp_path / "nope.json")])
    assert exc.value.code != 0


def test_resume_missing_run_exits_nine(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["resume", "definitely-missing-run", "--runs-dir", str(tmp_path)])
    assert exc.value.code == 9


def test_inspect_missing_run_exits_nine(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["inspect", str(tmp_path / "missing")])
    assert exc.value.code == 9


def test_validate_bad_spec_exit_three(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"experiment_id": "x"}), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["validate-experiment", str(bad)])
    assert exc.value.code == 3


def test_compare_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runs = tmp_path / "runs"
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(make_spec_dict()), encoding="utf-8")
    main(["run", str(spec_file), "--run-id", "ra", "--runs-dir", str(runs)])
    capsys.readouterr()
    main(["run", str(spec_file), "--run-id", "rb", "--runs-dir", str(runs)])
    capsys.readouterr()
    main(["compare", str(runs / "ra"), str(runs / "rb")])
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["same_protocol"] is True


def test_model_adapter_not_configured_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PROOFBENCH_MODEL_ID", "PROOFBENCH_MODEL_API_BASE", "PROOFBENCH_MODEL_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    from proofbench.model_adapter import OpenAICompatAdapter

    adapter = OpenAICompatAdapter()
    assert adapter.configured is False

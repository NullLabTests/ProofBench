"""Evidence bundle export and independent verification."""

import json
from pathlib import Path

import pytest

from proofbench.bundle import compare_runs, export_bundle, verify_bundle
from proofbench.errors import RunNotFound, VerificationFailed
from proofbench.loop import Context, run_experiment
from tests.conftest import make_spec_dict


@pytest.fixture()
def finished_run(tmp_path: Path):  # type: ignore[no-untyped-def]
    from proofbench.spec import load_spec

    spec = load_spec(make_spec_dict())
    ctx = Context(spec=spec, run_dir=tmp_path / "run", run_id="run", run_seed=99)
    outcome = run_experiment(ctx)
    return ctx, outcome


def test_export_and_verify_passes(finished_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    ctx, _outcome = finished_run
    bundle = export_bundle(ctx.run_dir, tmp_path / "bundle")
    report = verify_bundle(bundle)
    assert report["passed"] is True
    assert (bundle / "MANIFEST.json").exists()
    assert (bundle / "VERIFY.md").exists()


def test_verify_detects_modified_file(finished_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    ctx, _ = finished_run
    bundle = export_bundle(ctx.run_dir, tmp_path / "bundle")
    state = bundle / "state.json"
    state.write_text(state.read_text() + "\n", encoding="utf-8")  # any change
    with pytest.raises(VerificationFailed, match="manifest"):
        verify_bundle(bundle)


def test_verify_detects_missing_file(finished_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    ctx, _ = finished_run
    bundle = export_bundle(ctx.run_dir, tmp_path / "bundle")
    (bundle / "state.json").unlink()
    with pytest.raises(VerificationFailed, match="manifest"):
        verify_bundle(bundle)


def test_verify_detects_extra_file(finished_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    ctx, _ = finished_run
    bundle = export_bundle(ctx.run_dir, tmp_path / "bundle")
    (bundle / "injected.txt").write_text("surprise", encoding="utf-8")
    with pytest.raises(VerificationFailed, match="manifest"):
        verify_bundle(bundle)


def test_verify_detects_edited_events(finished_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    ctx, _ = finished_run
    bundle = export_bundle(ctx.run_dir, tmp_path / "bundle")
    # Edit an event payload and re-hash the file so the manifest matches but
    # the chain does not.
    events_path = bundle / "events.jsonl"
    lines = [json.loads(x) for x in events_path.read_text().splitlines() if x.strip()]
    lines[0]["payload"]["run_seed"] = 123456
    events_path.write_text(
        "\n".join(json.dumps(x, sort_keys=True, separators=(",", ":")) for x in lines) + "\n",
        encoding="utf-8",
    )
    # Refresh the manifest so only the chain check can catch this.
    from proofbench.canonical import hash_file

    manifest_path = bundle / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["events.jsonl"] = hash_file(str(events_path))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(VerificationFailed, match="event chain"):
        verify_bundle(bundle)


def test_export_refuses_nonempty_dir(finished_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    ctx, _ = finished_run
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "x.txt").write_text("x", encoding="utf-8")
    from proofbench.errors import IntegrityError

    with pytest.raises(IntegrityError, match="non-empty"):
        export_bundle(ctx.run_dir, target)


def test_export_non_run_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(RunNotFound):
        export_bundle(tmp_path / "empty", tmp_path / "out")


def test_compare_two_runs(tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from proofbench.spec import load_spec

    def run(name: str):  # type: ignore[no-untyped-def]
        spec = load_spec(make_spec_dict())
        ctx = Context(spec=spec, run_dir=tmp_path / name, run_id=name, run_seed=99)
        run_experiment(ctx)
        return ctx

    a = run("a")
    b = run("b")
    cmp = compare_runs(a.run_dir, b.run_dir)
    assert cmp["same_protocol"] is True
    assert cmp["a"]["outcome"] == cmp["b"]["outcome"]  # identical deterministic runs

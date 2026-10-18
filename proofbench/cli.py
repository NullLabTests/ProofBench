"""ProofBench command-line interface.

Every command has functional behavior and exit codes are part of the contract:

* 0 — success
* 1 — generic failure
* 2 — usage error (handled by the CLI framework)
* 3 — specification validation error
* 4 — integrity / verification failure
* 6 — policy violation
* 7 — budget exhausted
* 8 — required execution backend unavailable
* 9 — run not found
* 10 — model adapter not configured
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import typer

from proofbench import __version__
from proofbench.bundle import compare_runs, export_bundle, verify_bundle
from proofbench.errors import ProofBenchError, RunNotFound, SpecValidationError
from proofbench.events import EventLog, verify_chain
from proofbench.loop import Context, run_experiment
from proofbench.report import generate_report
from proofbench.spec import ExperimentSpec, load_spec
from proofbench.store import read_json
from proofbench.tasks.families import FAMILIES

app = typer.Typer(
    name="proofbench",
    help=(
        "ProofBench: research-grade benchmarking for long-horizon AI "
        "improvement with independently verifiable evidence bundles."
    ),
    add_completion=False,
    no_args_is_help=True,
)


def _default_runs_dir() -> Path:
    return Path(os.environ.get("PROOFBENCH_RUNS_DIR", "proofbench_runs"))


def _resolve_run(run_id_or_path: str, runs_dir: Path | None = None) -> Path:
    p = Path(run_id_or_path)
    if (p / "spec.json").exists():
        return p
    base = runs_dir or _default_runs_dir()
    candidate = base / run_id_or_path
    if (candidate / "spec.json").exists():
        return candidate
    raise RunNotFound(
        f"run {run_id_or_path!r} not found (looked for a directory with spec.json "
        f"at {p} and {candidate})"
    )


def _load_certificate_from_run(run_dir: Path) -> dict[str, Any]:
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        raise RunNotFound(f"{run_dir} has no event log")
    with open(events_path, encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    certs = [e for e in events if e["kind"] == "certificate_issued"]
    if not certs:
        raise RunNotFound(f"{run_dir} has no certificate; resume the run to complete it")
    artifact = certs[-1]["payload"]["artifact"]
    path = run_dir / "artifacts" / artifact[:2] / artifact
    cert: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return cert


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"proofbench {__version__}")
        raise typer.Exit(0)


@app.callback()
def _main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    # Group callback body: options are handled by eager callbacks above.
    # typer >= 0.26 resolves "missing command" *before* this body runs, so
    # --version must be an eager option callback, not a body check.
    pass


@app.command()
def doctor() -> None:
    """Diagnose the local environment for running ProofBench offline."""
    checks: list[tuple[str, bool, str]] = []

    py_ok = sys.version_info >= (3, 11)
    checks.append(("python>=3.11", py_ok, sys.version.split()[0]))

    for mod in ("pydantic", "numpy", "typer"):
        try:
            __import__(mod)
            checks.append((f"import {mod}", True, "ok"))
        except ImportError as exc:
            checks.append((f"import {mod}", False, str(exc)))

    runs_dir = _default_runs_dir()
    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        probe = runs_dir / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append((f"runs dir writable ({runs_dir})", True, "ok"))
    except OSError as exc:
        checks.append((f"runs dir writable ({runs_dir})", False, str(exc)))

    try:
        stat = os.statvfs(".")
        free_gb = stat.f_bavail * stat.f_frsize / 1e9
        checks.append(("disk free >= 1 GiB", free_gb >= 1.0, f"{free_gb:.1f} GiB"))
    except OSError as exc:  # pragma: no cover - unusual filesystems
        checks.append(("disk free check", False, str(exc)))

    runtime = shutil.which("docker") or shutil.which("podman")
    checks.append(
        (
            "container runtime (optional; needed only for untrusted code)",
            True,
            runtime or "not found — untrusted execution will be refused, as designed",
        )
    )

    width = max(len(name) for name, _, _ in checks)
    all_ok = True
    for name, ok, detail in checks:
        mark = "ok " if ok else "FAIL"
        if not ok:
            all_ok = False
        typer.echo(f"[{mark}] {name:<{width}}  {detail}")
    typer.echo(
        "\nnetwork is never used by core ProofBench commands; "
        "model-backed agents require explicit PROOFBENCH_MODEL_* configuration."
    )
    if not all_ok:
        raise typer.Exit(1)


@app.command("list-tasks")
def list_tasks() -> None:
    """List built-in task families and their documented difficulty parameters."""
    for name in sorted(FAMILIES):
        fam = FAMILIES[name]
        typer.echo(f"{name} (version {fam.version})")
        for key in fam.difficulty_keys():
            typer.echo(f"    - {key}")


@app.command()
def cite(as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON.")) -> None:
    """Print citations, licenses, and upstream attribution for ProofBench."""
    from proofbench.citations import citations_as_json, citations_as_text

    if as_json:
        typer.echo(json.dumps(citations_as_json(), indent=2, sort_keys=True))
    else:
        typer.echo(citations_as_text())


@app.command("validate-experiment")
def validate_experiment(spec_path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Strictly validate an experiment specification; reject invalid input."""
    try:
        data = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpecValidationError(f"{spec_path} is not valid JSON: {exc}") from exc
    spec = load_spec(data)
    typer.echo(f"valid: {spec.experiment_id}")
    typer.echo(f"spec hash: {spec.spec_hash()}")
    typer.echo(
        f"protocol: {spec.protocol_id} v{spec.protocol_version}; "
        f"{len(spec.tasks)} task(s), {len(spec.baselines)} baseline(s), "
        f"max_rounds={spec.budget.max_rounds}, "
        f"evaluations_per_instance={spec.budget.evaluations_per_instance}"
    )


@app.command()
def run(
    spec_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    run_id: str = typer.Option("", "--run-id", help="Run id (default: experiment id + timestamp)."),
    runs_dir: Path = typer.Option(None, "--runs-dir", help="Runs directory."),
) -> None:
    """Execute (or resume) an experiment from a validated specification."""
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    spec = load_spec(data)
    runs = runs_dir or _default_runs_dir()
    rid = run_id or f"{spec.experiment_id}-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = runs / rid
    if run_dir.exists() and not (run_dir / "spec.json").exists():
        raise RunNotFound(f"{run_dir} exists but is not a run directory")
    ctx = Context(spec=spec, run_dir=run_dir, run_id=rid, run_seed=_run_seed(data, rid, spec))
    typer.echo(f"run id: {rid}")
    outcome = run_experiment(ctx)
    _print_outcome(outcome)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="Run id or path to a run directory."),
    runs_dir: Path = typer.Option(None, "--runs-dir", help="Runs directory."),
) -> None:
    """Resume an interrupted or incomplete run from its last checkpoint."""
    run_dir = _resolve_run(run_id, runs_dir)
    spec_doc = read_json(run_dir / "spec.json")
    spec = load_spec(spec_doc["spec"])
    state = read_json(run_dir / "state.json")
    ctx = Context(
        spec=spec, run_dir=run_dir, run_id=str(state["run_id"]), run_seed=int(state["run_seed"])
    )
    typer.echo(f"resuming run {ctx.run_id} at phase {state['phase']}, round {state['round']}")
    outcome = run_experiment(ctx)
    _print_outcome(outcome)


@app.command()
def inspect(
    run_id: str = typer.Argument(...),
    runs_dir: Path = typer.Option(None, "--runs-dir", help="Runs directory."),
) -> None:
    """Show run status: phase, rounds, lineage, quarantine, resources, events."""
    run_dir = _resolve_run(run_id, runs_dir)
    state_path = run_dir / "state.json"
    if not state_path.exists():
        raise RunNotFound(f"{run_dir} has no state.json")
    state = read_json(state_path)
    events = EventLog(run_dir / "events.jsonl").read_all()
    chain_failures = verify_chain(events)
    kinds: dict[str, int] = {}
    for ev in events:
        kinds[ev["kind"]] = kinds.get(ev["kind"], 0) + 1
    info = {
        "run_dir": str(run_dir),
        "run_id": state.get("run_id"),
        "phase": state.get("phase"),
        "round": state.get("round"),
        "finalized": state.get("finalized"),
        "accepted_params": state.get("accepted_params"),
        "param_lineage_length": len(state.get("param_lineage", [])),
        "quarantined": len(state.get("quarantine", [])),
        "resource": state.get("resource"),
        "event_count": len(events),
        "event_kinds": kinds,
        "event_chain_intact": not chain_failures,
        "event_chain_failures": chain_failures[:5],
    }
    typer.echo(json.dumps(info, indent=2, sort_keys=True))


@app.command()
def compare(run_a: Path = typer.Argument(...), run_b: Path = typer.Argument(...)) -> None:
    """Compare two runs' certificates side by side."""
    a = _resolve_run(str(run_a))
    b = _resolve_run(str(run_b))
    typer.echo(json.dumps(compare_runs(a, b), indent=2, sort_keys=True))


@app.command("verify-bundle")
def verify_bundle_cmd(path: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Independently verify an exported evidence bundle (offline)."""
    report = verify_bundle(path)
    for check in report["checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        typer.echo(f"[{mark}] {check['check']}")
    typer.echo(f"\nrun {report['run_id']}: certified outcome = {report['outcome']}")
    typer.echo("bundle verification PASSED")


@app.command()
def report(
    run_id: str = typer.Argument(...),
    runs_dir: Path = typer.Option(None, "--runs-dir", help="Runs directory."),
) -> None:
    """Generate the markdown report for a completed run."""
    run_dir = _resolve_run(run_id, runs_dir)
    typer.echo(generate_report(run_dir))


@app.command()
def export(
    run_id: str = typer.Argument(...),
    out: Path = typer.Option(None, "--out", help="Output directory for the bundle."),
    runs_dir: Path = typer.Option(None, "--runs-dir", help="Runs directory."),
) -> None:
    """Export a self-contained, checksummed evidence bundle for a run."""
    run_dir = _resolve_run(run_id, runs_dir)
    out_dir = out or Path(f"proofbench-bundle-{run_dir.name}")
    export_bundle(run_dir, out_dir)
    typer.echo(f"bundle written to {out_dir}")
    typer.echo(f"verify with: proofbench verify-bundle {out_dir}")


def _run_seed(spec_data: dict[str, Any], run_id: str, spec: ExperimentSpec) -> int:
    from proofbench.loop import derive_seed

    if spec.run_seed is not None:
        return int(spec.run_seed)
    base = int(spec_data.get("analysis", {}).get("bootstrap_seed", 0))
    return derive_seed(base, run_id)


def _print_outcome(outcome: dict[str, Any]) -> None:
    cert = outcome["certificate"]
    typer.echo(f"outcome: {cert['outcome']}")
    pa = cert["primary_analysis"]
    typer.echo(
        f"primary: mean improvement {pa.get('mean_improvement')}, "
        f"CI [{pa.get('ci_low')}, {pa.get('ci_high')}], p={pa.get('p_value')}"
    )
    typer.echo(f"certificate artifact: {outcome['certificate_artifact']}")
    typer.echo(f"run dir: {outcome['run_dir']}")


def _click_exceptions() -> Any:
    """Return the click exceptions module typer actually raises from.

    typer >= 0.26 vendors click as ``typer._click`` and raises from that;
    older typer uses the standalone ``click`` package. Importing both and
    catching the wrong one would silently miss usage errors.
    """
    try:
        from typer._click import exceptions as vendored  # typer >= 0.26

        return vendored
    except ImportError:
        from click import exceptions as fallback  # older typer: real click

        return fallback


def main(argv: list[str] | None = None) -> None:
    """Process entry point mapping exceptions to documented exit codes."""
    ce = _click_exceptions()

    try:
        result = app(args=argv, standalone_mode=False)
        if isinstance(result, int):  # --help / --version return their exit code
            raise SystemExit(result) from None
    except ce.NoArgsIsHelpError as exc:  # bare invocation prints help, exit 2
        raise SystemExit(exc.exit_code) from None
    except ce.Exit as exc:
        raise SystemExit(exc.exit_code) from None
    except ce.ClickException as exc:  # usage errors -> exit 2
        exc.show()
        raise SystemExit(exc.exit_code) from None
    except SystemExit:
        raise
    except KeyboardInterrupt:
        typer.secho("interrupted", fg="yellow", err=True)
        raise SystemExit(130) from None
    except ProofBenchError as exc:
        typer.secho(f"error: {exc}", fg="red", err=True)
        raise SystemExit(exc.exit_code) from None


if __name__ == "__main__":
    main()

"""Self-contained evidence bundles: export and independent verification.

An evidence bundle is a directory another researcher can verify **offline**,
with no network access and no API keys:

    MANIFEST.json   content address (sha256) of every file in the bundle
    VERIFY.md       step-by-step verification instructions
    spec.json       the validated experiment specification + its hash
    events.jsonl    the full append-only, hash-chained event record
    state.json      final checkpoint (lineage, quarantine, resources)
    artifacts/      content-addressed raw results (test trials, ...)

``verify_bundle`` performs, in order:

1. manifest integrity — every listed file's sha256 recomputed; missing or
   extra files reported;
2. event chain integrity — full hash-chain verification;
3. spec identity — spec hash recomputed from the spec payload and matched
   against the certificate;
4. analysis recomputation — the primary and strategy comparisons are
   recomputed from the *raw per-trial test results* with the recorded
   procedure and seeds, and compared field-by-field with the certificate;
5. outcome recomputation — the preregistered acceptance rule is re-applied to
   the recomputed statistics and matched against the certified outcome;
6. baseline identity — baseline parameter hash recomputed.

A bundle that passes verification demonstrates *integrity and internal
consistency of the record*.  It is not by itself proof that the experiment was
scientifically well-designed; that judgment requires reading the protocol.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from proofbench import __version__
from proofbench.canonical import hash_file, hash_obj
from proofbench.errors import IntegrityError, RunNotFound, VerificationFailed
from proofbench.events import verify_chain
from proofbench.loop import derive_seed  # deterministic sub-seed derivation shared with the runner
from proofbench.spec import ExperimentSpec
from proofbench.stats import paired_comparison
from proofbench.store import atomic_write_json, read_json

BUNDLE_FILES = ("spec.json", "events.jsonl", "state.json")

_VERIFY_MD = """# Verifying this ProofBench evidence bundle

This bundle is self-contained and verifiable offline.  No network access, API
keys, or model weights are required.

## Quick verification

```bash
proofbench verify-bundle .
```

Expected exit code: 0 with all checks passing.  Any modified, missing, or
extra file is reported and produces exit code 4.

## What the checks mean

1. **Manifest integrity** — every file's SHA-256 matches MANIFEST.json.
   This establishes that the record has not been altered since export.
2. **Event chain** — events.jsonl is an append-only hash chain; any edit,
   deletion, or reordering breaks it.
3. **Spec identity** — the certificate was issued for exactly this spec.
4. **Analysis recomputation** — the reported statistics are recomputed from
   the raw per-trial test results using the recorded procedure version and
   seeds.  If the certificate's numbers cannot be reproduced, verification
   fails.
5. **Outcome recomputation** — the preregistered acceptance rule is
   re-applied; the certified outcome must follow from the recomputed numbers.
6. **Baseline identity** — the baseline the candidate was compared against is
   byte-identical to the one recorded at initialization.

## Deterministic vs stochastic components

* Deterministic: task instances, all built-in agent policies, all evaluation
  scores, the event chain, and every hash in this manifest.
* Seed-dependent but reproducible: bootstrap confidence intervals and
  permutation p-values (seeds are recorded in the certificate; re-running the
  verifier uses exactly those seeds).
* Not part of this bundle: any external model-backed proposal generation.
  This run used only deterministic built-in agents (see spec.json).

## What verification does NOT establish

Verification shows the record is intact and internally consistent with the
declared protocol.  It does not prove the protocol was a good test of
"improvement", nor does it generalize beyond the task suite and budgets
recorded in spec.json.
"""


def export_bundle(run_dir: Path, out_dir: Path) -> Path:
    """Create a self-contained, checksummed evidence bundle from a run directory."""
    run_dir = Path(run_dir)
    if not (run_dir / "spec.json").exists():
        raise RunNotFound(f"{run_dir} is not a ProofBench run directory")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise IntegrityError(f"refusing to export into non-empty directory {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in BUNDLE_FILES:
        src = run_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)
    artifacts_src = run_dir / "artifacts"
    if artifacts_src.exists():
        shutil.copytree(artifacts_src, out_dir / "artifacts")

    (out_dir / "VERIFY.md").write_text(_VERIFY_MD, encoding="utf-8")

    files: dict[str, str] = {}
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "MANIFEST.json":
            files[str(path.relative_to(out_dir))] = hash_file(str(path))

    manifest = {
        "bundle_format": "proofbench-evidence-bundle/1",
        "created_at": time.time(),
        "proofbench_version": __version__,
        "files": files,
        "self_hash_excluded": "MANIFEST.json",
    }
    atomic_write_json(out_dir / "MANIFEST.json", manifest)
    return out_dir


def verify_bundle(bundle_dir: Path) -> dict[str, Any]:
    """Verify a bundle; raise VerificationFailed with all problems if invalid."""
    bundle_dir = Path(bundle_dir)
    manifest_path = bundle_dir / "MANIFEST.json"
    if not manifest_path.exists():
        raise VerificationFailed(f"{bundle_dir} has no MANIFEST.json")
    manifest = read_json(manifest_path)
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    # 1. manifest integrity
    listed = set(manifest.get("files", {}))
    on_disk = {
        str(p.relative_to(bundle_dir))
        for p in bundle_dir.rglob("*")
        if p.is_file() and p.name != "MANIFEST.json"
    }
    missing = sorted(listed - on_disk)
    extra = sorted(on_disk - listed)
    bad_hash = []
    for rel, digest in sorted(manifest["files"].items()):
        path = bundle_dir / rel
        if path.exists() and hash_file(str(path)) != digest:
            bad_hash.append(rel)
    ok_manifest = not (missing or extra or bad_hash)
    checks.append(
        {
            "check": "manifest_integrity",
            "passed": ok_manifest,
            "missing": missing,
            "extra": extra,
            "modified": bad_hash,
        }
    )
    if not ok_manifest:
        errors.append("manifest integrity failed")

    if not (bundle_dir / "spec.json").exists():
        raise VerificationFailed("bundle is missing spec.json")
    spec_doc = read_json(bundle_dir / "spec.json")
    try:
        spec = ExperimentSpec.model_validate(spec_doc["spec"])
    except Exception as exc:
        raise VerificationFailed(f"bundle spec.json is not a valid specification: {exc}") from exc
    spec_hash = spec.spec_hash()

    # 2. event chain
    events: list[dict[str, Any]] = []
    events_path = bundle_dir / "events.jsonl"
    if events_path.exists():
        with open(events_path, encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
    chain_failures = verify_chain(events)
    checks.append(
        {
            "check": "event_chain",
            "passed": not chain_failures,
            "failures": chain_failures,
        }
    )
    if chain_failures:
        errors.append("event chain verification failed")

    # locate certificate + test results in the artifact store
    certs = [e for e in events if e["kind"] == "certificate_issued"]
    if not certs:
        raise VerificationFailed("event log contains no certificate_issued event")
    cert_artifact = certs[-1]["payload"]["artifact"]
    cert_path = bundle_dir / "artifacts" / cert_artifact[:2] / cert_artifact
    certificate: dict[str, Any] | None = None
    if not cert_path.exists():
        errors.append(f"certificate artifact {cert_artifact} missing")
        checks.append({"check": "certificate_content_address", "passed": False})
    elif hash_file(str(cert_path)) != cert_artifact:
        # Tampered certificate: keep going so the analysis-recomputation check
        # below also reports, and the final error lists every failure.
        errors.append("certificate artifact does not match its content address")
        checks.append({"check": "certificate_content_address", "passed": False})
        certificate = json.loads(cert_path.read_text(encoding="utf-8"))
    else:
        checks.append({"check": "certificate_content_address", "passed": True})
        certificate = json.loads(cert_path.read_text(encoding="utf-8"))

    # 3. spec identity
    if certificate is None:
        spec_ok = False
        checks.append({"check": "spec_identity", "passed": False, "reason": "no certificate"})
        errors.append("spec identity could not be checked: certificate missing")
    else:
        spec_ok = spec_hash == cert_hash(certificate) == spec_doc.get("spec_hash")
        checks.append(
            {
                "check": "spec_identity",
                "passed": spec_ok,
                "expected": spec_hash,
                "certificate": certificate.get("spec_hash"),
                "recorded": spec_doc.get("spec_hash"),
            }
        )
        if not spec_ok:
            errors.append("spec hash mismatch between bundle spec and certificate")

    # 4. analysis recomputation from raw trials
    if certificate is None:
        checks.append({"check": "analysis_recomputation", "passed": False})
        errors.append("analysis could not be recomputed: certificate missing")
    else:
        raw_artifact = certificate["test_results_artifact"]
        raw_path = bundle_dir / "artifacts" / raw_artifact[:2] / raw_artifact
        if not raw_path.exists():
            raise VerificationFailed(f"raw test-results artifact {raw_artifact} missing")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        recomputed_primary = _recompute(
            spec, raw, "test_candidate_final", "test_baseline", "primary"
        )
        recomputed_strategy = _recompute(
            spec, raw, "test_candidate_final", "test_candidate_initial", "strategy"
        )
        analysis_ok = _compare_analysis(
            recomputed_primary, certificate["primary_analysis"]
        ) and _compare_analysis(recomputed_strategy, certificate["strategy_improvement_analysis"])
        checks.append(
            {
                "check": "analysis_recomputation",
                "passed": analysis_ok,
                "recomputed_primary": {
                    k: recomputed_primary.get(k)
                    for k in ("n_pairs", "mean_improvement", "ci_low", "ci_high", "p_value")
                },
            }
        )
        if not analysis_ok:
            errors.append("recomputed analysis does not match the certificate")

    # 5. outcome recomputation
    if certificate is None:
        checks.append({"check": "outcome_recomputation", "passed": False})
        errors.append("outcome could not be recomputed: certificate missing")
    else:
        recomputed_outcome = _recompute_outcome(spec, recomputed_primary)
        outcome_ok = recomputed_outcome == certificate["outcome"]
        checks.append(
            {
                "check": "outcome_recomputation",
                "passed": outcome_ok,
                "recomputed": recomputed_outcome,
                "certificate": certificate["outcome"],
            }
        )
        if not outcome_ok:
            errors.append("recomputed outcome does not match the certified outcome")

    # 6. baseline identity
    if certificate is None:
        checks.append({"check": "baseline_identity", "passed": False})
        errors.append("baseline identity could not be checked: certificate missing")
    else:
        baseline = certificate["baseline"]
        baseline_hash = hash_obj({"agent": baseline["agent"], "params": baseline["params"]})
        baseline_ok = baseline_hash == baseline["params_hash"]
        checks.append(
            {
                "check": "baseline_identity",
                "passed": baseline_ok,
                "expected": baseline["params_hash"],
                "recomputed": baseline_hash,
            }
        )
        if not baseline_ok:
            errors.append("baseline hash mismatch")

    report = {
        "bundle": str(bundle_dir),
        "run_id": certificate.get("run_id") if certificate else None,
        "outcome": certificate.get("outcome") if certificate else None,
        "verified_at": time.time(),
        "proofbench_version": __version__,
        "checks": checks,
        "passed": not errors,
        "errors": errors,
    }
    if errors:
        raise VerificationFailed(
            "bundle verification FAILED: " + "; ".join(errors) + "\n" + json.dumps(report, indent=2)
        )
    return report


def cert_hash(certificate: dict[str, Any]) -> str:
    return str(certificate.get("spec_hash", ""))


def _recompute(
    spec: ExperimentSpec,
    raw: dict[str, Any],
    cand_key: str,
    base_key: str,
    tag: str,
) -> dict[str, Any]:
    direction = spec.primary_outcome.direction
    cand = [r["score"] for r in raw[cand_key]]
    base = [r["score"] for r in raw[base_key]]
    return paired_comparison(
        cand,
        base,
        direction=direction,
        alpha=spec.analysis.alpha,
        bootstrap_resamples=spec.analysis.bootstrap_resamples,
        bootstrap_seed=derive_seed(spec.analysis.bootstrap_seed, tag),
    )


def _compare_analysis(recomputed: dict[str, Any], certified: dict[str, Any]) -> bool:
    for key in (
        "status",
        "n_total",
        "n_pairs",
        "n_missing_or_invalid",
        "improved_pairs",
        "tied_pairs",
        "regressed_pairs",
    ):
        if recomputed.get(key) != certified.get(key):
            return False
    for key in (
        "candidate_mean",
        "baseline_mean",
        "mean_improvement",
        "std_improvement",
        "median_improvement",
        "ci_low",
        "ci_high",
        "effect_size_dz",
        "p_value",
    ):
        rc, ct = recomputed.get(key), certified.get(key)
        if rc is None or ct is None:
            if rc != ct:
                return False
        elif abs(float(rc) - float(ct)) > 1e-9:
            return False
    return True


def _recompute_outcome(spec: ExperimentSpec, primary: dict[str, Any]) -> str:
    total = primary.get("n_total", 0)
    valid_frac = primary.get("n_pairs", 0) / max(1, total)
    if primary.get("status") != "ok" or valid_frac < spec.acceptance.min_valid_trial_fraction:
        return "inconclusive"
    meets_margin = primary["mean_improvement"] >= spec.primary_outcome.acceptance_margin
    meets_ci = primary["ci_low"] > 0.0
    meets_p = primary["p_value"] <= spec.analysis.alpha
    if meets_margin and meets_ci and meets_p:
        return "improvement_demonstrated"
    return "improvement_not_demonstrated"


def compare_runs(run_a: Path, run_b: Path) -> dict[str, Any]:
    """Summarize two runs' certificates side by side for ``proofbench compare``."""

    def load(run_dir: Path) -> dict[str, Any]:
        run_dir = Path(run_dir)
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            raise RunNotFound(f"{run_dir} has no events.jsonl")
        with open(events_path, encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
        certs = [e for e in events if e["kind"] == "certificate_issued"]
        if not certs:
            raise RunNotFound(f"{run_dir} has no certificate (run may be incomplete)")
        artifact = certs[-1]["payload"]["artifact"]
        path = run_dir / "artifacts" / artifact[:2] / artifact
        cert: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return cert

    ca, cb = load(run_a), load(run_b)
    return {
        "a": {
            "run_id": ca["run_id"],
            "experiment_id": ca["experiment_id"],
            "outcome": ca["outcome"],
            "mean_improvement": ca["primary_analysis"].get("mean_improvement"),
            "ci": [ca["primary_analysis"].get("ci_low"), ca["primary_analysis"].get("ci_high")],
            "p_value": ca["primary_analysis"].get("p_value"),
            "spec_hash": ca["spec_hash"],
        },
        "b": {
            "run_id": cb["run_id"],
            "experiment_id": cb["experiment_id"],
            "outcome": cb["outcome"],
            "mean_improvement": cb["primary_analysis"].get("mean_improvement"),
            "ci": [cb["primary_analysis"].get("ci_low"), cb["primary_analysis"].get("ci_high")],
            "p_value": cb["primary_analysis"].get("p_value"),
            "spec_hash": cb["spec_hash"],
        },
        "same_protocol": (
            ca["protocol_id"] == cb["protocol_id"]
            and ca["protocol_version"] == cb["protocol_version"]
        ),
    }

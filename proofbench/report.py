"""Markdown report generation for a run.

The report presents the certificate, the primary analysis, strategy-vs-inference
decomposition, regression checks, resource accounting, quarantined proposals,
and — explicitly — negative or inconclusive outcomes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from proofbench.errors import RunNotFound
from proofbench.store import read_json


def _load_certificate(run_dir: Path) -> dict[str, Any]:
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        raise RunNotFound(f"{run_dir} is not a ProofBench run directory")
    with open(events_path, encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    certs = [e for e in events if e["kind"] == "certificate_issued"]
    if not certs:
        raise RunNotFound(
            f"run {run_dir} has no certificate; the run may be incomplete (use `proofbench resume`)"
        )
    artifact = certs[-1]["payload"]["artifact"]
    path = run_dir / "artifacts" / artifact[:2] / artifact
    cert: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return cert


def _fmt(v: Any, digits: int = 4) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def generate_report(run_dir: Path) -> str:
    cert = _load_certificate(Path(run_dir))
    state_path = Path(run_dir) / "state.json"
    state = read_json(state_path) if state_path.exists() else {}
    pa = cert["primary_analysis"]
    sa = cert["strategy_improvement_analysis"]

    lines: list[str] = []
    add = lines.append
    add(f"# ProofBench report — {cert['run_id']}")
    add("")
    add(f"**Experiment:** {cert['experiment_id']}  ")
    add(f"**Protocol:** {cert['protocol_id']} v{cert['protocol_version']}  ")
    add(f"**Spec hash:** `{cert['spec_hash']}`  ")
    add(f"**Issued by:** {cert['verification']['verifier']}")
    add("")
    add("## Outcome")
    add("")
    add(f"**{cert['outcome'].replace('_', ' ').upper()}**")
    add("")
    for reason in cert.get("outcome_reasons", []):
        add(f"- {reason}")
    add("")
    add("## Hypothesis (preregistered)")
    add("")
    add(f"> {cert['hypothesis']}")
    add("")
    add("## Primary outcome — held-out test instances")
    add("")
    add(f"- metric: `{cert['primary_outcome']['metric']}` ({cert['primary_outcome']['direction']})")
    add(
        f"- paired instances: {pa.get('n_pairs')} valid "
        f"({pa.get('n_missing_or_invalid')} missing/invalid)"
    )
    add(
        f"- candidate mean: {_fmt(pa.get('candidate_mean'))}, "
        f"baseline mean: {_fmt(pa.get('baseline_mean'))}"
    )
    add(
        f"- mean improvement: **{_fmt(pa.get('mean_improvement'))}** "
        f"(95% CI [{_fmt(pa.get('ci_low'))}, {_fmt(pa.get('ci_high'))}])"
    )
    add(
        f"- paired Cohen's dz: {_fmt(pa.get('effect_size_dz'))}, "
        f"permutation p = {_fmt(pa.get('p_value'))}"
    )
    add(
        f"- pairs improved / tied / regressed: {pa.get('improved_pairs')} / "
        f"{pa.get('tied_pairs')} / {pa.get('regressed_pairs')}"
    )
    add("")
    add("## Inference gain vs persistent strategy improvement")
    add("")
    add(
        "The candidate's *final accepted parameters* are compared against its own "
        "*initial parameters* on the same held-out instances. A positive difference "
        "here is evidence of persistent strategy improvement within this run; the "
        "candidate-vs-baseline difference alone would not distinguish this from a "
        "lucky initial configuration (inference-time gain)."
    )
    add("")
    add(
        f"- final-vs-initial mean improvement: **{_fmt(sa.get('mean_improvement'))}** "
        f"(95% CI [{_fmt(sa.get('ci_low'))}, {_fmt(sa.get('ci_high'))}]), "
        f"p = {_fmt(sa.get('p_value'))}"
    )
    add("")
    add("## Regression checks (per task family)")
    add("")
    for rc in cert.get("regression_checks", []):
        flag = "REGRESSION" if rc["regression_detected"] else "ok"
        add(
            f"- `{rc['family']}`: mean improvement {_fmt(rc['mean_improvement'])} "
            f"[{_fmt(rc['ci_low'])}, …], regressed pairs {rc['regressed_pairs']} — {flag}"
        )
    add("")
    add("## Candidate lineage")
    add("")
    for entry in cert.get("candidate_lineage", []):
        params_json = json.dumps(entry["params"], sort_keys=True)
        add(f"- round {entry['round']}: {entry['status']} — params `{params_json}`")
    add("")
    add(f"Quarantined (rejected, retained) proposals: {cert.get('quarantined_proposals')}")
    add("")
    add("## Resource accounting")
    add("")
    measured = cert["budget"]["measured"]
    add(
        f"- evaluations per instance (matched budget): {cert['budget']['evaluations_per_instance']}"
    )
    add(f"- rounds completed: {cert.get('rounds_completed')} / {cert['budget']['max_rounds']}")
    add(f"- episodes run: {measured['episodes']}")
    add(f"- wall time: {measured['wall_seconds']:.2f} s, CPU time: {measured['cpu_seconds']:.2f} s")
    add("")
    add("## Baseline")
    add("")
    b = cert["baseline"]
    add(f"- `{b['name']}` (agent `{b['agent']}`), params hash `{b['params_hash'][:16]}…`")
    add(f"- params: `{json.dumps(b['params'], sort_keys=True)}`")
    add("")
    add("## What this certificate does and does not establish")
    add("")
    add(
        "This certificate establishes that, under the recorded protocol, task "
        "suite, budgets, and seeds, the recorded improvement (or its absence) is "
        "an accurate property of the recorded artifacts, and that the evidence "
        "record is intact and internally consistent. It does **not** establish "
        "general intelligence, recursive self-improvement, or performance "
        "outside this task family and budget."
    )
    add("")
    if state:
        add("<details><summary>Machine-readable certificate reference</summary>")
        add("")
        add(f"- test results artifact: `{cert['test_results_artifact']}`")
        add(f"- analysis procedure: `{cert['analysis_procedure']}`")
        add("</details>")
    add("")
    return "\n".join(lines)

"""Long-horizon loop: end-to-end, checkpoint/resume, integrity guards."""

import json
from pathlib import Path

import pytest

from proofbench.bundle import export_bundle, verify_bundle
from proofbench.canonical import hash_obj
from proofbench.errors import IntegrityError
from proofbench.events import EventLog, verify_chain
from proofbench.loop import CandidateProposerer, Context, run_experiment
from proofbench.spec import load_spec
from proofbench.store import read_json
from tests.conftest import make_spec_dict


def _ctx(tmp_path: Path, spec_dict: dict, run_id: str = "r1") -> Context:  # type: ignore[no-untyped-def]
    spec = load_spec(spec_dict)
    return Context(spec=spec, run_dir=tmp_path / run_id, run_id=run_id, run_seed=99)


def test_end_to_end_run_issues_certificate(tmp_path: Path, tiny_spec) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(tmp_path, tiny_spec.model_dump(mode="json"))
    outcome = run_experiment(ctx)
    cert = outcome["certificate"]
    assert cert["outcome"] in {
        "improvement_demonstrated",
        "improvement_not_demonstrated",
        "inconclusive",
    }
    assert cert["primary_analysis"]["n_total"] == 4  # 4 held-out test instances
    assert (ctx.run_dir / "state.json").exists()
    events = EventLog(ctx.run_dir / "events.jsonl").read_all()
    assert verify_chain(events) == []
    kinds = [e["kind"] for e in events]
    assert "run_initialized" in kinds
    assert "certificate_issued" in kinds


def test_baseline_is_hash_verified_and_recorded(tmp_path: Path, tiny_spec) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(tmp_path, tiny_spec.model_dump(mode="json"), "r2")
    outcome = run_experiment(ctx)
    cert = outcome["certificate"]
    expected = hash_obj(
        {"agent": tiny_spec.baselines[0].agent, "params": tiny_spec.baselines[0].params}
    )
    assert cert["baseline"]["params_hash"] == expected


def test_resume_after_interruption(tmp_path: Path, tiny_spec, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(tmp_path, tiny_spec.model_dump(mode="json"), "r3")
    # Interrupt after the first checkpoint by making suite runs fail mid-way.
    import proofbench.loop as loop_mod

    original = loop_mod._run_suite
    calls = {"n": 0}

    def flaky(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 3:
            raise KeyboardInterrupt("simulated interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(loop_mod, "_run_suite", flaky)
    with pytest.raises(KeyboardInterrupt):
        run_experiment(ctx)
    events = EventLog(ctx.run_dir / "events.jsonl").read_all()
    assert [e["kind"] for e in events if e["kind"] == "run_interrupted"]

    monkeypatch.setattr(loop_mod, "_run_suite", original)
    outcome = run_experiment(ctx)  # resume
    events = EventLog(ctx.run_dir / "events.jsonl").read_all()
    assert "run_resumed" in [e["kind"] for e in events]
    assert verify_chain(events) == []
    assert outcome["certificate"]["outcome"] in {
        "improvement_demonstrated",
        "improvement_not_demonstrated",
        "inconclusive",
    }


def test_resume_refuses_mixed_specs(tmp_path: Path, tiny_spec) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(tmp_path, tiny_spec.model_dump(mode="json"), "r4")
    run_experiment(ctx)
    # Tamper: change the spec after the run completed.
    other = load_spec(make_spec_dict(budget={"evaluations_per_instance": 16, "max_rounds": 1}))
    ctx2 = Context(spec=other, run_dir=ctx.run_dir, run_id="r4", run_seed=99)
    with pytest.raises(IntegrityError, match="different specification"):
        run_experiment(ctx2)


def test_cannot_alter_baseline_after_initialization(tmp_path: Path, tiny_spec) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(tmp_path, tiny_spec.model_dump(mode="json"), "r5")
    run_experiment(ctx)
    # Simulate an in-run baseline swap by corrupting the stored baseline hash.
    state_path = ctx.run_dir / "state.json"
    state = read_json(state_path)
    state["baseline_hash"] = "f" * 64
    state["phase"] = "final_eval"
    state["finalized"] = False
    state["test_results"] = None
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(IntegrityError, match="baseline"):
        run_experiment(ctx)


def test_certificate_rejects_forged_numbers(tmp_path: Path, tiny_spec) -> None:  # type: ignore[no-untyped-def]
    ctx = _ctx(tmp_path, tiny_spec.model_dump(mode="json"), "r6")
    outcome = run_experiment(ctx)
    bundle = export_bundle(ctx.run_dir, tmp_path / "bundle")
    # Forge the certificate's mean improvement.
    cert_path = (
        bundle / "artifacts" / outcome["certificate_artifact"][:2] / outcome["certificate_artifact"]
    )
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    cert["primary_analysis"]["mean_improvement"] = 12345.0

    # Re-author the bundle coherently so that the *byte-level* checks all pass
    # and the analysis-recomputation check is the one that must catch the
    # forgery: the artifact filename is its content address, the event log is
    # hash-chained, and the manifest must agree with both.
    from proofbench.canonical import canonical_json, hash_file, sha256_hex
    from proofbench.events import GENESIS

    new_bytes = canonical_json(cert).encode()
    new_hash = sha256_hex(new_bytes)
    cert_path.unlink()
    new_dir = bundle / "artifacts" / new_hash[:2]
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / new_hash).write_bytes(new_bytes)

    events_path = bundle / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
    for ev in events:
        if ev["kind"] == "certificate_issued":
            ev["payload"]["artifact"] = new_hash
    # Re-chain: chain_hash covers (prev, payload); recompute for all events.
    prev = GENESIS
    for ev in events:
        ev["prev"] = prev
        ev["chain_hash"] = sha256_hex(f"{prev}\n{canonical_json(ev['payload'])}".encode())
        prev = ev["chain_hash"]
    events_path.write_text("".join(canonical_json(ev) + "\n" for ev in events), encoding="utf-8")

    manifest_path = bundle / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_rel = f"artifacts/{outcome['certificate_artifact'][:2]}/{outcome['certificate_artifact']}"
    del manifest["files"][old_rel]
    manifest["files"][f"artifacts/{new_hash[:2]}/{new_hash}"] = new_hash
    manifest["files"]["events.jsonl"] = hash_file(str(events_path))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(Exception, match="verification FAILED"):
        verify_bundle(bundle)


def test_proposerer_respects_bounds_and_cycles_coordinates() -> None:
    from proofbench.spec import ParamBound

    bounds = [
        ParamBound(name="a", kind="float", low=0.0, high=1.0),
        ParamBound(name="b", kind="int", low=1, high=5),
    ]
    p = CandidateProposerer(bounds, seed=1)
    current = {"a": 0.5, "b": 3}
    seen = []
    for r in range(10):
        proposal = p.propose(current, r)
        if proposal is None:
            break
        for k, v in proposal.items():
            b = next(x for x in bounds if x.name == k)
            assert b.low <= v <= b.high
        seen.append(proposal)
    assert seen  # at least one proposal before exhaustion

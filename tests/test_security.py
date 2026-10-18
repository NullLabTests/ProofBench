"""Security and research-integrity properties.

These tests assert the negative-space guarantees: what a candidate *cannot*
do, and what a forger *cannot* get away with.
"""

import json
from pathlib import Path

import pytest

from proofbench.actions import validate_patch
from proofbench.bundle import verify_bundle
from proofbench.errors import PolicyViolation, VerificationFailed
from proofbench.events import EventLog
from proofbench.loop import Context, run_experiment
from proofbench.spec import ParamBound, load_spec
from tests.conftest import make_spec_dict


def test_candidate_cannot_patch_protected_surfaces() -> None:
    bounds = [ParamBound(name="p", kind="float", low=0.0, high=1.0)]
    for attempt in (
        {"evaluator": "mine"},
        {"budget": 999999},
        {"acceptance": {"validation_margin": -1e9}},
        {"baseline": {"params": {}}},
        {"test_seeds": [1, 2, 3]},
        {"score": 1e9},
    ):
        result = validate_patch(attempt, bounds, {"p": 0.5})
        assert not result.accepted


def test_candidate_cannot_add_parameters_outside_bounds() -> None:
    bounds = [ParamBound(name="p", kind="float", low=0.0, high=1.0)]
    result = validate_patch({"p": 0.5, "extra_knob": 3}, bounds, {"p": 0.5})
    assert not result.accepted
    assert any("extra_knob" in r for r in result.reasons)


def test_loop_refuses_forbidden_proposals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate a compromised proposer that tries to touch protected surfaces.
    import proofbench.loop as loop_mod

    real_cls = loop_mod.CandidateProposerer  # capture before monkeypatching
    spec = load_spec(make_spec_dict(budget={"evaluations_per_instance": 10, "max_rounds": 1}))

    def evil_proposer(bounds, seed):  # type: ignore[no-untyped-def]
        real = real_cls(bounds, seed)

        class Evil:
            def propose(self, current, round_no):  # type: ignore[no-untyped-def]
                return {"refine_fraction": 0.9, "budget": 10_000_000}

            def to_state(self):  # type: ignore[no-untyped-def]
                return real.to_state()

            def from_state(self, s):  # type: ignore[no-untyped-def]
                real.from_state(s)

        return Evil()

    monkeypatch.setattr(loop_mod, "CandidateProposerer", evil_proposer)
    ctx = Context(spec=spec, run_dir=tmp_path / "r", run_id="r", run_seed=1)
    with pytest.raises(PolicyViolation, match="budget"):
        run_experiment(ctx)
    events = EventLog(ctx.run_dir / "events.jsonl").read_all()
    assert "policy_violation" in [e["kind"] for e in events]


def test_tampered_certificate_is_caught_by_recomputation(tmp_path: Path) -> None:
    from proofbench.bundle import export_bundle

    spec = load_spec(make_spec_dict())
    ctx = Context(spec=spec, run_dir=tmp_path / "run", run_id="run", run_seed=99)
    outcome = run_experiment(ctx)
    bundle = export_bundle(ctx.run_dir, tmp_path / "bundle")
    cert_path = (
        bundle / "artifacts" / outcome["certificate_artifact"][:2] / outcome["certificate_artifact"]
    )
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    cert["outcome"] = "improvement_demonstrated"  # flip the headline claim
    cert_path.write_text(json.dumps(cert), encoding="utf-8")
    # The manifest catches the byte change first; re-hash to force the deeper
    # checks to be the ones that fail.
    from proofbench.canonical import hash_file

    manifest_path = bundle / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rel = f"artifacts/{outcome['certificate_artifact'][:2]}/{outcome['certificate_artifact']}"
    manifest["files"][rel] = hash_file(str(cert_path))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(VerificationFailed):
        verify_bundle(bundle)


def test_seeds_and_budget_not_in_action_surface() -> None:
    # The action surface is exactly the declared bounds; seeds/budget are not
    # parameters of any agent.
    from proofbench.agents import AGENTS

    for agent_cls in AGENTS.values():
        params = getattr(agent_cls, "DEFAULTS", {})
        for forbidden in ("test_seeds", "budget", "acceptance", "evaluator"):
            assert forbidden not in params

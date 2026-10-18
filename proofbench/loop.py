"""Long-horizon improvement loop.

The stateful experimental loop (see docs/architecture.md):

1. Initialize candidate (mutable within bounds) and immutable baseline.
2. Each round: run the candidate on train instances (learning curve record),
   propose one bounded parameter change, validate it against the action
   policy, evaluate on *validation* instances, then accept / reject /
   quarantine per the preregistered acceptance policy.
3. Checkpoint atomically after every round; runs are resumable.
4. After the round budget or stopping condition, evaluate the final candidate,
   the *initial* candidate, and the immutable baseline on held-out test
   instances, compute the preregistered primary outcome, and issue a
   certificate with one of three outcomes.

Integrity properties:

* The baseline's parameters are hashed at initialization and re-verified at
  final evaluation; a mismatch aborts the run.
* Candidates only ever propose parameter patches inside declared bounds;
  violations are audited and quarantined, never applied.
* Scores are produced only by the independent evaluator; candidates cannot
  supply, override, or hide results.
"""

from __future__ import annotations

import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proofbench import ANALYSIS_PROCEDURE_VERSION, CERTIFICATE_VERSION, __version__
from proofbench.actions import audit_forbidden_keys, validate_patch
from proofbench.agents import AGENTS, Agent
from proofbench.canonical import hash_obj
from proofbench.errors import IntegrityError, PolicyViolation, SpecValidationError
from proofbench.evaluator import EpisodeResult, Evaluator
from proofbench.events import EventLog
from proofbench.spec import ExperimentSpec, ParamBound
from proofbench.stats import paired_comparison
from proofbench.store import ArtifactStore, atomic_write_json, read_json
from proofbench.tasks.families import FAMILIES


def derive_seed(run_seed: int, *parts: object) -> int:
    """Deterministic sub-seed derivation independent of Python hash randomization."""
    import hashlib

    material = ":".join([str(run_seed), *[str(p) for p in parts]])
    return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big") % (2**31 - 1)


@dataclass
class Context:
    spec: ExperimentSpec
    run_dir: Path
    run_id: str
    run_seed: int

    @property
    def events(self) -> EventLog:
        return EventLog(self.run_dir / "events.jsonl")

    @property
    def artifacts(self) -> ArtifactStore:
        return ArtifactStore(self.run_dir / "artifacts")

    @property
    def state_path(self) -> Path:
        return self.run_dir / "state.json"


class CandidateProposerer:
    """Deterministic bounded proposal strategy (the candidate's self-modifier).

    Coordinate search over declared bounds: one parameter per round, direction
    alternating based on prior accept/reject feedback for that coordinate.
    This is a *fixed algorithm* seeded by the run seed — the candidate's
    "strategy" being tested is the AdaptiveSearch parameter surface; the
    proposer itself cannot be modified by the candidate.
    """

    def __init__(self, bounds: list[ParamBound], seed: int) -> None:
        self.bounds = {b.name: b for b in bounds}
        self.order = [b.name for b in bounds]
        self.seed = seed
        # Per-coordinate set of already-tried (name, value) proposals. A fresh
        # set per coordinate is required — dict.fromkeys would share one set.
        # Categorical coordinates store hash strings; numeric ones store floats.
        self.tried: dict[str, set[tuple[str, float | str]]] = {n: set() for n in self.order}
        self.direction: dict[str, float] = dict.fromkeys(self.order, 1.0)

    def propose(self, current: dict[str, Any], round_no: int) -> dict[str, Any] | None:
        if not self.order:
            return None
        for offset in range(len(self.order)):
            name = self.order[(round_no + offset) % len(self.order)]
            b = self.bounds[name]
            if b.kind == "categorical":
                choices = [c for c in (b.choices or []) if c != current.get(name)]
                if not choices:
                    continue
                pick = choices[derive_seed(self.seed, "cat", name, round_no) % len(choices)]
                key = (name, hash_obj(pick))
                if key in self.tried[name]:
                    continue
                self.tried[name].add(key)
                return {name: pick}
            low, high = float(b.low), float(b.high)  # type: ignore[arg-type]
            span = high - low
            for direction in (self.direction[name], -self.direction[name]):
                base = float(current.get(name, low))
                raw = base + direction * 0.25 * span
                value = min(high, max(low, raw))
                if b.kind == "int":
                    value = float(round(value))
                if value == base:
                    continue
                num_key = (name, value)
                if num_key in self.tried[name]:
                    continue
                self.tried[name].add(num_key)
                if direction < 0:
                    self.direction[name] = -1.0
                return {name: value}
        return None

    def to_state(self) -> dict[str, Any]:
        return {
            "tried": {k: sorted(t) for k, t in self.tried.items()},
            "direction": dict(self.direction),
        }

    def from_state(self, state: dict[str, Any]) -> None:
        self.tried = {k: set(map(tuple, v)) for k, v in state.get("tried", {}).items()}
        for n in self.order:
            self.tried.setdefault(n, set())
        self.direction.update(state.get("direction", {}))


def _instance_id(task_index: int, family: str, seed: int) -> str:
    return f"t{task_index}-{family}-s{seed}"


def _build_agent(agent_type: str, params: dict[str, Any]) -> Agent:
    if agent_type not in AGENTS:
        raise SpecValidationError(f"unknown agent type {agent_type!r}; available: {sorted(AGENTS)}")
    return AGENTS[agent_type](params)


def _run_suite(
    ctx: Context,
    agent_type: str,
    params: dict[str, Any],
    seeds: list[int],
    label: str,
) -> list[EpisodeResult]:
    """Run one method over every task in the suite on the given split seeds."""
    evaluator = Evaluator()
    results: list[EpisodeResult] = []
    for ti, task in enumerate(ctx.spec.tasks):
        family = FAMILIES.get(task.family)
        if family is None:
            raise SpecValidationError(
                f"unknown task family {task.family!r}; available: {sorted(FAMILIES)}"
            )
        if family.version != task.version:
            raise SpecValidationError(
                f"task family {task.family!r} version {family.version!r} does not "
                f"match spec version {task.version!r}"
            )
        for seed in seeds:
            instance = family.sample(seed, dict(task.difficulty))
            iid = _instance_id(ti, task.family, seed)
            agent = _build_agent(agent_type, params)
            rng_seed = derive_seed(ctx.run_seed, label, iid)
            result = evaluator.run_episode(
                family, instance, agent, ctx.spec.budget.evaluations_per_instance, rng_seed, iid
            )
            results.append(result)
    return results


def _mean_score(results: list[EpisodeResult]) -> float | None:
    valid = [r.score for r in results if r.valid]
    return float(sum(valid) / len(valid)) if valid else None


def _valid_fraction(results: list[EpisodeResult]) -> float:
    return sum(1 for r in results if r.valid) / max(1, len(results))


def run_experiment(ctx: Context) -> dict[str, Any]:
    """Execute (or resume) a full experiment and issue the certificate."""
    run_dir = ctx.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    spec_path = run_dir / "spec.json"
    spec_hash = ctx.spec.spec_hash()
    if spec_path.exists():
        stored = read_json(spec_path)
        if stored.get("spec_hash") != spec_hash:
            raise IntegrityError(
                f"run {ctx.run_id} was created from a different specification "
                f"({stored.get('spec_hash')} != {spec_hash}); refusing to mix specs"
            )
    else:
        atomic_write_json(
            spec_path,
            {
                "spec_hash": spec_hash,
                "spec": ctx.spec.model_dump(mode="json"),
                "proofbench_version": __version__,
                "protocol_version": ctx.spec.protocol_version,
            },
        )

    events = ctx.events
    state = _load_or_init_state(ctx, events, spec_hash)

    try:
        if state["phase"] in ("rounds", "final_eval"):
            state = _run_rounds(ctx, state, events)
        if state["phase"] == "final_eval":
            state = _final_evaluation(ctx, state, events)
    except BaseException as exc:
        atomic_write_json(ctx.state_path, state)
        events.append(
            "run_interrupted",
            {"phase": state["phase"], "round": state["round"], "error": repr(exc)},
        )
        raise

    atomic_write_json(ctx.state_path, state)
    certificate = _issue_certificate(ctx, state)
    cert_hash = ctx.artifacts.put_obj(certificate)
    events.append(
        "certificate_issued",
        {
            "artifact": cert_hash,
            "outcome": certificate["outcome"],
        },
    )
    return {
        "run_id": ctx.run_id,
        "run_dir": str(run_dir),
        "certificate": certificate,
        "certificate_artifact": cert_hash,
        "state": state,
    }


def _load_or_init_state(ctx: Context, events: EventLog, spec_hash: str) -> dict[str, Any]:
    if ctx.state_path.exists():
        state: dict[str, Any] = read_json(ctx.state_path)
        if state.get("spec_hash") != spec_hash:
            raise IntegrityError("state.json does not match the current specification")
        events.append("run_resumed", {"phase": state["phase"], "round": state["round"]})
        return state

    baseline = ctx.spec.baselines[0]
    baseline_params_hash = hash_obj({"agent": baseline.agent, "params": baseline.params})
    initial_params = {
        k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
        for k, v in ctx.spec.candidate.params.items()
    }
    state = {
        "run_id": ctx.run_id,
        "spec_hash": spec_hash,
        "run_seed": ctx.run_seed,
        "proofbench_version": __version__,
        "phase": "rounds",
        "round": 0,
        "initial_candidate_params": initial_params,
        "accepted_params": dict(initial_params),
        "accepted_val_mean": None,
        "rounds_without_accept": 0,
        "param_lineage": [{"round": 0, "params": dict(initial_params), "status": "initial"}],
        "quarantine": [],
        "baseline_hash": baseline_params_hash,
        "proposer_state": {"tried": {}, "direction": {}},
        "train_history": [],
        "resource": {"wall_seconds": 0.0, "cpu_seconds": 0.0, "episodes": 0},
        "test_results": None,
        "finalized": False,
    }
    # Verify agent types up front so a bad spec fails before any work.
    _build_agent(ctx.spec.candidate.agent, initial_params)
    for b in ctx.spec.baselines:
        _build_agent(b.agent, b.params)
    for t in ctx.spec.tasks:
        if t.family not in FAMILIES:
            raise SpecValidationError(f"unknown task family {t.family!r}")
    atomic_write_json(ctx.state_path, state)
    events.append(
        "run_initialized",
        {
            "run_id": ctx.run_id,
            "spec_hash": spec_hash,
            "run_seed": ctx.run_seed,
            "baseline": {"name": baseline.name, "params_hash": baseline_params_hash},
            "candidate": {"name": ctx.spec.candidate.name, "params": initial_params},
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "proofbench": __version__,
            },
            "hypothesis": ctx.spec.hypothesis,
        },
    )
    return state


def _run_rounds(ctx: Context, state: dict[str, Any], events: EventLog) -> dict[str, Any]:
    spec = ctx.spec
    bounds: list[ParamBound] = spec.action_bounds
    proposer = CandidateProposerer(bounds, derive_seed(ctx.run_seed, "proposer"))
    if state["proposer_state"]["tried"]:
        proposer.from_state(state["proposer_state"])

    sign = 1.0 if spec.primary_outcome.direction == "higher_is_better" else -1.0

    while state["round"] < spec.budget.max_rounds:
        round_no = state["round"] + 1
        t_wall, t_cpu = time.perf_counter(), time.process_time()

        # (a) Train pass with the accepted candidate (learning-curve record).
        train = _run_suite(
            ctx, spec.candidate.agent, state["accepted_params"], spec.seeds.train_seeds, "train"
        )
        train_mean = _mean_score(train)
        state["resource"]["episodes"] += len(train)
        state["train_history"].append(
            {"round": round_no, "params": dict(state["accepted_params"]), "mean_score": train_mean}
        )

        # (b) Propose one bounded modification.
        proposal = proposer.propose(state["accepted_params"], round_no)
        state["proposer_state"] = proposer.to_state()
        if proposal is None:
            events.append(
                "budget_exhausted",
                {
                    "round": round_no,
                    "reason": "no untried parameter modifications remain within bounds",
                },
            )
            state["phase"] = "final_eval"
            break

        # (c) Validate against the permitted action policy.
        forbidden = audit_forbidden_keys(proposal)
        if forbidden:
            events.append(
                "policy_violation",
                {"round": round_no, "proposal": proposal, "reasons": forbidden},
            )
            raise PolicyViolation(
                f"proposer produced forbidden keys: {forbidden}; this indicates a "
                "bug in the candidate modification pipeline"
            )
        validation = validate_patch(proposal, bounds, state["accepted_params"])
        if not validation.accepted:
            events.append(
                "modification_rejected",
                {"round": round_no, "proposal": proposal, "reasons": validation.reasons},
            )
            state["quarantine"].append(
                {"round": round_no, "proposal": proposal, "reasons": validation.reasons}
            )
            state["round"] = round_no
            state["rounds_without_accept"] += 1
            _checkpoint(ctx, state, events, t_wall, t_cpu)
            continue
        patched_params = validation.normalized

        # (d) Validation evaluation: patched vs currently-accepted params.
        patched_val = _run_suite(
            ctx, spec.candidate.agent, patched_params, spec.seeds.validation_seeds, "validation"
        )
        if state["accepted_val_mean"] is None:
            accepted_val = _run_suite(
                ctx,
                spec.candidate.agent,
                state["accepted_params"],
                spec.seeds.validation_seeds,
                "validation",
            )
            state["accepted_val_mean"] = _mean_score(accepted_val)
        patched_mean = _mean_score(patched_val)
        state["resource"]["episodes"] += len(patched_val)

        # (e) Accept / reject per the preregistered policy.
        ok_frac = _valid_fraction(patched_val) >= spec.acceptance.min_valid_trial_fraction
        improvement = None
        if patched_mean is not None and state["accepted_val_mean"] is not None:
            improvement = sign * (patched_mean - state["accepted_val_mean"])
        accepted = (
            ok_frac and improvement is not None and improvement >= spec.acceptance.validation_margin
        )
        round_record = {
            "round": round_no,
            "proposal": proposal,
            "patched_val_mean": patched_mean,
            "accepted_val_mean": state["accepted_val_mean"],
            "validation_improvement": improvement,
            "valid_fraction": _valid_fraction(patched_val),
            "accepted": accepted,
        }
        state["param_lineage"].append(
            {
                "round": round_no,
                "params": dict(patched_params),
                "status": "accepted" if accepted else "rejected",
            }
        )
        if accepted:
            state["accepted_params"] = patched_params
            state["accepted_val_mean"] = patched_mean
            state["rounds_without_accept"] = 0
            events.append("candidate_accepted", round_record)
        else:
            reason = (
                "below validation margin" if ok_frac else "invalid trial fraction below threshold"
            )
            round_record["reason"] = reason
            events.append("candidate_rejected_quarantined", round_record)
            if spec.acceptance.quarantine_proposals:
                state["quarantine"].append(round_record)
            state["rounds_without_accept"] += 1

        state["round"] = round_no
        no_accept_limit = spec.stopping.stop_if_no_accepts_for_rounds
        if no_accept_limit is not None and state["rounds_without_accept"] >= no_accept_limit:
            events.append(
                "stopping_condition_met",
                {"round": round_no, "reason": "no_accepts_for_rounds", "limit": no_accept_limit},
            )
            state["phase"] = "final_eval"
            _checkpoint(ctx, state, events, t_wall, t_cpu)
            break
        _checkpoint(ctx, state, events, t_wall, t_cpu)

    if state["phase"] == "rounds":
        state["phase"] = "final_eval"
    return state


def _checkpoint(
    ctx: Context,
    state: dict[str, Any],
    events: EventLog,
    t_wall: float,
    t_cpu: float,
) -> None:
    state["resource"]["wall_seconds"] += time.perf_counter() - t_wall
    state["resource"]["cpu_seconds"] += time.process_time() - t_cpu
    atomic_write_json(ctx.state_path, state)
    events.append(
        "checkpoint",
        {"round": state["round"], "phase": state["phase"], "state_hash": hash_obj(state)},
    )


def _final_evaluation(ctx: Context, state: dict[str, Any], events: EventLog) -> dict[str, Any]:
    spec = ctx.spec
    baseline = spec.baselines[0]

    # Baseline immutability re-verification before final scoring.
    current_hash = hash_obj({"agent": baseline.agent, "params": baseline.params})
    if current_hash != state["baseline_hash"]:
        raise IntegrityError(
            "immutable baseline parameters changed during the run; aborting final evaluation"
        )
    events.append("baseline_verified", {"params_hash": current_hash})

    t_wall, t_cpu = time.perf_counter(), time.process_time()
    test_seeds = spec.seeds.test_seeds
    baseline_test = _run_suite(ctx, baseline.agent, baseline.params, test_seeds, "test-baseline")
    final_test = _run_suite(
        ctx, spec.candidate.agent, state["accepted_params"], test_seeds, "test-candidate-final"
    )
    initial_test = _run_suite(
        ctx,
        spec.candidate.agent,
        state["initial_candidate_params"],
        test_seeds,
        "test-candidate-initial",
    )
    state["resource"]["episodes"] += len(baseline_test) + len(final_test) + len(initial_test)
    state["resource"]["wall_seconds"] += time.perf_counter() - t_wall
    state["resource"]["cpu_seconds"] += time.process_time() - t_cpu

    def dump(results: list[EpisodeResult]) -> list[dict[str, Any]]:
        return [
            {
                "instance_id": r.instance_id,
                "family": r.family,
                "score": r.score if r.valid else None,
                "valid": r.valid,
                "error": r.error,
                "steps_used": r.steps_used,
                "budget": r.budget,
                "invalid_actions": r.invalid_actions,
                "wall_seconds": r.wall_seconds,
                "cpu_seconds": r.cpu_seconds,
            }
            for r in results
        ]

    raw = {
        "test_baseline": dump(baseline_test),
        "test_candidate_final": dump(final_test),
        "test_candidate_initial": dump(initial_test),
    }
    raw_artifact = ctx.artifacts.put_obj(raw)
    events.append("test_results_recorded", {"artifact": raw_artifact})
    state["test_results"] = {"artifact": raw_artifact}
    state["phase"] = "done"
    state["finalized"] = True
    return state


def _issue_certificate(ctx: Context, state: dict[str, Any]) -> dict[str, Any]:
    spec = ctx.spec
    raw = ctx.artifacts.get_obj(state["test_results"]["artifact"])
    direction = spec.primary_outcome.direction

    def scores(key: str) -> list[float | None]:
        return [r["score"] for r in raw[key]]

    primary = paired_comparison(
        scores("test_candidate_final"),
        scores("test_baseline"),
        direction=direction,
        alpha=spec.analysis.alpha,
        bootstrap_resamples=spec.analysis.bootstrap_resamples,
        bootstrap_seed=derive_seed(spec.analysis.bootstrap_seed, "primary"),
    )
    strategy = paired_comparison(
        scores("test_candidate_final"),
        scores("test_candidate_initial"),
        direction=direction,
        alpha=spec.analysis.alpha,
        bootstrap_resamples=spec.analysis.bootstrap_resamples,
        bootstrap_seed=derive_seed(spec.analysis.bootstrap_seed, "strategy"),
    )

    total = primary.get("n_total", 0)
    valid_frac = primary.get("n_pairs", 0) / max(1, total)
    meets_margin = (
        primary.get("status") == "ok"
        and primary["mean_improvement"] >= spec.primary_outcome.acceptance_margin
    )
    meets_ci = primary.get("status") == "ok" and primary["ci_low"] > 0.0
    meets_p = primary.get("status") == "ok" and primary["p_value"] <= spec.analysis.alpha
    meets_valid = valid_frac >= spec.acceptance.min_valid_trial_fraction

    if primary.get("status") != "ok" or not meets_valid:
        outcome = "inconclusive"
        reasons = ["insufficient valid held-out pairs to evaluate the primary outcome"]
    elif meets_margin and meets_ci and meets_p:
        outcome = "improvement_demonstrated"
        reasons = ["preregistered acceptance rule satisfied on held-out test instances"]
    else:
        outcome = "improvement_not_demonstrated"
        reasons = []
        if not meets_margin:
            reasons.append(
                f"mean improvement below preregistered margin "
                f"{spec.primary_outcome.acceptance_margin}"
            )
        if not meets_ci:
            reasons.append("confidence interval includes zero")
        if not meets_p:
            reasons.append("permutation p-value above alpha")

    # Regression checks: per-family breakdown of the primary comparison.
    regression_checks: list[dict[str, Any]] = []
    families = sorted({r["family"] for r in raw["test_baseline"]})
    for fam in families:
        fam_c = [r["score"] for r in raw["test_candidate_final"] if r["family"] == fam]
        fam_b = [r["score"] for r in raw["test_baseline"] if r["family"] == fam]
        fam_res = paired_comparison(
            fam_c,
            fam_b,
            direction=direction,
            alpha=spec.analysis.alpha,
            bootstrap_resamples=min(2000, spec.analysis.bootstrap_resamples),
            bootstrap_seed=derive_seed(spec.analysis.bootstrap_seed, fam),
        )
        regression_checks.append(
            {
                "family": fam,
                "mean_improvement": fam_res.get("mean_improvement"),
                "ci_low": fam_res.get("ci_low"),
                "regressed_pairs": fam_res.get("regressed_pairs"),
                "regression_detected": (
                    fam_res.get("status") == "ok" and fam_res.get("mean_improvement", 0.0) < 0.0
                ),
            }
        )

    certificate: dict[str, Any] = {
        "certificate_version": CERTIFICATE_VERSION,
        "analysis_procedure": ANALYSIS_PROCEDURE_VERSION,
        "run_id": ctx.run_id,
        "experiment_id": spec.experiment_id,
        "protocol_id": spec.protocol_id,
        "protocol_version": spec.protocol_version,
        "spec_hash": ctx.spec.spec_hash(),
        "hypothesis": spec.hypothesis,
        "primary_outcome": spec.primary_outcome.model_dump(mode="json"),
        "acceptance_rule": {
            "mean_improvement_margin": spec.primary_outcome.acceptance_margin,
            "ci_must_exclude_zero": True,
            "alpha": spec.analysis.alpha,
            "min_valid_trial_fraction": spec.acceptance.min_valid_trial_fraction,
        },
        "outcome": outcome,
        "outcome_reasons": reasons,
        "primary_analysis": primary,
        "strategy_improvement_analysis": strategy,
        "regression_checks": regression_checks,
        "valid_trial_fraction": valid_frac,
        "budget": {
            "evaluations_per_instance": spec.budget.evaluations_per_instance,
            "max_rounds": spec.budget.max_rounds,
            "measured": dict(state["resource"]),
        },
        "candidate_lineage": state["param_lineage"],
        "accepted_params": state["accepted_params"],
        "initial_params": state["initial_candidate_params"],
        "baseline": {
            "name": spec.baselines[0].name,
            "agent": spec.baselines[0].agent,
            "params": spec.baselines[0].params,
            "params_hash": state["baseline_hash"],
        },
        "rounds_completed": state["round"],
        "quarantined_proposals": len(state["quarantine"]),
        "test_results_artifact": state["test_results"]["artifact"],
        "verification": {
            "verifier": f"proofbench=={__version__}",
            "independently_recomputable_from": "test_results_artifact",
        },
    }
    return certificate

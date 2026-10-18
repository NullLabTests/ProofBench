"""Versioned, machine-readable experiment specifications.

Specifications are validated strictly (extra fields rejected, semantic rules
enforced) *before* execution.  Protocol definitions live here, separate from
execution code; changing scoring or task definitions requires a visible version
bump (``protocol_version`` / per-family ``version``).
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from proofbench.canonical import hash_obj
from proofbench.errors import SpecValidationError

SPEC_SCHEMA_VERSION = "1.0"
PROTOCOL_VERSION = "1.0"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")


def _check_id(v: str) -> str:
    if not _ID_RE.match(v):
        raise ValueError(f"identifier {v!r} must match [a-z0-9][a-z0-9_.-]{{0,127}} (lowercase)")
    return v


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BudgetSpec(Strict):
    """Matched evaluation budget and stopping conditions."""

    evaluations_per_instance: int = Field(ge=1, le=100_000)
    max_rounds: int = Field(ge=1, le=10_000)
    wall_clock_seconds_per_instance: float | None = Field(default=None, gt=0)


class Splits(Strict):
    """Disjoint instance seeds for train / validation / test."""

    train_seeds: list[int] = Field(min_length=1)
    validation_seeds: list[int] = Field(min_length=1)
    test_seeds: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def _disjoint(self) -> Splits:
        all_seeds = self.train_seeds + self.validation_seeds + self.test_seeds
        if len(set(all_seeds)) != len(all_seeds):
            raise ValueError("train/validation/test seeds must be pairwise disjoint")
        return self


class TaskSpec(Strict):
    family: str
    version: str = "1"
    difficulty: dict[str, int | float | str | bool] = Field(default_factory=dict)

    @field_validator("family")
    @classmethod
    def _family_id(cls, v: str) -> str:
        return _check_id(v)

    @field_validator("version")
    @classmethod
    def _version_id(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9_.-]*$", v):
            raise ValueError(f"version {v!r} must match [a-z0-9][a-z0-9_.-]*")
        return v


class ParamBound(Strict):
    """Permitted modification boundary for one candidate parameter."""

    name: str
    kind: Literal["float", "int", "categorical"]
    low: float | None = None
    high: float | None = None
    choices: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _check_id(v)

    @model_validator(mode="after")
    def _consistent(self) -> ParamBound:
        if self.kind == "categorical":
            if not self.choices or len(self.choices) < 2:
                raise ValueError("categorical bound needs >= 2 choices")
            if self.low is not None or self.high is not None:
                raise ValueError("categorical bound must not set low/high")
        else:
            if self.low is None or self.high is None or self.low >= self.high:
                raise ValueError("numeric bound needs low < high")
            if self.choices is not None:
                raise ValueError("numeric bound must not set choices")
            if self.kind == "int":
                import math

                if math.ceil(self.low) > math.floor(self.high):
                    raise ValueError(f"int bound [{self.low}, {self.high}] contains no integer")
        return self


class MethodSpec(Strict):
    """A candidate or baseline method: agent type plus its parameters."""

    name: str
    agent: str
    params: dict[str, int | float | str | bool] = Field(default_factory=dict)

    @field_validator("name", "agent")
    @classmethod
    def _ids(cls, v: str) -> str:
        return _check_id(v)


class AcceptancePolicy(Strict):
    """Declared accept / reject / quarantine rule for candidate modifications."""

    validation_margin: float = Field(
        description="Patched candidate must beat the accepted candidate on mean "
        "validation score by at least this margin to be accepted."
    )
    min_valid_trial_fraction: float = Field(default=0.9, ge=0.0, le=1.0)
    quarantine_proposals: bool = Field(
        default=True,
        description="Rejected proposals are quarantined (retained, never silently dropped).",
    )


class PrimaryOutcome(Strict):
    metric: str
    direction: Literal["lower_is_better", "higher_is_better"]
    acceptance_margin: float = Field(
        description="Minimum improvement over baseline on the primary metric for the "
        "hypothesis to count as supported (preregistered practical threshold)."
    )


class AnalysisSpec(Strict):
    bootstrap_resamples: int = Field(default=5000, ge=200, le=200_000)
    bootstrap_seed: int = 20261018
    alpha: float = Field(default=0.05, gt=0, lt=1)
    multiple_comparison: Literal["holm-bonferroni", "none"] = "holm-bonferroni"


class StoppingSpec(Strict):
    """Stops the long-horizon loop before max_rounds if declared conditions hit."""

    stop_if_no_accepts_for_rounds: int | None = Field(default=None, ge=1)


class ExperimentSpec(Strict):
    schema_version: str = SPEC_SCHEMA_VERSION
    experiment_id: str
    protocol_id: str = "proofbench-adaptive-improvement"
    protocol_version: str = PROTOCOL_VERSION
    hypothesis: str = Field(min_length=10)
    primary_outcome: PrimaryOutcome
    tasks: list[TaskSpec] = Field(min_length=1)
    candidate: MethodSpec
    baselines: list[MethodSpec] = Field(min_length=1)
    seeds: Splits
    budget: BudgetSpec
    action_bounds: list[ParamBound] = Field(default_factory=list)
    acceptance: AcceptancePolicy
    analysis: AnalysisSpec = Field(default_factory=AnalysisSpec)
    stopping: StoppingSpec = Field(default_factory=StoppingSpec)
    run_seed: int | None = Field(
        default=None,
        description="Master seed for the long-horizon loop (agent episode seeds, "
        "proposal scheduling, bootstrap streams). When absent, the CLI derives "
        "it deterministically from the analysis seed and run id.",
    )
    notes: str = ""

    @field_validator("experiment_id", "protocol_id")
    @classmethod
    def _ids(cls, v: str) -> str:
        return _check_id(v)

    @field_validator("schema_version", "protocol_version")
    @classmethod
    def _versions(cls, v: str) -> str:
        if not re.match(r"^\d+\.\d+$", v):
            raise ValueError(f"version {v!r} must look like 'MAJOR.MINOR'")
        return v

    @model_validator(mode="after")
    def _semantic(self) -> ExperimentSpec:
        if self.schema_version != SPEC_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported spec schema_version {self.schema_version!r}; "
                f"this build validates {SPEC_SCHEMA_VERSION!r}"
            )
        bound_names = [b.name for b in self.action_bounds]
        if len(set(bound_names)) != len(bound_names):
            raise ValueError("action_bounds contain duplicate parameter names")
        return self

    def spec_hash(self) -> str:
        return hash_obj(self.model_dump(mode="json"))


def load_spec(data: dict[str, Any]) -> ExperimentSpec:
    """Validate a raw dict into an ExperimentSpec, mapping errors consistently."""
    try:
        return ExperimentSpec.model_validate(data)
    except Exception as exc:  # pydantic ValidationError or ValueError
        raise SpecValidationError(f"invalid experiment specification: {exc}") from exc

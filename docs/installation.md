# Installation & troubleshooting

## Requirements

- Linux x86-64 (developed and tested on Ubuntu, Python 3.14; CI targets 3.12).
  Python >= 3.11 is required.
- CPU only. No GPU, no container runtime, no Kubernetes, no Firecracker, and
  no network access are needed for the core platform.
- Disk: < 100 MB for the package plus whatever your runs produce (typically a
  few MB per run).

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"     # or without dev tools: -e .
```

With [uv](https://github.com/astral-sh/uv):

```bash
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
```

Runtime dependencies (kept deliberately minimal): `pydantic` (strict spec
validation), `numpy` (statistics + deterministic task math), `typer` (CLI).
Dev tools: `pytest`, `pytest-cov`, `ruff`, `mypy`.

## Verify the install

```bash
.venv/bin/proofbench doctor
.venv/bin/pytest -q
```

`doctor` prints one line per check and exits non-zero if a required check
fails. Container runtime absence is reported but never fails `doctor` —
untrusted execution is simply refused (by design).

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `proofbench: command not found` | Use `.venv/bin/proofbench`, or activate the venv. |
| `SpecValidationError` on a valid-looking JSON | Specs are strict: unknown fields, non-disjoint seeds, or out-of-range difficulty values are rejected on purpose. Read the error; it names the offending field. |
| Exit code 3 | Spec validation failure — same as above. |
| Exit code 4 | Integrity/verification failure. For `verify-bundle`, the output lists which check failed (manifest, event chain, recomputation, outcome, baseline). |
| Exit code 8 | Untrusted execution was requested but no container runtime is configured. This is a refusal, not a crash: either configure docker/podman explicitly or keep candidates in the bounded parameter-patch model. |
| Exit code 10 | A model-backed agent was requested without `PROOFBENCH_MODEL_*` configuration. Core experiments never need this. |
| `run ... not found` | Run ids resolve under `proofbench_runs/` (override with `--runs-dir` or `PROOFBENCH_RUNS_DIR`). You can also pass the run directory path directly. |
| Run interrupted (Ctrl-C, crash) | `proofbench resume RUN_ID` continues from the last atomic checkpoint. The interrupted event is in the log; nothing is lost. |
| Different spec on resume | A run directory is bound to one `spec_hash`. To change the spec, start a new run. |

## Uninstall

```bash
.venv/bin/pip uninstall proofbench
rm -rf proofbench_runs/          # your run outputs (optional)
```

# ProofBench

Research platform for investigating whether AI systems can improve their problem-solving performance under controlled, reproducible conditions. ProofBench distinguishes inference-time gains, strategy improvements, artifact improvements, learning, generalization, and self-modification—requiring strong evidence before making such claims.

## Key principles

- **CPU-only first**: Core experiments run without GPU, paid APIs, Kubernetes, or Firecracker.
- **Deterministic baselines**: Offline test suite after dependencies installed.
- **Explicit opt-ins**: Expensive model experiments are opt-in; no automatic model downloads; network access explicit.
- **Evidence as a first-class product**: Every run produces append-only event logs, content-addressed artifacts, and independently verifiable evidence bundles.
- **Authoritative evaluation**: Candidates cannot modify the evaluator, acceptance policy, or their own immutable baseline.
- **Honest statistics**: Report variability, uncertainty, held-out generalization, and both improvements and regressions.
- **License**: MIT (verify incorporated dependencies before distribution).

## Quick start

```bash
cd ProofBench
uv sync  # or pip install -e ".[dev]"
proofbench doctor
proofbench list-tasks
proofbench run examples/experiments/smoke_offline.toml
proofbench inspect <RUN_ID>
proofbench export <RUN_ID>
```

## What ProofBench can/cannot establish

ProofBench can establish that a method improved performance under a specific preregistered protocol, on a specific task family, under matched budgets, with held-out evaluation and uncertainty quantification. It cannot establish general AGI capability, universal self-improvement, or security guarantees beyond the explicitly supported execution paths.

# ProofBench Workshop: Traceable, Verifiable, Falsifiable

ProofBench is more than a single benchmark. It is a **workshop** for building trust
in claims — turning "trust me" into "here's how to check."

The world needs tools that make claims falsifiable instead of just persuasive.
We ship four tiny, offline-first, CPU-only CLI tools as part of this project so
anyone can start applying the same discipline immediately.

## The Four Tools

| Tool | Purpose | Status |
|---|---|---|
| [`tracebundle`](#tracebundle) | Wrap *any* command and emit a hash-chained, content-addressed evidence bundle of stdout, stderr, env (filtered), exit code, git state, timing, and working directory. | Built |
| [`reprocheck`](#reprocheck) | Given a published evidence bundle from someone else, verify it offline with zero dependencies beyond Python. Fails loud and clearly on tampering. | Built |
| [`eval-audit`](#eval-audit) | Audit an agent eval harness for red flags: train/test leakage, missing baselines, non-determinism hints, hidden prompts, unverifiable scores, and missing provenance. | Built |
| [`hermetic-run`](#hermetic-run) | A simple, container-free hermetic runner that snapshots the environment, pins dependency manifests, records a full attestation, and runs commands reproducibly without Firecracker/K8s. | Built |

All four tools share the same philosophy as ProofBench itself: offline-first,
deterministic where possible, content-addressed, independently verifiable, and
honest about limitations.

## Philosophy

1. **Make claims falsifiable.** If a claim is worth making, it should be
   possible to check it.
2. **Verification should be easier than assertion.** `verify-bundle` and
   `reprocheck` should be the path of least resistance.
3. **No hidden trust.** We don't ask for keys, tokens, or network access to
   verify a bundle.
4. **Be skeptical of your own tools.** Built-in audits and attestation are first
   class, not afterthoughts.
5. **Small tools compound.** Four tiny CLIs can shift norms faster than one giant platform.

## Quick Start

```bash
# Install with dev tools
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Trace any command
.venv/bin/tracebundle -- run pytest -q

# Verify someone else's bundle
.venv/bin/reprocheck path/to/bundle

# Audit an eval harness
.venv/bin/eval-audit path/to/eval-harness

# Run hermetically
.venv/bin/hermetic-run --env-lock requirements.txt -- run python my_script.py
```

## Design Principles

- **Hash-chained integrity.** Every action and artifact is linked with SHA-256
  hashes.
- **Content-addressed artifacts.** Filenames are their hashes; tampering is
  immediately obvious.
- **Offline-first.** Everything works air-gapped.
- **No execution of untrusted blobs.** Tools refuse unsafe fallbacks.
- **Human-readable and machine-verifiable.** Both reports and JSON outputs exist.
- **Minimal dependencies.** Core uses only stdlib + the same deps as ProofBench.

## Why now

The web is awash in AI-generated claims. The counterbalance is not more
benchmarks — it's more **proof**. By bundling these tools together, ProofBench
Workshop gives developers, researchers, and reviewers a shared toolkit to hold
claims accountable without needing a massive infra stack.

*"Make weak claims hard to support."*

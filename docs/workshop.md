# ProofBench Workshop: Traceable, Verifiable, Falsifiable

ProofBench is a **workshop for trust**. Alongside the benchmark, we ship four
tiny, offline-first, CPU-only CLI tools that turn "trust me" into "here's how
to check". The goal: make weak claims hard to support and strong claims easy to
verify.

## The Four Tools

| Tool | What it does | CLI | Output |
|---|---|---|---|
| **[tracebundle](#tracebundle)** | Wrap *any* command and emit a self-contained, hash-chained, content-addressed evidence bundle (stdout, stderr, filtered env, git state, cwd, exit code, timing). | `tracebundle -- <cmd> [...]` | `tracebundle-<ts>-<pid>/` with `manifest.json`, `env.json`, `stdout.txt`, `stderr.txt`, `VERIFICATION.md`, `bundle.sha256` |
| **[reprocheck](#reprocheck)** | Independently verify a bundle offline with zero network access. Checks manifest, every artifact hash, and optional bundle hash. Fails loud on tampering/missing files. | `reprocheck <bundle-dir>` | Human-readable PASS/FAIL with actionable errors |
| **[eval-audit](#eval-audit)** | Audit an agent eval harness for reproducibility/verifiability red flags: train/test leakage hints, missing baselines, non-determinism, hidden prompts, unverifiable scoring, missing provenance, secret risks. | `eval-audit <path> [--json]` | Scored report (A–F) with concrete fixes |
| **[hermetic-run](#hermetic-run)** | Container-free hermetic runner that snapshots env/platform/python/manifest hashes, writes a signed-style attestation, and runs the command transparently. | `hermetic-run [--env-lock FILE] [--out DIR] -- <cmd> [...]` | `hermetic-run-<ts>-<pid>/` with `snapshot.json`, `attestation.json`, `RUN.md` |

## Philosophy

1. **Make claims falsifiable.** If it's worth asserting, it should be checkable.
2. **Verification before assertion.** Publishing a bundle beats a screenshot.
3. **No hidden trust.** Verification needs nothing but files on disk.
4. **Content-address everything.** Hashes establish identity and integrity, not validity.
5. **Be explicit about limits.** Tools refuse unsafe fallbacks and document what they don't do.
6. **Tiny tools compound.** A few simple CLIs can shift norms.

## Quick Start (offline, CPU-only)

```bash
# Install
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 1) Trace any execution
.venv/bin/tracebundle -- pytest -q

# 2) Verify it (or someone else's bundle)
.venv/bin/reprocheck ./tracebundle-*/

# 3) Audit an eval harness
.venv/bin/eval-audit ./path/to/harness
.venv/bin/eval-audit ./path/to/harness --json

# 4) Run with a transparent attestation
.venv/bin/hermetic-run --env-lock pyproject.toml -- python -c "print('ok')"
```

## Design: A Coherent Story

- **Trace** (`tracebundle`) creates proof of *what happened*.
- **Verify** (`reprocheck`) lets anyone *check that proof* without trust.
- **Audit** (`eval-audit`) helps you *find holes before publishing*.
- **Attest** (`hermetic-run`) makes *future runs easier to reproduce*.

Together with ProofBench's benchmark workflow, these tools form a single
discipline: preregister → run with evidence → audit → publish a bundle →
let others verify independently.

## Verification Contract

- **Offline-first:** All operations work air-gapped.
- **Deterministic serialization:** Canonical JSON (sorted keys, compact) for stable hashes.
- **Content addressing:** Artifacts referenced by their SHA-256.
- **Fail loud:** Tampering, missing files, or hash mismatches produce clear errors and non-zero exits.
- **No secrets in bundles:** Environment is filtered; keys/tokens/secrets are redacted.
- **Minimal surface:** Stdlib-first, same dependencies as ProofBench.

## Limitations (by design)

- `hermetic-run` provides **transparency + attestation**, not OS-level sandboxing. For untrusted code, use a real sandbox (see `docs/threat-model.md`).
- `eval-audit` uses heuristics; false positives/negatives are possible — treat it as a reviewer, not a judge.
- Hashes prove integrity, not correctness or scientific validity.

*"Make weak claims hard to support."*

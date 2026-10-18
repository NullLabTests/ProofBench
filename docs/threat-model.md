# Threat model and trust boundaries

## What ProofBench protects against

| Adversary | Capability | Defense |
|---|---|---|
| A candidate method wanting better scores | Modify its own parameters outside declared bounds | `validate_patch` + `audit_forbidden_keys`; violations are audited events, never applied |
| A candidate wanting to hide failures | Delete or edit the evidence record | Append-only hash-chained `events.jsonl`; any edit breaks `verify_chain`; bundles are content-addressed and `verify-bundle` detects missing/extra/modified files |
| A candidate supplying its own score | Report a number instead of being evaluated | Scores exist only as `Episode.finalize()` results computed by the independent `Evaluator`; certificates are recomputed from raw per-trial records at verification time |
| Silent baseline replacement | Swap the baseline for an easier one mid-run | Baseline params hashed at init, re-verified before final scoring; mismatch aborts with `IntegrityError` |
| Post-hoc acceptance tuning | Change the margin after seeing test results | Acceptance rule lives in the spec, which is hashed at initialization and frozen inside the bundle; the verifier re-applies the recorded rule |
| Forged certificate | Edit numbers inside a certificate | Certificate is stored content-addressed in the artifact store; the bundle manifest pins its sha256; the verifier recomputes all statistics from raw trials |
| Seed shopping | Re-run until a desired result appears | Run directories are content-addressed and every run issues a certificate, including null/negative outcomes; `compare` displays both; reviewers should demand the full set of runs (documented limitation: ProofBench cannot prevent undisclosed parallel runs) |

## Trust boundaries

**Inside the trust boundary (trusted computing base):**
`evaluator.py`, `loop.py`, `bundle.py`, `stats.py`, `events.py`, `store.py`,
`spec.py`, and the built-in task families/agents as shipped. These are
content-hashed by the bundle manifest; changing them changes verification.

**Outside the trust boundary (untrusted):**
Everything a candidate proposes (parameter patches; in future, code artifacts
executed only via the refusing `ContainerExecutor`), any external model
service behind `model_adapter.py`, and any run directory produced by a
different ProofBench build (detected: verifier checks `proofbench_version` and
recomputes rather than trusting).

## Resource & safety boundaries

- Built-in episodes are bounded by `evaluations_per_instance`; every step
  consumes budget, malformed actions included.
- The local executor applies wall-clock bounds. It is explicitly **not** a
  security sandbox and is used only for trusted built-ins.
- Untrusted execution (`ContainerExecutor`) requires an explicit container
  runtime and image, runs with `--network none`, memory/CPU/PID limits, and a
  read-only rootfs. Without a configured runtime it raises
  `ExecutionUnavailable` (exit 8). There is no silent fallback path.
- v0.1 executes no candidate-supplied code at all.

## Out of scope

- A malicious operator with write access to the runs directory can delete
  runs. The hash chain and manifests make *tampering* detectable, not
  *deletion* impossible. Evidence-portability (publishing bundles) is the
  mitigation.
- A compromised host kernel or Python runtime is outside the boundary.
- Statistical validity depends on the experimenter's discipline (preregistration
  honesty, publishing null results). ProofBench enforces the *record*, not the
  *sociology*.

## Explicit non-claims

ProofBench does not provide: a security sandbox for arbitrary code on the
default path, protection against a colluding operator, or cryptographic
proofs of scientific validity. Hashes are integrity tools, not notarization.

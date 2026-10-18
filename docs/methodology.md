# Experimental methodology

## Phenomena ProofBench distinguishes

| Phenomenon | Where it appears in a ProofBench run | What it is NOT |
|---|---|---|
| **Inference improvement** | A single episode's score improves because the agent used feedback *within* the episode (e.g., local refinement around a good point). Visible in candidate-vs-baseline episode scores. | Not learning; nothing persists across episodes. |
| **Strategy improvement** | The candidate's *accepted parameters* change across rounds and the **final-vs-initial** held-out comparison is positive. The change persists for every subsequent episode. | Not generalization by itself; the parameter change could still be task-family-specific. |
| **Artifact improvement** | (Future work, via the container backend) a proposed code artifact passes independent verification. | Not self-supplied scoring; the evaluator grades the artifact. |
| **Learning** | Improvement attributable to information retained from prior experience — here, the validation feedback that drives parameter acceptance. | Not implied by a single-run improvement. |
| **Generalization** | Improvement measured on **test seeds** never seen during adaptation (disjoint, preregistered). | Guards against memorizing instances, not against overfitting to the family's structure. |
| **Self-modification** | The candidate proposes bounded parameter changes; the controller validates, evaluates, and accepts/rejects them. | Never touches the evaluator, budget, acceptance policy, baseline, seeds, or evidence. |

A model producing a better answer after receiving more tokens is, by itself,
none of the above. ProofBench requires the final-vs-initial and
candidate-vs-baseline decompositions to make any claim.

## Preregistration discipline

The specification is the preregistration. It fixes, before any held-out
evaluation:

- the hypothesis and primary metric (including direction and a **practical
  acceptance margin**, not just a p-value);
- task families, versions, and difficulty parameters;
- candidate and baseline identities and parameters;
- train / validation / test instance seeds (validated pairwise-disjoint);
- the evaluation budget (identical for all methods on an instance);
- the per-round acceptance rule (validation margin, validity threshold);
- the analysis procedure (bootstrap resamples + seed, alpha, multiple-
  comparison policy).

The spec is hashed at run start; the hash is stamped into the certificate and
the bundle. The verifier re-applies the *recorded* rule to *recomputed*
numbers. Changing the rule changes the hash; a certificate cannot be reissued
under an old run without detection.

## Held-out evaluation procedure

1. **Train instances** (`train_seeds`) are used inside the long-horizon loop;
   their scores populate the learning curve but never the primary outcome.
2. **Validation instances** (`validation_seeds`) gate each proposed parameter
   change. Only the accept/reject decision uses them.
3. **Test instances** (`test_seeds`) are touched exactly once per method, in
   the final phase: final candidate, initial candidate, and baseline. The
   primary outcome is computed only from these.

All three splits are fixed in the spec before the run. Seed ranges in the
shipped experiments are deliberately separated by orders of magnitude
(1–12 / 100–107 / 1000–1015) to make overlap visually obvious in review.

## Budget matching

`budget.evaluations_per_instance` is identical for candidate and baseline on
every instance, and the episode loop hard-steps the budget: malformed or
invalid actions **consume** budget rather than granting retries. Wall-clock
and CPU time are recorded per episode and summed per run; reports quality
*and* cost. Inference-time gains from extra compute are additionally exposed
by the compute-matched design: to win, the adaptive method must use its budget
better, not more.

## Acceptance, rejection, quarantine

A proposed parameter change is:

1. checked against the **permitted action policy** (bounded parameters only);
   violations become audit events and are never applied;
2. evaluated on validation instances against the currently-accepted
   parameters;
3. **accepted** only if the improvement clears the preregistered validation
   margin with a valid-trial fraction above threshold;
4. otherwise **rejected and quarantined** — retained in the record with its
   results, never silently dropped, never overwriting the accepted candidate.

## Reporting obligations

- Report all three possible outcomes; the negative-control experiment
  (`experiments/negative-control-v1.json`) exists precisely to demonstrate a
  null result end-to-end.
- Report missing/invalid trials (the analysis counts them explicitly).
- Report regressions: the certificate contains a per-family breakdown with
  regression flags.
- Distinguish the preregistered primary outcome (one test) from exploratory
  secondary analyses (strategy comparison, per-family checks), which get
  Holm-Bonferroni correction when enabled.
- Statistical significance is never sufficient: the acceptance rule requires a
  preregistered *practical* margin in addition to CI and p-value criteria.

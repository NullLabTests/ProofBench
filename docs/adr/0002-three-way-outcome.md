# ADR-0002: Three-way outcome, not binary pass/fail

## Status

Accepted for v0.1.

## Context

Binary pass/fail conflates "the method does not work" with "the evaluation
broke". Both are scientifically meaningful and must not be merged.

## Decision

Certificates carry exactly one of: `improvement_demonstrated`,
`improvement_not_demonstrated`, `inconclusive`. Inconclusive is reserved for
evaluations with too few valid held-out pairs
(`n_pairs/n_total < min_valid_trial_fraction`) — e.g., widespread agent
crashes — and is never presented as a null result.

## Consequences

- Reviewers can distinguish a real negative from a broken run at a glance.
- The verifier recomputes the outcome class from raw trials, so a certificate
  cannot relabel an inconclusive run as a negative or vice versa.

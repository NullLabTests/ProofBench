# ADR-0004: One primary outcome, preregistered in the spec

## Status

Accepted for v0.1.

## Context

Post-hoc metric selection is the classic way to manufacture improvement.
Statistical correction cannot save an outcome chosen after seeing results.

## Decision

Each experiment declares exactly one `primary_outcome` (metric, direction,
practical acceptance margin) before evaluation. The certificate's headline
outcome is computed from that single preregistered test. Secondary analyses
(strategy comparison, per-family regression checks) are labeled exploratory
and receive Holm-Bonferroni correction when enabled.

## Consequences

- The headline claim is falsifiable and single-use.
- Exploratory findings are still reported (regressions and all) but are
  visually and structurally separated from the primary result.

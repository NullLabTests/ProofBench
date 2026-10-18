# ADR-0001: Candidates modify bounded parameters, not code (v0.1)

## Status

Accepted for v0.1.

## Context

The mission calls for "bounded modifications to working artifacts" but the
development host has no container runtime, and a Python subprocess with a
timeout is not a security sandbox. Executing candidate-generated code on the
host would make the security model unauditable.

## Decision

v0.1 candidates modify only a declared parameter surface (`action_bounds`).
All candidate content is data validated by `actions.validate_patch`; nothing
is evaluated by dynamic import or shell. The `ContainerExecutor` interface
exists with refusal semantics for when a real runtime is available.

## Consequences

- The trusted computing base is small and auditable; the threat model is
  credible for the paths actually supported.
- Code-artifact improvement experiments are deferred to the container-backed
  roadmap item and are explicitly not claimed.

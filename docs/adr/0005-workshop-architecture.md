# ADR 0005: Workshop Architecture

## Status
Accepted

## Context
ProofBench needs tools to make AI/ML claims falsifiable. The original four tools needed maturation and unification.

## Decision
Create `proofbench/workshop/` as unified package with:
- `tracebundle` - execution tracing
- `reprocheck` - bundle verification  
- `eval_audit` - harness auditing
- `hermetic_run` - hermetic execution
- `cli` - unified interface `proofbench-workshop`

Add supporting modules:
- `proofbench/attest/` - SLSA-style attestations
- `proofbench/ledger/` - append-only verification ledger
- `proofbench/schema/` - JSON schemas

## Consequences
- Unified UX through single CLI
- Modular design allows independent use
- Attestations provide supply-chain style provenance
- Ledger enables audit trails across verifications
- All tools remain offline-first and deterministic

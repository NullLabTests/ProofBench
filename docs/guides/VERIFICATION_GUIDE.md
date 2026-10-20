# Verification Guide

This guide explains how to verify ProofBench artifacts end-to-end, from bundles to attestations to ledger entries.

## Principles
- **Offline-first**: All verification uses only local files.
- **Content-addressed**: Every artifact is hashed with SHA-256.
- **Append-only**: Verification ledger maintains hash chain.
- **Deterministic**: Canonical JSON ensures reproducible hashes.
- **Falsifiable**: Claims can be independently checked.

## Quick verification
```bash
# Verify a trace bundle
proofbench-workshop verify bundle-dir/

# Verify attestation
python -m json.tool attestation.json | head -40

# Verify ledger chain
proofbench-workshop ledger verify

# Verify experiment bundle
proofbench verify-bundle runs/exp/bundle.json
```

## Bundle structure
A tracebundle contains:
- `manifest.json` - Canonical manifest with all artifact hashes
- `bundle.sha256` - Hash of manifest
- `stdout.txt`, `stderr.txt` - Command output
- `env.json` - Redacted environment
- `VERIFICATION.md` - Human-readable instructions

## What gets verified
1. Manifest JSON is valid
2. Every artifact listed exists and matches its hash
3. `manifest.json` hash matches its entry (self-verification)
4. `bundle.sha256` matches manifest hash

## Attestations
ProofBench uses in-toto style attestations (SLSA-inspired):
```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [{"name": "...", "digest": {"sha256": "..."}}],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {...}
}
```

## Ledger
Append-only JSONL with chain linking:
```json
{"seq": 0, "ts": ..., "prev_hash": "0"*64, "hash": "...", ...}
```
Each entry's hash covers all fields except `hash` itself.

## Troubleshooting
- **TAMPERED**: File modified after bundle creation
- **MISSING**: File deleted
- **hash mismatch**: Content changed or wrong serialization

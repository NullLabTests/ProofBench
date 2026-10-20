# TraceBundle v2 Specification

## Overview
TraceBundle captures deterministic execution traces with cryptographic verification.

## Format
Schema: `tracebundle/2`

### manifest.json
```json
{
  "schema": "tracebundle/2",
  "tracebundle_version": "...",
  "workshop_version": "0.2.0",
  "command": [...],
  "exit_code": 0,
  "elapsed_seconds": 1.234,
  "started_at_unix": 1234567890.0,
  "ended_at_unix": 1234567891.0,
  "cwd": "/path",
  "pid": 12345,
  "platform": "...",
  "python": "...",
  "git": {"commit": "...", "branch": "...", "dirty": false},
  "artifacts": {"name": "sha256hex", ...},
  "events": [{"seq": 0, "kind": "start", ...}, ...],
  "chain_head": "sha256hex"
}
```

## Hashing
- All hashes are SHA-256 hex strings
- Canonical JSON (sorted keys, no extra whitespace) for deterministic serialization
- File hashes computed on raw bytes
- Bundle hash = SHA-256 of canonical manifest.json bytes

## Security
- Environment variables redacted if name contains: key, token, secret, password, pass, auth, credential, private
- No secrets written to bundle
- Git remote captured for provenance

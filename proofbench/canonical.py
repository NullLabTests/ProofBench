"""Canonical serialization and content addressing.

All identity and integrity checks in ProofBench are SHA-256 hashes of canonical
JSON (sorted keys, compact separators, no NaN) or of raw bytes.  Hashes establish
*identity and integrity only*; they are not evidence that an experiment was
scientifically valid.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialize ``obj`` to a deterministic JSON string.

    Keys are sorted, separators are compact, and non-finite floats are rejected
    so that two structurally equal objects always produce identical bytes.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_obj(obj: Any) -> str:
    """Content-address any JSON-serializable object."""
    return sha256_hex(canonical_json(obj).encode("utf-8"))


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

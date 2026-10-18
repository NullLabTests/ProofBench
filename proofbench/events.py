"""Append-only, hash-chained event log.

Every run emits an ordered stream of JSON events.  Each event embeds the
SHA-256 of its canonical payload plus the previous event's chain hash, so any
post-hoc insertion, deletion, or edit breaks the chain and is detectable by
``verify_chain``.  The chain establishes *integrity of the record*, not
scientific validity.

Events are appended with fsync so an interrupted run retains its history up to
the last durable event (paired with atomic ``state.json`` checkpoints).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from proofbench.canonical import canonical_json, sha256_hex

GENESIS = "0" * 64


def _chain_hash(prev: str, payload: dict[str, Any]) -> str:
    return sha256_hex(f"{prev}\n{canonical_json(payload)}".encode())


class EventLog:
    """Append-only JSONL event stream with a verifiable hash chain."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._load_tail()

    def _load_tail(self) -> str:
        if not self.path.exists():
            return GENESIS
        last = GENESIS
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)["chain_hash"]
        return last

    @property
    def last_hash(self) -> str:
        return self._last_hash

    def append(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        event: dict[str, Any] = {
            "seq": self._count_events(),
            "ts": time.time(),
            "kind": kind,
            "payload": payload,
            "prev": self._last_hash,
        }
        event["chain_hash"] = _chain_hash(self._last_hash, payload)
        line = canonical_json(event) + "\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        self._last_hash = event["chain_hash"]
        return event

    def _count_events(self) -> int:
        if not self.path.exists():
            return 0
        with open(self.path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


def verify_chain(events: list[dict[str, Any]]) -> list[str]:
    """Verify ordering, sequence numbers, and the full hash chain.

    Returns a list of human-readable failure descriptions (empty = valid).
    """
    failures: list[str] = []
    prev = GENESIS
    for i, ev in enumerate(events):
        if ev.get("seq") != i:
            failures.append(f"event {i}: sequence number is {ev.get('seq')!r}")
        if ev.get("prev") != prev:
            failures.append(f"event {i}: prev hash mismatch")
        payload = ev.get("payload")
        if not isinstance(payload, dict):
            failures.append(f"event {i}: payload is not an object")
            prev = ev.get("chain_hash", "")
            continue
        expected = _chain_hash(prev, payload)
        if ev.get("chain_hash") != expected:
            failures.append(f"event {i}: chain hash mismatch (payload edited?)")
        prev = ev.get("chain_hash", "")
    return failures

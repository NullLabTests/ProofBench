"""Append-only verification ledger."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from proofbench.canonical import canonical_json, hash_obj


class Ledger:
    def __init__(self, path: Path | str = "verification-ledger.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict) -> dict:
        rec = {"seq": self._count(), "ts": time.time(), **entry}
        rec["prev_hash"] = self._last_hash()
        rec["hash"] = hash_obj({k: v for k, v in rec.items() if k != "hash"})
        with self.path.open("a", encoding="utf-8") as f:
            f.write(canonical_json(rec) + "\n")
        return rec

    def _count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open() as f:
            return sum(1 for _ in f)

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        last = None
        with self.path.open() as f:
            for line in f:
                if line.strip():
                    try:
                        last = json.loads(line)
                    except Exception:
                        pass
        return last.get("hash", "0" * 64) if last else "0" * 64

    def verify(self) -> tuple[bool, list[str]]:
        if not self.path.exists():
            return True, []
        errors = []
        prev = "0" * 64
        seq = 0
        with self.path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception as e:
                    errors.append(f"bad json: {e}")
                    continue
                if rec.get("seq") != seq:
                    errors.append(f"seq mismatch at {seq}")
                if rec.get("prev_hash") != prev:
                    errors.append(f"chain break at {seq}")
                exp = hash_obj({k: v for k, v in rec.items() if k != "hash"})
                if rec.get("hash") != exp:
                    errors.append(f"hash mismatch at {seq}")
                prev = rec.get("hash", "")
                seq += 1
        return len(errors) == 0, errors

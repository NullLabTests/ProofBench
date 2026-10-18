"""Content-addressed artifact store and atomic writes."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from proofbench.canonical import canonical_json, hash_obj, sha256_hex
from proofbench.errors import IntegrityError


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically (tmp file + fsync + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_bytes(path, (canonical_json(obj) + "\n").encode("utf-8"))


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class ArtifactStore:
    """Content-addressed store: ``put`` returns the sha256, ``get`` verifies it."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest

    def put_bytes(self, data: bytes) -> str:
        digest = sha256_hex(data)
        self._path(digest).parent.mkdir(parents=True, exist_ok=True)
        target = self._path(digest)
        if not target.exists():
            atomic_write_bytes(target, data)
        return digest

    def put_obj(self, obj: Any) -> str:
        return self.put_bytes((canonical_json(obj) + "\n").encode("utf-8"))

    def get_bytes(self, digest: str) -> bytes:
        path = self._path(digest)
        if not path.exists():
            raise IntegrityError(f"artifact {digest} missing from store")
        data = path.read_bytes()
        if sha256_hex(data) != digest:
            raise IntegrityError(f"artifact {digest} failed integrity check")
        return data

    def get_obj(self, digest: str) -> Any:
        return json.loads(self.get_bytes(digest).decode("utf-8"))

    def has(self, digest: str) -> bool:
        return self._path(digest).exists()

    def verify_all(self) -> list[str]:
        """Re-hash every artifact; return list of failure descriptions."""
        failures: list[str] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            digest = path.name
            if sha256_hex(path.read_bytes()) != digest:
                failures.append(f"{path}: content does not match its address")
        return failures


def obj_hash(obj: Any) -> str:
    return hash_obj(obj)

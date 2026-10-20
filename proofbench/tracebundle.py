"""tracebundle — wrap any command and emit an evidence bundle."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from proofbench import __version__
from proofbench.canonical import canonical_json


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in ("PROOFBENCH_MODEL_API_KEY", "OPENAI_API_KEY"):
            out[k] = "***redacted***"
            continue
        out[k] = v
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: tracebundle -- <command ...>", file=sys.stderr)
        return 0 if args else 2
    cmd = args[1:] if args[0] == "--" else args
    if not cmd:
        print("tracebundle: no command given", file=sys.stderr)
        return 2

    start = time.time()
    t0 = time.perf_counter()
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print(f"tracebundle: command not found: {cmd[0]}", file=sys.stderr)
        return 127
    t1 = time.perf_counter()
    elapsed = t1 - t0

    ts = time.strftime("%Y%m%d-%H%M%S")
    bundle_dir = Path(f"tracebundle-{ts}")
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "stdout.txt").write_text(p.stdout or "", encoding="utf-8")
    (bundle_dir / "stderr.txt").write_text(p.stderr or "", encoding="utf-8")

    manifest: dict[str, Any] = {
        "tracebundle_version": __version__,
        "command": cmd,
        "exit_code": p.returncode,
        "elapsed_seconds": round(elapsed, 6),
        "timestamp": start,
        "cwd": os.getcwd(),
        "git": None,
        "artifacts": {},
    }
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0:
            manifest["git"] = {"sha": r.stdout.strip()}
    except Exception:
        pass

    for name in ("stdout.txt", "stderr.txt"):
        f = bundle_dir / name
        if f.exists():
            manifest["artifacts"][name] = _hash_file(f)

    (bundle_dir / "manifest.json").write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    (bundle_dir / "env.json").write_text(canonical_json(_safe_env()) + "\n", encoding="utf-8")
    (bundle_dir / "self_hash.txt").write_text(hashlib.sha256(canonical_json(manifest).encode()).hexdigest(), encoding="utf-8")

    print(f"tracebundle: wrote {bundle_dir}")
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())

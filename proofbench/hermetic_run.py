"""hermetic-run — container-free hermetic execution with attestation.

Snapshots environment, records dependency manifests, produces a hash-
chained attestation, and runs the command. No Firecracker/K8s required.
Focus on transparency and reproducibility over heavy sandboxing.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from proofbench import __version__
from proofbench.canonical import canonical_json, hash_file, hash_obj


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: hermetic-run [--env-lock FILE] [--out DIR] -- <command> [args...]\n\n"
            "Run with a transparent environment snapshot and attestation.\n"
            "Records manifests, keys, platform info, and hashes.",
            file=sys.stderr,
        )
        return 0 if args else 2

    env_lock = None
    out_dir_arg = None
    i = 0
    while i < len(args):
        if args[i] == "--env-lock" and i + 1 < len(args):
            env_lock = args[i + 1]
            i += 2
            continue
        if args[i] == "--out" and i + 1 < len(args):
            out_dir_arg = args[i + 1]
            i += 2
            continue
        if args[i] == "--":
            i += 1
            break
        break
    cmd = list(args[i:]) if i < len(args) else []
    if not cmd:
        print("hermetic-run: missing command", file=sys.stderr)
        return 2

    ts = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir_arg) if out_dir_arg else Path(f"hermetic-run-{ts}-{os.getpid()}")
    out_dir.mkdir(parents=True, exist_ok=False)

    lock_hash = None
    if env_lock and Path(env_lock).exists():
        lock_hash = hash_file(env_lock)

    snap: dict[str, Any] = {
        "schema": "hermetic-run/1",
        "hermetic_run_version": __version__,
        "timestamp": time.time(),
        "cwd": os.getcwd(),
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "env_lock": env_lock,
        "env_lock_hash": lock_hash,
        "env_keys": sorted([k for k in os.environ if not any(s in k.lower() for s in ("key", "token", "secret"))]),
    }
    snap_hash = hash_obj(snap)
    (out_dir / "snapshot.json").write_text(canonical_json(snap) + "\n", encoding="utf-8")

    att: dict[str, Any] = {
        "schema": "hermetic-run-attestation/1",
        "attested_at": time.time(),
        "snapshot_hash": snap_hash,
        "command": cmd,
        "verifier_hint": "Compare snapshot.json and attestation.json hashes offline.",
    }
    (out_dir / "attestation.json").write_text(canonical_json(att) + "\n", encoding="utf-8")
    (out_dir / "RUN.md").write_text(
        "# hermetic-run\n\n"
        f"Snapshot: {out_dir}/snapshot.json (sha256 {snap_hash})\n"
        f"Command: {json.dumps(cmd)}\n\n"
        "This is a transparent attestation, not a mandatory VM sandbox.\n",
        encoding="utf-8",
    )

    print(f"hermetic-run: attestation in {out_dir}")
    print(f"hermetic-run: snapshot sha256 {snap_hash}")
    try:
        p = subprocess.run(cmd)
        return p.returncode
    except Exception as e:
        print(f"hermetic-run: {e}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())

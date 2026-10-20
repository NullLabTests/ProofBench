"""hermetic-run — container-free hermetic runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from proofbench import __version__
from proofbench.canonical import canonical_json, sha256_hex


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: hermetic-run [--env-lock FILE] -- <command ...>", file=sys.stderr)
        return 0 if args else 2
    env_lock = None
    if args and args[0] == "--env-lock":
        env_lock = args[1]
        args = args[2:]
    cmd = args[1:] if args and args[0] == "--" else args
    if not cmd:
        print("hermetic-run: no command", file=sys.stderr)
        return 2

    snap = {
        "hermetic_run_version": __version__,
        "cwd": os.getcwd(),
        "python": sys.version,
        "env_lock": env_lock,
        "env_keys": sorted(os.environ.keys()),
    }
    if env_lock and Path(env_lock).exists():
        snap["env_lock_hash"] = sha256_hex(Path(env_lock).read_bytes())

    out_dir = Path(f"hermetic-{time.strftime('%Y%m%d-%H%M%S')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "snapshot.json").write_text(canonical_json(snap) + "\n", encoding="utf-8")
    (out_dir / "attestation.json").write_text(
        json.dumps(
            {"attested_at": time.time(), "snapshot_hash": sha256_hex(canonical_json(snap).encode())},
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        p = subprocess.run(cmd)
        return p.returncode
    except Exception as e:
        print(f"hermetic-run: {e}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())

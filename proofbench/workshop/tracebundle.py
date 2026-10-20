"""tracebundle — wrap any command and emit a verifiable evidence bundle."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from proofbench import __version__
from proofbench.canonical import canonical_json, hash_file


def _safe_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in os.environ.items():
        kl = k.lower()
        if any(s in kl for s in ("key", "token", "secret", "password", "pass", "auth")):
            out[k] = "***REDACTED***"
            continue
        out[k] = v
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: tracebundle -- <command> [args...]", file=sys.stderr)
        return 0 if args else 2
    if args[0] == "--":
        cmd = args[1:]
    else:
        cmd = list(args)
    if not cmd:
        print("tracebundle: missing command", file=sys.stderr)
        return 2

    start_wall = time.time()
    start_perf = time.perf_counter()
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        print(f"tracebundle: command not found: {cmd[0]!r}", file=sys.stderr)
        return 127

    elapsed = time.perf_counter() - start_perf
    ts = time.strftime("%Y%m%d-%H%M%S")
    bundle_dir = Path(f"tracebundle-{ts}-{os.getpid()}")
    bundle_dir.mkdir(parents=True, exist_ok=False)

    (bundle_dir / "stdout.txt").write_text(proc.stdout if proc.stdout is not None else "", encoding="utf-8")
    (bundle_dir / "stderr.txt").write_text(proc.stderr if proc.stderr is not None else "", encoding="utf-8")

    manifest: dict[str, Any] = {
        "schema": "tracebundle/1",
        "tracebundle_version": __version__,
        "command": list(cmd),
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 6),
        "started_at_unix": round(start_wall, 6),
        "cwd": os.getcwd(),
        "pid": os.getpid(),
        "git": None,
        "artifacts": {},
    }

    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if r.returncode == 0 and r.stdout.strip():
            manifest["git"] = {"commit": r.stdout.strip()}
    except Exception:
        pass

    for name in ("stdout.txt", "stderr.txt"):
        manifest["artifacts"][name] = hash_file(str(bundle_dir / name))

    env_json_bytes = (canonical_json(_safe_env()) + "\n").encode("utf-8")
    (bundle_dir / "env.json").write_bytes(env_json_bytes)
    manifest["artifacts"]["env.json"] = hashlib.sha256(env_json_bytes).hexdigest()

    verification_md = (
        "# tracebundle verification\n\n"
        f"Bundle: {bundle_dir.name}\nCommand: {json.dumps(cmd)}\nExit code: {proc.returncode}\n\n"
        "Verify with: `reprocheck <this-bundle>`\n"
    )
    vm_bytes = verification_md.encode("utf-8")
    (bundle_dir / "VERIFICATION.md").write_bytes(vm_bytes)
    manifest["artifacts"]["VERIFICATION.md"] = hashlib.sha256(vm_bytes).hexdigest()

    manifest_json_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
    (bundle_dir / "manifest.json").write_bytes(manifest_json_bytes)
    manifest["artifacts"]["manifest.json"] = hashlib.sha256(manifest_json_bytes).hexdigest()

    manifest_final = canonical_json(manifest) + "\n"
    (bundle_dir / "manifest.json").write_text(manifest_final, encoding="utf-8")
    (bundle_dir / "bundle.sha256").write_text(hashlib.sha256(manifest_final.encode("utf-8")).hexdigest() + "\n", encoding="utf-8")

    print(f"tracebundle: wrote {bundle_dir}")
    print(f"tracebundle: verify with `reprocheck {bundle_dir}`")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

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
        if any(
            s in kl
            for s in (
                "key",
                "token",
                "secret",
                "password",
                "pass",
                "auth",
                "credential",
                "private",
            )
        ):
            out[k] = "***REDACTED***"
            continue
        out[k] = v
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: tracebundle -- <command> [args...]", file=sys.stderr)
        return 0 if args else 2
    cmd = args[1:] if args[0] == "--" else list(args)
    if not cmd:
        print("tracebundle: missing command", file=sys.stderr)
        return 2

    start_wall = time.time()
    start_perf = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"tracebundle: command not found: {cmd[0]!r}", file=sys.stderr)
        return 127

    elapsed = time.perf_counter() - start_perf
    ts = time.strftime("%Y%m%d-%H%M%S")
    bundle_dir = Path(f"tracebundle-{ts}-{os.getpid()}")
    bundle_dir.mkdir(parents=True, exist_ok=False)

    (bundle_dir / "stdout.txt").write_text(
        proc.stdout if proc.stdout is not None else "", encoding="utf-8"
    )
    (bundle_dir / "stderr.txt").write_text(
        proc.stderr if proc.stderr is not None else "", encoding="utf-8"
    )

    artifacts: dict[str, str] = {}
    for name in ("stdout.txt", "stderr.txt"):
        artifacts[name] = hash_file(str(bundle_dir / name))

    env_json_bytes = (canonical_json(_safe_env()) + "\n").encode("utf-8")
    (bundle_dir / "env.json").write_bytes(env_json_bytes)
    artifacts["env.json"] = hashlib.sha256(env_json_bytes).hexdigest()

    verification_md = (
        "# tracebundle verification\n\n"
        f"Bundle: {bundle_dir.name}\nCommand: {json.dumps(cmd)}\nExit code: {proc.returncode}\n\n"
        "Verify with: `reprocheck <this-bundle>`\n"
    )
    vm_bytes = verification_md.encode("utf-8")
    (bundle_dir / "VERIFICATION.md").write_bytes(vm_bytes)
    artifacts["VERIFICATION.md"] = hashlib.sha256(vm_bytes).hexdigest()

    events = [
        {"seq": 0, "kind": "start", "ts": start_wall},
        {"seq": 1, "kind": "finish", "ts": time.time(), "exit_code": proc.returncode},
    ]
    manifest: dict[str, Any] = {
        "schema": "tracebundle/1",
        "tracebundle_version": __version__,
        "command": list(cmd),
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 6),
        "started_at_unix": round(start_wall, 6),
        "ended_at_unix": round(time.time(), 6),
        "cwd": os.getcwd(),
        "pid": os.getpid(),
        "git": None,
        "events": events,
        "chain_head": hashlib.sha256(canonical_json(events).encode()).hexdigest(),
        "artifacts": dict(artifacts),
    }
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        )
        if r.returncode == 0 and r.stdout.strip():
            manifest["git"] = {"commit": r.stdout.strip()}
    except Exception:
        pass

    m = json.loads(canonical_json(manifest))
    m["artifacts"] = dict(m["artifacts"])
    (bundle_dir / "manifest.json").write_text(
        canonical_json(m) + "\n", encoding="utf-8"
    )
    self_h = hash_file(str(bundle_dir / "manifest.json"))
    m["artifacts"]["manifest.json"] = self_h
    m_final_str = canonical_json(m) + "\n"
    (bundle_dir / "manifest.json").write_text(m_final_str, encoding="utf-8")
    manifest_path = bundle_dir / "manifest.json"
    bundle_hash = hash_file(str(manifest_path))
    (bundle_dir / "bundle.sha256").write_text(bundle_hash + "\n", encoding="utf-8")

    print(f"tracebundle: wrote {bundle_dir}")
    print(f"tracebundle: verify with `reprocheck {bundle_dir}`")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

"""reprocheck — independently verify an evidence bundle offline.

reprocheck makes verification the easiest path: given any tracebundle/
ProofBench-style bundle, it checks manifest integrity, content addresses
of every artifact, optional bundle hash, and reports clear pass/fail.
No network access. No secrets required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from proofbench.canonical import canonical_json, hash_file


def verify(bundle_dir: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not bundle_dir.exists():
        errors.append(f"bundle not found: {bundle_dir}")
        return False, errors
    if not bundle_dir.is_dir():
        errors.append(f"not a directory: {bundle_dir}")
        return False, errors

    mpath = bundle_dir / "manifest.json"
    if not mpath.exists():
        errors.append("missing manifest.json")
        return False, errors

    try:
        manifest: dict[str, Any] = json.loads(mpath.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"manifest.json is not valid JSON: {e}")
        return False, errors

    artifacts = manifest.get("artifacts", {}) or {}
    if not isinstance(artifacts, dict):
        errors.append("manifest.artifacts must be an object")
        return False, errors

    for name, expected in artifacts.items():
        f = bundle_dir / name
        if not f.exists():
            errors.append(f"MISSING: {name}")
            continue
        got = hash_file(str(f))
        if got != expected:
            errors.append(f"TAMPERED: {name} (hash mismatch)")

    bsha = bundle_dir / "bundle.sha256"
    if bsha.exists():
        expected_b = bsha.read_text(encoding="utf-8").strip()
        got_b = __import__("hashlib").sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
        if got_b != expected_b:
            errors.append("bundle hash mismatch (manifest tampered)")

    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: reprocheck <bundle-dir>\n\n"
            "Verify a tracebundle or compatible evidence bundle offline.\n"
            "Checks manifest, artifact hashes, and optional bundle hash.",
            file=sys.stderr,
        )
        return 0 if args else 2
    ok, errs = verify(Path(args[0]))
    if ok:
        print("reprocheck: PASSED — bundle is intact and verifiably consistent")
        return 0
    print("reprocheck: FAILED", file=sys.stderr)
    for e in errs:
        print(f"  - {e}", file=sys.stderr)
    print("\nTip: verification is offline. No network, no secrets needed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

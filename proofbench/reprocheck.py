"""reprocheck — verify an evidence bundle offline."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from proofbench.canonical import canonical_json, sha256_hex


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: reprocheck <bundle-dir>", file=sys.stderr)
        return 0 if args else 2
    bundle = Path(args[0])
    if not bundle.is_dir():
        print(f"reprocheck: not a directory: {bundle}", file=sys.stderr)
        return 1
    mpath = bundle / "manifest.json"
    if not mpath.exists():
        print(f"reprocheck: missing manifest.json in {bundle}", file=sys.stderr)
        return 1
    try:
        manifest: dict[str, Any] = json.loads(mpath.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"reprocheck: bad manifest: {e}", file=sys.stderr)
        return 1
    h = sha256_hex(canonical_json(manifest).encode())
    selfh = (bundle / "self_hash.txt")
    if selfh.exists() and selfh.read_text().strip() != h:
        print("reprocheck: FAILED (manifest hash mismatch)", file=sys.stderr)
        return 1
    for name, h2 in manifest.get("artifacts", {}).items():
        f = bundle / name
        if not f.exists():
            print(f"reprocheck: MISSING {name}", file=sys.stderr)
            return 1
        from proofbench.tracebundle import _hash_file

        if _hash_file(f) != h2:
            print(f"reprocheck: FAILED (artifact {name} tampered)", file=sys.stderr)
            return 1
    print("reprocheck: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

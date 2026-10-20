"""reprocheck — independently verify an evidence bundle offline."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from proofbench.canonical import hash_file


def verify(bundle_dir: Path | str) -> dict[str, Any]:
    bundle_dir = Path(bundle_dir)
    res: dict[str, Any] = {
        "bundle": str(bundle_dir),
        "ok": True,
        "checks": [],
        "errors": [],
    }
    if not bundle_dir.exists():
        res["ok"] = False
        res["errors"].append(f"bundle not found: {bundle_dir}")
        return res
    if not bundle_dir.is_dir():
        res["ok"] = False
        res["errors"].append(f"not a directory: {bundle_dir}")
        return res

    mpath = bundle_dir / "manifest.json"
    res["checks"].append({"name": "manifest_exists", "ok": mpath.exists()})
    if not mpath.exists():
        res["ok"] = False
        res["errors"].append("missing manifest.json")
        return res

    try:
        manifest: dict[str, Any] = json.loads(mpath.read_text(encoding="utf-8"))
        res["checks"].append({"name": "manifest_json_valid", "ok": True})
    except Exception as e:
        res["ok"] = False
        res["checks"].append({"name": "manifest_json_valid", "ok": False})
        res["errors"].append(f"manifest.json is not valid JSON: {e}")
        return res

    artifacts = manifest.get("artifacts", {}) or {}
    if not isinstance(artifacts, dict):
        res["ok"] = False
        res["errors"].append("manifest.artifacts must be an object")
        return res

    for name, expected in artifacts.items():
        f = bundle_dir / name
        if not f.exists():
            res["ok"] = False
            res["errors"].append(f"MISSING: {name}")
            res["checks"].append({"name": f"artifact.{name}", "ok": False, "error": "missing"})
            continue
        got = hash_file(str(f))
        if name == "manifest.json":
            if got == expected:
                res["checks"].append({"name": f"artifact.{name}", "ok": True})
                continue
            # try alternative: maybe bundle.sha256 is the source of truth
            bsha = bundle_dir / "bundle.sha256"
            if bsha.exists():
                expected_b = bsha.read_text(encoding="utf-8").strip()
                if got == expected_b:
                    res["checks"].append({"name": f"artifact.{name}", "ok": True})
                    continue
            res["ok"] = False
            res["errors"].append(f"TAMPERED: {name} (hash mismatch)")
            res["checks"].append({"name": f"artifact.{name}", "ok": False})
            continue
        if got != expected:
            res["ok"] = False
            res["errors"].append(f"TAMPERED: {name} (hash mismatch)")
            res["checks"].append({"name": f"artifact.{name}", "ok": False})
        else:
            res["checks"].append({"name": f"artifact.{name}", "ok": True})

    bsha = bundle_dir / "bundle.sha256"
    if bsha.exists():
        expected_b = bsha.read_text(encoding="utf-8").strip()
        got_b = hash_file(str(mpath))
        if got_b != expected_b:
            res["ok"] = False
            res["errors"].append("bundle hash mismatch (manifest tampered)")
            res["checks"].append({"name": "bundle_sha256", "ok": False})
        else:
            res["checks"].append({"name": "bundle_sha256", "ok": True})

    return res


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: reprocheck <bundle-dir>\n\n", file=sys.stderr)
        return 0 if args else 2
    as_json = "--json" in args
    target = next((a for a in args if not a.startswith("-")), args[0] if args else ".")
    res = verify(Path(target))
    if as_json:
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
    if res.get("ok"):
        print("reprocheck: PASSED — bundle is intact and verifiably consistent")
        for c in res.get("checks", []):
            if c.get("ok"):
                print(f"  ✓ {c['name']}")
        return 0
    print("reprocheck: FAILED", file=sys.stderr)
    for e in res.get("errors", []):
        print(f"  - {e}", file=sys.stderr)
    print("\nTip: verification is offline. No network, no secrets needed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

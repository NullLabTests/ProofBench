"""eval-audit — audit agent eval harnesses for red flags."""

from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any


def audit_path(p: Path) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if p.is_file():
        texts = [(p.name, p.read_text(encoding="utf-8", errors="ignore"))]
    else:
        texts = []
        for ext in ("*.py", "*.json", "*.yaml", "*.yml", "*.md", "*.txt"):
            for f in p.rglob(ext):
                if "__pycache__" in str(f):
                    continue
                with contextlib.suppress(Exception):
                    texts.append((str(f), f.read_text(encoding="utf-8", errors="ignore")))
    for name, t in texts:
        if re.search(r"\b(train.*test|test.*train)\b.*leak", t, re.I):
            flags.append({"severity": "high", "type": "leakage_hint", "file": name})
        if "baseline" not in t.lower() and "random" not in t.lower() and name.endswith(".py"):
            flags.append({"severity": "med", "type": "no_baseline_hint", "file": name})
        if re.search(r"random\.seed|np\.random\.seed|set_seed", t):
            flags.append({"severity": "info", "type": "seed_set", "file": name})
        if "prompt" in t.lower() and len(t) > 10000 and "hidden" in t.lower():
            flags.append({"severity": "high", "type": "hidden_prompt", "file": name})
    if not any("verify" in n.lower() or "eval" in n.lower() for n, _ in texts):
        flags.append({"severity": "high", "type": "no_verifier", "path": str(p)})
    return flags


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: eval-audit <path>", file=sys.stderr)
        return 0 if args else 2
    p = Path(args[0])
    if not p.exists():
        print(f"eval-audit: not found: {p}", file=sys.stderr)
        return 1
    res = audit_path(p)
    out = {"path": str(p), "flags": res, "count": len(res)}
    print(json.dumps(out, indent=2))
    return 1 if any(f["severity"] == "high" for f in res) else 0


if __name__ == "__main__":
    sys.exit(main())

"""eval-audit — audit agent eval harnesses for red flags.

Catches common reproducibility/eval pitfalls: missing baselines,
train/test leakage hints, non-determinism, unverifiable scoring,
hidden prompts, and missing provenance. Produces human-readable
and JSON reports. 100% offline.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


SUSPICIOUS_EXTS = {".py", ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".csv"}


def _read_texts(root: Path) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    if root.is_file():
        try:
            texts.append((str(root), root.read_text(encoding="utf-8", errors="ignore")))
        except Exception:
            pass
        return texts
    if not root.exists():
        return texts
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in str(p) for part in ("__pycache__", ".git", ".venv", "node_modules")):
            continue
        if p.suffix.lower() not in SUSPICIOUS_EXTS and p.name not in ("README", "LICENSE"):
            continue
        try:
            texts.append((str(p), p.read_text(encoding="utf-8", errors="ignore")))
        except Exception:
            pass
    return texts


def audit_path(root: Path) -> dict[str, Any]:
    texts = _read_texts(root)
    flags: list[dict[str, Any]] = []

    all_text = "\n".join(t for _, t in texts)
    all_names = " ".join(n for n, _ in texts).lower()

    if re.search(r"(train.*test|test.*train).*(leak|overlap|same.*set)", all_text, re.I):
        flags.append({"severity": "high", "type": "train_test_leakage_hint", "evidence": "train/test co-referenced with leak/overlap wording", "fix": "Enforce disjoint train/val/test splits with fixed seeds and document them."})
    if "baseline" not in all_text.lower() and "random" not in all_text.lower():
        flags.append({"severity": "high", "type": "missing_baseline", "evidence": "No 'baseline' or 'random' reference found", "fix": "Add an immutable baseline compared under matched budget."})
    if not re.search(r"random\.seed|np\.random\.seed|torch\.manual_seed|set_seed|seed", all_text):
        flags.append({"severity": "med", "type": "non_determinism_hint", "evidence": "No obvious seed-setting calls found", "fix": "Pin all RNG seeds and log them in the evidence bundle."})
    if "hidden" in all_text.lower() and "prompt" in all_text.lower():
        flags.append({"severity": "high", "type": "hidden_prompt_risk", "evidence": "'hidden' and 'prompt' appear together", "fix": "Move prompts to config, version them, or disclose them. Hidden prompts are unverifiable."})
    if "verify" not in all_names and "verif" not in all_names and "check" not in all_names:
        flags.append({"severity": "high", "type": "no_verifier_found", "evidence": "No verifier/check code detected", "fix": "Scoring must be done by an independent/verifiable component."})
    if not re.search(r"(sha256|hash|artifact|bundle|trace)", all_text):
        flags.append({"severity": "med", "type": "no_provenance", "evidence": "No hashing/artifact/bundle mentions", "fix": "Emit content-addressed artifacts and a verifiable trace."})
    if re.search(r"(api[_-]?key|secret|token)\s*=", all_text):
        flags.append({"severity": "high", "type": "hardcoded_secret_risk", "evidence": "Possible hardcoded secret assignment", "fix": "Use env vars; never log secrets; redact in bundles."})

    score = 100
    for f in flags:
        if f["severity"] == "high":
            score -= 25
        elif f["severity"] == "med":
            score -= 10
        else:
            score -= 2
    score = max(0, score)

    return {
        "path": str(root),
        "files_scanned": len(texts),
        "audit_score": score,
        "grade": "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F",
        "flags": flags,
        "recommendation": "Make claims falsifiable: add baselines, pin seeds, version splits, and publish a verifiable bundle.",
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(
            "usage: eval-audit <path> [--json]\n\n"
            "Audit an agent eval harness for reproducibility and verifiability red flags.\n"
            "Offline. Reports human-readable or JSON output.",
            file=sys.stderr,
        )
        return 0 if args else 2
    as_json = "--json" in args
    root = Path([a for a in args if not a.startswith("-")][0])
    if not root.exists():
        print(f"eval-audit: not found: {root}", file=sys.stderr)
        return 1
    res = audit_path(root)
    if as_json:
        print(json.dumps(res, indent=2))
    else:
        print(f"eval-audit report for {res['path']}")
        print(f"Files scanned: {res['files_scanned']}")
        print(f"Score: {res['audit_score']}/100 (Grade {res['grade']})")
        print("")
        if not res["flags"]:
            print("No obvious red flags detected. Still verify with a tracebundle.")
        else:
            for f in res["flags"]:
                print(f"[{f['severity'].upper()}] {f['type']}: {f['evidence']}")
                print(f"  Fix: {f['fix']}")
                print("")
        print(res["recommendation"])
    if any(f["severity"] == "high" for f in res["flags"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

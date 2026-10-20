"""Artifact and build attestation with SLSA-inspired transparency."""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

from proofbench import __version__
from proofbench.canonical import hash_file, hash_obj


SCHEMA = "attestation/1"


def collect_subjects(paths: list[Path]) -> list[dict[str, Any]]:
    subjects: list[dict[str, Any]] = []
    for p in paths:
        if p.is_file():
            subjects.append({"name": str(p), "digest": {"sha256": hash_file(str(p))}})
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    subjects.append({"name": str(f), "digest": {"sha256": hash_file(str(f))}})
    return subjects


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: proofbench-attest [--out FILE] [path ...]", file=sys.stderr)
        return 0 if args else 2
    out = "attestation.json"
    paths: list[Path] = []
    i = 0
    while i < len(args):
        if args[i] == "--out" and i + 1 < len(args):
            out = args[i + 1]
            i += 2
            continue
        paths.append(Path(args[i]))
        i += 1
    if not paths:
        paths = [Path(".")]

    att: dict[str, Any] = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": collect_subjects(paths),
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://proofbench.dev/buildtype/cli@v1",
                "externalParameters": {"command": sys.argv},
                "internalParameters": {"proofbench_version": __version__},
                "resolvedDependencies": [],
            },
            "runDetails": {
                "builder": {"id": "proofbench-attest"},
                "metadata": {"invocationId": f"{os.getpid()}-{int(time.time())}", "startedOn": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                "byproducts": [],
            },
        },
        "metadata": {
            "schema": SCHEMA,
            "attested_at": time.time(),
            "platform": platform.platform(),
            "python": sys.version,
        },
    }
    att["digest"] = hash_obj(att)
    Path(out).write_text(json.dumps(att, indent=2) + "\n")
    print(f"attestation written to {out} ({len(att['subject'])} subjects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

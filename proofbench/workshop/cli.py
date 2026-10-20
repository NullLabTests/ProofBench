"""Unified workshop CLI."""

from __future__ import annotations

import json
import sys

from proofbench import eval_audit, hermetic_run
from proofbench.attest import attest
from proofbench.ledger import ledger
from proofbench.workshop import reprocheck, tracebundle


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(
            "proofbench-workshop v0.2.0\n\n"
            "Commands:\n"
            "  tracebundle -- <cmd>   Trace any command into a verifiable bundle\n"
            "  verify <bundle>        Verify a bundle (reprocheck)\n"
            "  audit <path>           Audit an eval harness\n"
            "  attest [paths...]      Create SLSA-style attestation\n"
            "  ledger add <json>      Append to verification ledger\n"
            "  ledger verify         Verify ledger chain\n"
            "  hermetic -- <cmd>      Hermetic run with attestation\n",
            file=sys.stderr,
        )
        return 0 if args else 2
    cmd = args[0]
    rest = args[1:]
    if cmd == "tracebundle":
        return tracebundle.main(rest)
    if cmd == "verify":
        return reprocheck.main(rest)
    if cmd == "audit":
        return eval_audit.main(rest)
    if cmd == "attest":
        return attest.main(rest)
    if cmd == "hermetic":
        return hermetic_run.main(rest)
    if cmd == "ledger":
        if not rest:
            print("usage: ledger add|verify", file=sys.stderr)
            return 2
        sub = rest[0]
        if sub == "verify":
            led = ledger.Ledger()
            ok, errs = led.verify()
            if ok:
                print("ledger: OK")
                return 0
            for e in errs:
                print(f"ledger: {e}", file=sys.stderr)
            return 1
        if sub == "add":
            led = ledger.Ledger()
            try:
                entry = json.loads(rest[1]) if len(rest) > 1 else {}
            except Exception:
                entry = {"raw": " ".join(rest[1:])}
            rec = led.append(entry)
            print(json.dumps(rec))
            return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

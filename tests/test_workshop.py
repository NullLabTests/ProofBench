"""Tests for ProofBench Workshop tools."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from proofbench.workshop import tracebundle, reprocheck
from proofbench.attest import attest
from proofbench.ledger import ledger


def test_tracebundle_creates_bundle(tmp_path):
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        rc = tracebundle.main(["--", sys.executable, "-c", "print('test')"])
        assert rc == 0
        bundles = list(tmp_path.glob("tracebundle-*"))
        assert len(bundles) == 1
        b = bundles[0]
        assert (b / "manifest.json").exists()
        assert (b / "stdout.txt").exists()
        assert (b / "stderr.txt").exists()
        assert (b / "env.json").exists()
        assert (b / "bundle.sha256").exists()
        assert (b / "VERIFICATION.md").exists()
        m = json.loads((b / "manifest.json").read_text())
        assert m["schema"] == "tracebundle/1" or m["schema"].startswith("tracebundle/")
        assert "artifacts" in m
        assert "events" in m
        assert "chain_head" in m
    finally:
        os.chdir(old)


def test_reprocheck_passes_valid_bundle(tmp_path):
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        tracebundle.main(["--", sys.executable, "-c", "print('x')"])
        b = list(tmp_path.glob("tracebundle-*"))[0]
        rep = reprocheck.verify(b)
        assert rep["ok"]
        rc = reprocheck.main([str(b)])
        assert rc == 0
    finally:
        os.chdir(old)


def test_reprocheck_detects_tamper(tmp_path):
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        tracebundle.main(["--", sys.executable, "-c", "print('x')"])
        b = list(tmp_path.glob("tracebundle-*"))[0]
        (b / "stdout.txt").write_text("TAMPERED")
        rep = reprocheck.verify(b)
        assert not rep["ok"]
        assert any("TAMPERED" in e for e in rep["errors"])
    finally:
        os.chdir(old)


def test_attest_creates_attestation(tmp_path):
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        (tmp_path / "test.txt").write_text("hello")
        out = tmp_path / "att.json"
        rc = attest.main(["--out", str(out), "test.txt"])
        assert rc == 0
        assert out.exists()
        att = json.loads(out.read_text())
        assert att["_type"] == "https://in-toto.io/Statement/v1"
        assert att["predicateType"] == "https://slsa.dev/provenance/v1"
        assert len(att["subject"]) == 1
        assert "digest" in att
    finally:
        os.chdir(old)


def test_ledger_append_and_verify(tmp_path):
    path = tmp_path / "ledger.jsonl"
    led = ledger.Ledger(path)
    r1 = led.append({"type": "test", "data": 1})
    r2 = led.append({"type": "test", "data": 2})
    assert r1["seq"] == 0
    assert r2["seq"] == 1
    assert r2["prev_hash"] == r1["hash"]
    ok, errs = led.verify()
    assert ok
    assert errs == []


def test_ledger_detects_tamper(tmp_path):
    path = tmp_path / "ledger.jsonl"
    led = ledger.Ledger(path)
    led.append({"type": "test"})
    led.append({"type": "test2"})
    # tamper
    lines = path.read_text().splitlines()
    obj = json.loads(lines[0])
    obj["type"] = "TAMPERED"
    # need canonical
    from proofbench.canonical import canonical_json
    lines[0] = canonical_json(obj)
    path.write_text("\n".join(lines) + "\n")
    ok, errs = led.verify()
    assert not ok
    assert len(errs) > 0

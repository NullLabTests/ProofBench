"""Event chain integrity and artifact store."""

from pathlib import Path

import pytest

from proofbench.errors import IntegrityError
from proofbench.events import EventLog, verify_chain
from proofbench.store import ArtifactStore, atomic_write_json, read_json


def test_event_chain_grows_and_verifies(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    for i in range(5):
        log.append("test_event", {"i": i})
    events = EventLog(tmp_path / "events.jsonl").read_all()
    assert [e["payload"]["i"] for e in events] == [0, 1, 2, 3, 4]
    assert verify_chain(events) == []


def test_chain_detects_payload_edit(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    log.append("a", {"x": 1})
    log.append("b", {"y": 2})
    events = log.read_all()
    events[0]["payload"]["x"] = 999  # tamper with an old event
    failures = verify_chain(events)
    assert failures


def test_chain_detects_deletion(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    for i in range(4):
        log.append("e", {"i": i})
    events = log.read_all()
    del events[1]  # remove one event
    assert verify_chain(events)


def test_chain_detects_reorder(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    log.append("e", {"i": 0})
    log.append("e", {"i": 1})
    events = log.read_all()
    events[0], events[1] = events[1], events[0]
    assert verify_chain(events)


def test_append_after_load_resumes_chain(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    log.append("e", {"i": 0})
    log2 = EventLog(path)  # reload, e.g. after resume
    log2.append("e", {"i": 1})
    assert verify_chain(log2.read_all()) == []


def test_artifact_store_roundtrip(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    digest = store.put_obj({"hello": "world", "n": 3})
    assert store.get_obj(digest) == {"hello": "world", "n": 3}
    assert store.has(digest)
    assert store.verify_all() == []


def test_artifact_store_detects_corruption(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    digest = store.put_obj({"v": 1})
    path = tmp_path / "artifacts" / digest[:2] / digest
    path.write_bytes(b'{"v":2}\n')
    with pytest.raises(IntegrityError, match="integrity"):
        store.get_obj(digest)
    assert store.verify_all()  # verify_all reports the corruption


def test_artifact_store_missing_object(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    with pytest.raises(IntegrityError, match="missing"):
        store.get_obj("0" * 64)


def test_atomic_write_and_read(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "state.json"
    atomic_write_json(p, {"a": 1})
    assert read_json(p) == {"a": 1}
    atomic_write_json(p, {"a": 2})
    assert read_json(p) == {"a": 2}
    # no leftover temp files
    assert list(p.parent.glob(".tmp-*")) == []

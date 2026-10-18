"""Canonical serialization and content addressing."""

from proofbench.canonical import canonical_json, hash_obj, sha256_hex


def test_canonical_json_is_deterministic_and_sorted() -> None:
    a = canonical_json({"b": 1, "a": [1, 2]})
    b = canonical_json({"a": [1, 2], "b": 1})
    assert a == b == '{"a":[1,2],"b":1}'


def test_hash_obj_detects_changes() -> None:
    assert hash_obj({"x": 1}) != hash_obj({"x": 2})
    assert hash_obj({"x": 1}) == hash_obj({"x": 1})


def test_sha256_known_value() -> None:
    # sha256 of empty string, a fixed external constant.
    assert sha256_hex(b"") == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

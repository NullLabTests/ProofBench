"""Model adapter: refuses without configuration; never leaks secrets."""

import pytest

from proofbench.errors import ModelAdapterNotConfigured
from proofbench.model_adapter import OpenAICompatAdapter


def test_refuses_without_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PROOFBENCH_MODEL_ID", "PROOFBENCH_MODEL_API_BASE", "PROOFBENCH_MODEL_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    adapter = OpenAICompatAdapter()
    with pytest.raises(ModelAdapterNotConfigured, match="PROOFBENCH_MODEL_ID"):
        adapter.propose("anything")


def test_partial_configuration_still_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFBENCH_MODEL_ID", "test-model")
    monkeypatch.delenv("PROOFBENCH_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("PROOFBENCH_MODEL_API_BASE", raising=False)
    adapter = OpenAICompatAdapter()
    assert adapter.configured is False
    with pytest.raises(ModelAdapterNotConfigured):
        adapter.propose("anything")


def test_usage_record_never_contains_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFBENCH_MODEL_ID", "m")
    monkeypatch.setenv("PROOFBENCH_MODEL_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("PROOFBENCH_MODEL_API_KEY", "sk-super-secret")
    adapter = OpenAICompatAdapter()
    record = adapter.usage_record()
    assert "sk-super-secret" not in repr(record)
    assert record["model"] == "m"
    # api_base is recorded (it is configuration, not a credential)
    assert record["api_base"] == "https://example.invalid/v1"


def test_no_network_at_import_or_config_time(monkeypatch: pytest.MonkeyPatch) -> None:
    # Constructing the adapter must not perform any request even when fully
    # configured; only propose() may.
    monkeypatch.setenv("PROOFBENCH_MODEL_ID", "m")
    monkeypatch.setenv("PROOFBENCH_MODEL_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("PROOFBENCH_MODEL_API_KEY", "k")
    adapter = OpenAICompatAdapter()
    assert adapter.configured is True
    assert adapter.usage.requests == 0

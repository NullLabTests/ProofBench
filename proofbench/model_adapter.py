"""Optional OpenAI-compatible model adapter.

Design rules (see docs/adapters.md):

* The adapter is **never** required for core experiments.  Without explicit
  operator configuration it raises :class:`ModelAdapterNotConfigured`.
* Credentials come from the environment only (``PROOFBENCH_MODEL_API_KEY``;
  optionally ``PROOFBENCH_MODEL_API_BASE`` and ``PROOFBENCH_MODEL_ID``).  Keys
  are never logged, never written to evidence, and never committed.
* Every request is recorded: model id, parameters, request count, and token
  usage *when the service reports it*.  Reproducibility of stochastic remote
  inference is limited to what the recorded configuration and the service
  actually permit — this adapter makes no stronger claim.
* The adapter produces *proposals* (candidate parameter suggestions); it never
  touches the evaluator, scoring, or acceptance logic.
* No network call is performed at import time or without explicit
  configuration.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from proofbench.errors import ModelAdapterNotConfigured


@dataclass
class ModelUsage:
    requests: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    failures: int = 0
    model: str = ""
    api_base: str = ""
    log: list[dict[str, Any]] = field(default_factory=list)


class OpenAICompatAdapter:
    """Minimal OpenAI-compatible chat-completions client for proposals."""

    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
        temperature: float = 0.0,
    ) -> None:
        self.model = model or os.environ.get("PROOFBENCH_MODEL_ID")
        self.api_base = (api_base or os.environ.get("PROOFBENCH_MODEL_API_BASE", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("PROOFBENCH_MODEL_API_KEY")
        self.timeout = timeout
        self.temperature = temperature
        self.usage = ModelUsage()

    @property
    def configured(self) -> bool:
        return bool(self.model and self.api_base and self.api_key)

    def _require_configured(self) -> None:
        if not self.configured:
            raise ModelAdapterNotConfigured(
                "model adapter requires explicit configuration: set "
                "PROOFBENCH_MODEL_ID, PROOFBENCH_MODEL_API_BASE and "
                "PROOFBENCH_MODEL_API_KEY in the environment (never commit "
                "credentials). Core ProofBench experiments run fully offline "
                "without this adapter."
            )

    def propose(self, prompt: str, context: dict[str, Any] | None = None) -> str:
        """Send one proposal request. Returns the model's text output."""
        self._require_configured()
        assert self.model is not None and self.api_base and self.api_key
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You propose bounded parameter changes for a search "
                        "policy. Reply with a single JSON object mapping "
                        "parameter names to values. Do not include any other "
                        "text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        self.usage.requests += 1
        self.usage.model = self.model
        self.usage.api_base = self.api_base
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self.usage.failures += 1
            self.usage.log.append({"event": "request_failed", "error": type(exc).__name__})
            raise
        text = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage", {})
        self.usage.log.append(
            {
                "event": "request_ok",
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                # NOTE: the request body/prompt is intentionally NOT logged.
            }
        )
        if usage.get("prompt_tokens") is not None:
            self.usage.prompt_tokens = (self.usage.prompt_tokens or 0) + int(usage["prompt_tokens"])
        if usage.get("completion_tokens") is not None:
            self.usage.completion_tokens = (self.usage.completion_tokens or 0) + int(
                usage["completion_tokens"]
            )
        return str(text)

    def usage_record(self) -> dict[str, Any]:
        """Serializable usage record for evidence (never contains the key)."""
        return {
            "model": self.usage.model or (self.model or ""),
            "api_base": self.usage.api_base or self.api_base,
            "requests": self.usage.requests,
            "failures": self.usage.failures,
            "prompt_tokens": self.usage.prompt_tokens,
            "completion_tokens": self.usage.completion_tokens,
            "temperature": self.temperature,
            "log": list(self.usage.log),
        }

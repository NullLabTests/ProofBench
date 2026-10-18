"""Pluggable execution backends.

Learning from SPACE's separation of management, execution, and output
collection, ProofBench defines a small executor interface with explicit
capability advertisement:

* :class:`LocalExecutor` — bounded in-process execution of **trusted built-in
  benchmark functions only** (task families, evaluators, deterministic
  agents).  It applies wall-clock limits via a watchdog thread and is the
  default backend.
* :class:`ContainerExecutor` — for untrusted candidate code in an explicitly
  configured isolated container with network disabled and resource limits.
  If no container runtime is available and configured, it **refuses**
  (:class:`ExecutionUnavailable`); it never silently falls back to host
  execution.

Security honesty: :class:`LocalExecutor` is *not* a security sandbox.  It
exists for trusted built-ins only.  v0.1 does not execute candidate-supplied
code at all — candidates propose bounded parameter patches, which keeps the
trusted computing base small (see docs/threat-model.md).
"""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from proofbench.errors import ExecutionUnavailable

T = TypeVar("T")


@dataclass(frozen=True)
class ExecutorCapabilities:
    name: str
    trusted_only: bool
    network_disabled: bool
    memory_limit: bool
    cpu_limit: bool
    filesystem_isolation: bool


class Executor(ABC):
    capabilities: ExecutorCapabilities

    @abstractmethod
    def run_trusted(self, fn: Callable[[], T], timeout_seconds: float) -> T:
        """Run a trusted built-in callable with a wall-clock bound."""


class LocalExecutor(Executor):
    """In-process bounded execution for trusted built-ins. Not a sandbox."""

    capabilities = ExecutorCapabilities(
        name="local",
        trusted_only=True,
        network_disabled=False,
        memory_limit=False,
        cpu_limit=False,
        filesystem_isolation=False,
    )

    def run_trusted(self, fn: Callable[[], T], timeout_seconds: float) -> T:
        import threading

        result: list[T] = []
        error: list[BaseException] = []

        def target() -> None:
            try:
                result.append(fn())
            except BaseException as exc:  # propagated to caller
                error.append(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout_seconds)
        if thread.is_alive():
            raise TimeoutError(f"trusted call exceeded {timeout_seconds}s wall-clock limit")
        if error:
            raise error[0]
        return result[0]


class ContainerExecutor(Executor):
    """Isolated container execution for untrusted candidate code (optional).

    Requires an explicit container runtime (docker/podman) *and* explicit
    operator configuration.  Network is disabled by default.  Without both,
    every untrusted call raises :class:`ExecutionUnavailable` — ProofBench
    refuses unsafe execution rather than falling back to the host.
    """

    capabilities = ExecutorCapabilities(
        name="container",
        trusted_only=False,
        network_disabled=True,
        memory_limit=True,
        cpu_limit=True,
        filesystem_isolation=True,
    )

    def __init__(
        self,
        runtime: str | None = None,
        image: str | None = None,
        memory: str = "512m",
        cpus: str = "1.0",
    ) -> None:
        self.image = image
        self.memory = memory
        self.cpus = cpus
        self.runtime = runtime or _detect_runtime()
        if self.runtime is None or self.image is None:
            self.available = False
        else:
            self.available = shutil.which(self.runtime) is not None

    def run_untrusted(
        self, command: list[str], timeout_seconds: float, workdir: str | None = None
    ) -> dict[str, Any]:
        if not self.available:
            raise ExecutionUnavailable(
                "container isolation is not available on this host: no container "
                "runtime and/or image configured. ProofBench refuses to execute "
                "untrusted candidate code on the host instead. Install and "
                "configure a container runtime (docker or podman) and re-run with "
                "an explicit image, or keep candidates within the bounded "
                "parameter-patch model (the default)."
            )
        assert self.runtime is not None and self.image is not None
        cmd = [
            self.runtime,
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            self.memory,
            "--cpus",
            self.cpus,
            "--pids-limit",
            "128",
            "--read-only",
        ]
        if workdir:
            cmd += ["-v", f"{workdir}:/work:rw", "-w", "/work"]
        cmd += [self.image, *command]
        proc = subprocess.run(  # fixed argv, no shell
            cmd, capture_output=True, timeout=timeout_seconds, check=False
        )
        return {
            "returncode": proc.returncode,
            "stdout_bytes": len(proc.stdout),
            "stderr_bytes": len(proc.stderr),
            "truncated_stdout": proc.stdout[:4096].decode("utf-8", "replace"),
        }

    def run_trusted(self, fn: Callable[[], T], timeout_seconds: float) -> T:
        # Container executor does not run in-process trusted callables.
        raise ExecutionUnavailable("ContainerExecutor executes subprocesses in containers only")


def _detect_runtime() -> str | None:
    for candidate in ("docker", "podman"):
        if shutil.which(candidate):
            return candidate
    return None


def best_available_executor() -> Executor:
    """Default: local executor for trusted built-ins. Containers are opt-in."""
    return LocalExecutor()

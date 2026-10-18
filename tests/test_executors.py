"""Execution backends: bounded local execution; container refusal."""

import shutil

import pytest

from proofbench.errors import ExecutionUnavailable
from proofbench.executors import ContainerExecutor, LocalExecutor, best_available_executor


def test_local_executor_runs_trusted_call() -> None:
    ex = LocalExecutor()
    assert ex.run_trusted(lambda: 21 * 2, timeout_seconds=5.0) == 42


def test_local_executor_propagates_errors() -> None:
    ex = LocalExecutor()

    def boom() -> None:
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        ex.run_trusted(boom, timeout_seconds=5.0)


def test_local_executor_times_out() -> None:
    import time

    ex = LocalExecutor()
    with pytest.raises(TimeoutError, match="wall-clock"):
        ex.run_trusted(lambda: time.sleep(3.0), timeout_seconds=0.2)


def test_local_executor_is_honestly_not_a_sandbox() -> None:
    ex = LocalExecutor()
    assert ex.capabilities.filesystem_isolation is False
    assert ex.capabilities.network_disabled is False


def test_container_executor_refuses_without_runtime() -> None:
    if shutil.which("docker") or shutil.which("podman"):
        pytest.skip("container runtime present; refusal path not applicable on this host")
    ex = ContainerExecutor(image=None)
    with pytest.raises(ExecutionUnavailable, match="refuses"):
        ex.run_untrusted(["true"], timeout_seconds=5.0)


def test_container_runtime_without_image_also_refuses() -> None:
    ex = ContainerExecutor(image=None)
    with pytest.raises(ExecutionUnavailable):
        ex.run_untrusted(["true"], timeout_seconds=5.0)


def test_default_executor_is_local() -> None:
    assert isinstance(best_available_executor(), LocalExecutor)

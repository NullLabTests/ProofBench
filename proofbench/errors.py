"""Explicit error types and process exit codes for ProofBench.

Exit codes are part of the CLI contract and documented in docs/cli.md.
"""

from __future__ import annotations


class ProofBenchError(Exception):
    """Base class for all ProofBench errors."""

    exit_code = 1


class SpecValidationError(ProofBenchError):
    """An experiment specification is malformed or semantically invalid."""

    exit_code = 3


class PolicyViolation(ProofBenchError):
    """A candidate attempted an action outside its permitted modification boundary."""

    exit_code = 6


class IntegrityError(ProofBenchError):
    """An artifact, event chain, or bundle failed an integrity check."""

    exit_code = 4


class BudgetExhausted(ProofBenchError):
    """An evaluation or time budget was fully consumed."""

    exit_code = 7


class ExecutionUnavailable(ProofBenchError):
    """A required execution backend (e.g. container isolation) is not available.

    ProofBench refuses unsafe execution rather than silently falling back to an
    untrusted host execution path.
    """

    exit_code = 8


class RunNotFound(ProofBenchError):
    """The referenced run id or path does not exist."""

    exit_code = 9


class VerificationFailed(ProofBenchError):
    """An evidence bundle failed verification."""

    exit_code = 4


class ModelAdapterNotConfigured(ProofBenchError):
    """A model-backed agent was requested but no external service is configured."""

    exit_code = 10


EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_USAGE = 2

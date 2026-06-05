"""Error hierarchy for Q-day Clock.

Per CLAUDE.md §8, errors do not get silently swallowed. Every failure
mode below carries an ``error_code`` that lets callers, tests, and CI
distinguish *what* went wrong without parsing message strings.
"""

from __future__ import annotations


class QDayClockError(Exception):
    """Base class for all Q-day Clock errors."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class CanonicalizationError(QDayClockError):
    """Raised when an object has no canonical JSON representation."""


class SignatureError(QDayClockError):
    """Raised when Ed25519 sign / verify / serialization fails."""


class SchemaError(QDayClockError):
    """Raised when a pydantic model fails domain-level validation
    (e.g. weights do not sum to 1.0)."""


class IngestError(QDayClockError):
    """Raised when signal ingest fails (bad manifest, missing fields,
    or a stale Curator commit).

    Never swallowed silently; the ingest layer surfaces this to the
    refresh workflow and the workflow opens a PR showing the error log."""


class ExtractError(QDayClockError):
    """Raised when an axis extractor cannot determine a numeric reading
    from an article that nominally matched its keyword set."""


class GateError(QDayClockError):
    """Raised when a Goodhart gate is misconfigured (not when it fires;
    firing is a normal verdict)."""


class ThresholdDriftError(QDayClockError):
    """Raised by ThresholdGuard when the hash-locked threshold file
    drifts from the version-controlled snapshot."""

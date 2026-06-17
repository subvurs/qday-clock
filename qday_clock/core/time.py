"""UTC normalization and freshness-window helpers.

All timestamps in Q-day Clock are stored and signed in UTC. Signal
freshness is computed in days (not weeks / months) so that the
``StaleSignalGate`` and history rendering are agreement-free.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=UTC)


def to_utc(value: datetime) -> datetime:
    """Normalize a datetime to UTC. Naive datetimes are assumed to be UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso(value: datetime) -> str:
    """Serialize a datetime to an RFC 3339 / ISO 8601 UTC string ending in Z."""
    value = to_utc(value)
    # strftime to ensure deterministic output across platforms; we
    # explicitly emit microseconds=0 for stable canonicalization.
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def days_between(a: datetime, b: datetime) -> float:
    """Return ``|a - b|`` in days, as a float."""
    delta = to_utc(a) - to_utc(b)
    return abs(delta.total_seconds()) / 86400.0

"""UTC time helper unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from qday_clock.core.time import days_between, iso, to_utc, utcnow


def test_utcnow_is_utc() -> None:
    now = utcnow()
    assert now.tzinfo is not None
    assert now.tzinfo.utcoffset(now) == timedelta(0)


def test_to_utc_naive_assumes_utc() -> None:
    naive = datetime(2026, 5, 1, 12, 0, 0)
    converted = to_utc(naive)
    assert converted.tzinfo is UTC


def test_to_utc_converts_eastern_offset() -> None:
    eastern = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone(timedelta(hours=-4)))
    converted = to_utc(eastern)
    assert converted.hour == 12  # 8am EDT == 12 noon UTC
    assert converted.tzinfo is UTC


def test_iso_round_trip() -> None:
    dt = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    text = iso(dt)
    assert "2026-05-01" in text


def test_days_between() -> None:
    a = datetime(2026, 5, 1, tzinfo=UTC)
    b = datetime(2026, 5, 11, tzinfo=UTC)
    assert days_between(a, b) == pytest.approx(10.0)

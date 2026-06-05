"""Axis-4 (error rate floor) extractor unit tests."""

from __future__ import annotations

import pytest

from qday_clock.extract.axis_error_rate import extract, matches


# ---------------------------------------------------------------------------
# Keyword gate
# ---------------------------------------------------------------------------


def test_matches_on_keyword() -> None:
    assert matches("Two-qubit gate error reduced", "")
    assert not matches("Quantum stock roundup", "no relevant content")


def test_no_keyword_returns_none() -> None:
    assert extract("Unrelated headline", "no relevant content") is None


# ---------------------------------------------------------------------------
# Explicit error rate parsing
# ---------------------------------------------------------------------------


def test_one_percent_gate_error_floors_at_zero() -> None:
    res = extract("New chip with 1% two-qubit gate error", "")
    assert res is not None
    assert res.error_rate == pytest.approx(0.01)
    assert res.normalized_value == pytest.approx(0.0)


def test_one_in_one_thousand_gate_error_mid_anchor() -> None:
    """0.1 % = 1e-3 → log-interp y = (-2 - (-3))/3 = 1/3."""
    res = extract("Vendor reports 0.1% gate error", "")
    assert res is not None
    assert res.error_rate == pytest.approx(1e-3)
    assert res.normalized_value == pytest.approx(1.0 / 3.0, abs=1e-6)


def test_one_in_ten_thousand_two_thirds_anchor() -> None:
    """1e-4 → y = (-2 - (-4))/3 = 2/3."""
    res = extract("Demonstrated two-qubit error 0.01%", "")
    assert res is not None
    assert res.error_rate == pytest.approx(1e-4)
    assert res.normalized_value == pytest.approx(2.0 / 3.0, abs=1e-6)


def test_one_in_one_hundred_thousand_pegs_to_one() -> None:
    res = extract("Two-qubit gate error 0.001%", "")
    assert res is not None
    assert res.error_rate == pytest.approx(1e-5)
    assert res.normalized_value == pytest.approx(1.0)


def test_below_floor_clamps_to_one() -> None:
    res = extract("Two-qubit gate error 1e-7 reported", "speculative")
    assert res is not None
    assert res.normalized_value == pytest.approx(1.0)


def test_scientific_notation_parsing() -> None:
    res = extract("gate error 5e-3 in latest chip", "")
    assert res is not None
    assert res.error_rate == pytest.approx(5e-3, rel=1e-3)


def test_decimal_error_rate() -> None:
    res = extract("gate error 0.0005 reported", "two-qubit calibration")
    assert res is not None
    assert res.error_rate == pytest.approx(5e-4, rel=1e-3)


# ---------------------------------------------------------------------------
# Fidelity → error conversion
# ---------------------------------------------------------------------------


def test_fidelity_percent_to_error() -> None:
    res = extract("Gate fidelity 99.9% measured", "two-qubit gate error mentioned")
    assert res is not None
    assert res.error_rate == pytest.approx(1e-3, rel=1e-2)
    assert res.source_kind == "fidelity_conversion"


def test_fidelity_decimal_to_error() -> None:
    res = extract("gate fidelity 0.9999 demonstrated", "two-qubit gate error mentioned")
    assert res is not None
    assert res.error_rate == pytest.approx(1e-4, rel=1e-2)


def test_explicit_error_preferred_over_fidelity_on_tie() -> None:
    """When both channels yield the same numeric, prefer the explicit reading."""
    res = extract(
        "two-qubit gate error 0.001 measured",
        "gate fidelity 99.9% reported",
    )
    assert res is not None
    assert res.source_kind == "explicit_error"


# ---------------------------------------------------------------------------
# Multi-value selection
# ---------------------------------------------------------------------------


def test_takes_smallest_error_when_multiple() -> None:
    """Two error rates in one article → take the better (smaller)."""
    res = extract(
        "two-qubit gate error 1% baseline; gate error 0.01% on best chain",
        "",
    )
    assert res is not None
    assert res.error_rate == pytest.approx(1e-4)


# ---------------------------------------------------------------------------
# T1/T2 only → None
# ---------------------------------------------------------------------------


def test_t1_t2_only_returns_none() -> None:
    """Keyword matches but no gate-error / fidelity numeric → fail-conservative."""
    res = extract("T1 of 100 microseconds reported", "T2 also improved")
    assert res is None


# ---------------------------------------------------------------------------
# Implausible values rejected
# ---------------------------------------------------------------------------


def test_implausible_high_fidelity_rejected() -> None:
    """A 'fidelity 99.99999%' parses to 1e-7 error → clamps to 1.0; that is
    fine. But '50% fidelity' is implausibly low for axis-4 and should NOT
    register."""
    res = extract("gate fidelity 50% on broken chain", "two-qubit gate error")
    assert res is None


def test_rationale_string_present() -> None:
    res = extract("gate error 5e-4 reported", "")
    assert res is not None
    assert res.rationale  # non-empty

"""Axis-2 (physical qubit scaling) extractor unit tests."""

from __future__ import annotations

import math

import pytest

from qday_clock.extract.axis_physical_scaling import extract, matches


def test_matches_on_keyword() -> None:
    assert matches("IBM Condor 1121 qubit processor", "")
    assert matches("", "Google announces Willow physical qubits")
    assert not matches("Q3 earnings report", "vendor outlook positive")


def test_no_keyword_returns_none() -> None:
    assert extract("Generic tech roundup", "no quantum content") is None


def test_keyword_match_without_numeric_returns_none() -> None:
    # Hits a vendor keyword but cites no numeric qubit count — fail-conservative.
    assert extract("PsiQuantum updates roadmap", "no qubit count cited") is None


def test_one_hundred_qubit_floor() -> None:
    """100 qubits is the lower NISQ anchor → 0.0."""
    res = extract("100-qubit processor announced", "physical qubits")
    assert res is not None
    assert res.n_qubits == 100
    assert res.normalized_value == 0.0


def test_below_floor_clamps_to_zero() -> None:
    """A 50-qubit announcement floors at 0.0."""
    res = extract("Tempo 64-qubit chip", "vendor announcement")
    # 64 qubits < 100 floor → 0.0
    assert res is not None
    assert res.n_qubits == 64
    assert res.normalized_value == 0.0


def test_ten_thousand_qubit_mid_anchor() -> None:
    """10,000 physical qubits maps to 0.4 exactly."""
    res = extract("10,000 physical qubits milestone", "")
    assert res is not None
    assert res.n_qubits == 10_000
    assert res.normalized_value == pytest.approx(0.4)


def test_one_million_qubit_anchor() -> None:
    """1,000,000 physical qubits maps to 0.7 exactly."""
    res = extract("PsiQuantum 1,000,000 physical qubits target", "")
    assert res is not None
    assert res.n_qubits == 1_000_000
    assert res.normalized_value == pytest.approx(0.7)


def test_twenty_million_qubit_ceiling() -> None:
    """20M qubits == Gidney-Ekera RSA-2048 estimate → 1.0."""
    res = extract("20,000,000 physical qubits required for RSA-2048", "")
    assert res is not None
    assert res.n_qubits == 20_000_000
    assert res.normalized_value == 1.0


def test_above_ceiling_clamps_to_one() -> None:
    res = extract("50,000,000 physical qubits projected", "")
    assert res is not None
    assert res.normalized_value == 1.0


def test_log_linear_between_anchors() -> None:
    """1000 qubits sits halfway (in log space) between 100 and 10k → 0.2."""
    res = extract("1000-qubit processor announced", "")
    assert res is not None
    assert res.n_qubits == 1_000
    # log10(1000)=3 sits halfway between log10(100)=2 and log10(10k)=4,
    # so y = 0.0 + 0.5*(0.4-0.0) = 0.2
    assert res.normalized_value == pytest.approx(0.2)


def test_comma_thousands_parsed() -> None:
    """Thousands-separator commas survive parsing."""
    res = extract("IBM Condor 1,121 qubit processor", "")
    assert res is not None
    assert res.n_qubits == 1_121


def test_takes_largest_count_in_blob() -> None:
    """Multiple counts in one article → use the largest."""
    res = extract(
        "IBM Condor 1121-qubit processor",
        "Successor Flamingo will reach 1386 physical qubits",
    )
    assert res is not None
    assert res.n_qubits == 1_386


def test_rejects_implausible_small() -> None:
    """A '5-qubit demo' should NOT register — below the 10-qubit plausibility floor."""
    res = extract("5-qubit teaching demo", "Atom Computing toy example")
    assert res is None


def test_rationale_string_present() -> None:
    res = extract("133 qubits announced", "physical qubits")
    assert res is not None
    assert res.rationale  # non-empty
    assert "133" in res.rationale


def test_log_linear_continuity() -> None:
    """Spot-check monotonicity: more qubits → higher reading inside band."""
    a = extract("500 physical qubits", "")
    b = extract("5,000 physical qubits", "")
    c = extract("50,000 physical qubits", "")
    assert a is not None and b is not None and c is not None
    assert a.normalized_value < b.normalized_value < c.normalized_value


def test_log_anchor_arithmetic() -> None:
    """Verify the log-interp formula at a numerically clean point.

    100,000 qubits sits at log10(1e5)=5, halfway between log10(1e4)=4 and
    log10(1e6)=6, so y = 0.4 + 0.5*(0.7-0.4) = 0.55.
    """
    res = extract("100,000 physical qubits", "")
    assert res is not None
    assert res.normalized_value == pytest.approx(0.55)
    # Sanity: matches the helper's anchor arithmetic.
    x = math.log10(100_000.0)
    y = 0.4 + (x - 4.0) / (6.0 - 4.0) * (0.7 - 0.4)
    assert res.normalized_value == pytest.approx(y)

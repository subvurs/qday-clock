"""Axis-3 (resource estimate + AES-128/Grover) extractor unit tests."""

from __future__ import annotations

import pytest

from qday_clock.extract.axis_resource_estimate import (
    AES_SUB_WEIGHT,
    extract,
    matches,
)

# ---------------------------------------------------------------------------
# Keyword gate
# ---------------------------------------------------------------------------


def test_matches_on_shor_keyword() -> None:
    assert matches("Improved Shor estimate for RSA-2048", "")


def test_matches_on_grover_keyword() -> None:
    assert matches("Grover attack on AES-128 refined", "")


def test_no_keyword_returns_none() -> None:
    assert extract("Quantum stock roundup", "Q4 earnings") is None


# ---------------------------------------------------------------------------
# Shor channel — qubits-to-factor
# ---------------------------------------------------------------------------


def test_shor_baseline_20m_qubits_maps_to_zero() -> None:
    res = extract("Gidney-Ekera RSA-2048 estimate: 20 million qubits", "")
    assert res is not None
    assert res.channel == "shor"
    assert res.qubits_to_factor == 20_000_000
    assert res.normalized_value == pytest.approx(0.0)


def test_shor_one_million_qubits_maps_to_half() -> None:
    res = extract("Factor RSA-2048 with 1 million qubits", "")
    assert res is not None
    assert res.qubits_to_factor == 1_000_000
    assert res.normalized_value == pytest.approx(0.5)


def test_shor_100k_qubits_pegs_to_one() -> None:
    res = extract("100,000 qubits sufficient to factor RSA-2048", "")
    assert res is not None
    assert res.qubits_to_factor == 100_000
    assert res.normalized_value == pytest.approx(1.0)


def test_shor_below_floor_clamps_to_one() -> None:
    """Sub-100k qubit factoring claim → ceiling at 1.0 (closer to Q-day)."""
    res = extract("Factor RSA-2048 with 50,000 qubits", "")
    assert res is not None
    assert res.normalized_value == pytest.approx(1.0)


def test_shor_above_ceiling_clamps_to_zero() -> None:
    """100M qubit estimate is worse than Gidney-Ekera → 0.0."""
    res = extract("100 million qubits to factor RSA-2048", "")
    assert res is not None
    assert res.normalized_value == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Shor channel — time-to-factor
# ---------------------------------------------------------------------------


def test_shor_8_hours_anchors_to_zero() -> None:
    res = extract("Factoring RSA-2048 in 8 hours on future hardware", "")
    assert res is not None
    assert res.time_to_factor_minutes == pytest.approx(8 * 60.0)
    assert res.normalized_value == pytest.approx(0.0)


def test_shor_one_hour_anchors_to_half() -> None:
    res = extract("Improved factoring of RSA-2048 in 1 hour", "")
    assert res is not None
    assert res.normalized_value == pytest.approx(0.5)


def test_shor_one_minute_pegs_to_one() -> None:
    res = extract("Factor RSA-2048 in 1 minute (theoretical)", "")
    assert res is not None
    assert res.normalized_value == pytest.approx(1.0)


def test_shor_both_qubits_and_time_takes_max() -> None:
    """When both channels present, take the channel closest to Q-day."""
    res = extract(
        "Factor RSA-2048 in 1 hour with 1 million qubits",
        "",
    )
    assert res is not None
    # Both map to 0.5; result is 0.5.
    assert res.normalized_value == pytest.approx(0.5)


def test_shor_keyword_without_numeric_returns_none() -> None:
    res = extract("RSA-2048 will eventually fall to Shor", "general commentary")
    assert res is None


# ---------------------------------------------------------------------------
# AES/Grover sub-channel
# ---------------------------------------------------------------------------


def test_aes_grover_baseline_mention_capped_by_sub_weight() -> None:
    """Bare 'Grover on AES-128' mention → severity 0.3, after fold ≈ 0.09."""
    res = extract("Grover algorithm applied to AES-128 keyspace", "")
    assert res is not None
    assert res.channel == "aes_grover"
    assert res.normalized_value == pytest.approx(0.3 * AES_SUB_WEIGHT)


def test_aes_grover_constant_factor_improvement() -> None:
    """An improved Grover-on-AES-128 estimate → severity 0.5, folded to 0.15."""
    res = extract("Improved Grover circuit for AES-128 with reduced T-count", "")
    assert res is not None
    assert res.channel == "aes_grover"
    assert res.normalized_value == pytest.approx(0.5 * AES_SUB_WEIGHT)


def test_aes_grover_claimed_break_pegs_sub_channel_to_one() -> None:
    """A practical-break claim → severity 1.0, folded to 0.30."""
    res = extract("AES-128 practical break demonstrated via Grover", "")
    assert res is not None
    assert res.channel == "aes_grover"
    assert res.normalized_value == pytest.approx(AES_SUB_WEIGHT)


def test_aes_without_grover_returns_none() -> None:
    """AES-128 mentioned but no Grover → not an axis-3 signal."""
    res = extract("AES-128 still considered secure for symmetric primitives", "")
    assert res is None


# ---------------------------------------------------------------------------
# Sub-weight invariant
# ---------------------------------------------------------------------------


def test_aes_signal_never_exceeds_sub_weight() -> None:
    """No AES signal can contribute more than ``AES_SUB_WEIGHT`` to the axis."""
    res = extract("AES-128 practical break via Grover", "")
    assert res is not None
    assert res.normalized_value <= AES_SUB_WEIGHT + 1e-9


# ---------------------------------------------------------------------------
# Monotonicity sanity
# ---------------------------------------------------------------------------


def test_shor_qubits_monotone_severity() -> None:
    """Fewer qubits → higher (closer-to-Q-day) reading."""
    a = extract("Factor RSA-2048 with 10 million qubits", "")
    b = extract("Factor RSA-2048 with 1 million qubits", "")
    c = extract("Factor RSA-2048 with 200,000 qubits", "")
    assert a is not None and b is not None and c is not None
    assert a.normalized_value < b.normalized_value < c.normalized_value


def test_shor_time_monotone_severity() -> None:
    """Shorter time → higher reading."""
    a = extract("Factor RSA-2048 in 5 hours", "")
    b = extract("Factor RSA-2048 in 30 minutes", "")
    c = extract("Factor RSA-2048 in 2 minutes", "")
    assert a is not None and b is not None and c is not None
    assert a.normalized_value < b.normalized_value < c.normalized_value

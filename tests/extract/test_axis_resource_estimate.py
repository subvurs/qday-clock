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
    assert res.channel == "shor_rsa"
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


# ---------------------------------------------------------------------------
# RSA channel — Gidney 2025 phrasing ("a million noisy qubits")
# ---------------------------------------------------------------------------


def test_gidney_2025_indefinite_article_million_noisy_qubits() -> None:
    """Gidney 2025 (arXiv 2505.15917) title phrasing.

    "factor 2048 bit RSA integers with less than a million noisy qubits":
    the indefinite article "a" → 1, magnitude "million", and the
    physical-class adjective "noisy" must all parse to 1,000,000 qubits
    → axis reading 0.5 (on the ≤1M anchor).
    """
    res = extract(
        "How to factor 2048 bit RSA integers with less than a million noisy qubits",
        "",
    )
    assert res is not None
    assert res.channel == "shor_rsa"
    assert res.qubits_to_factor == 1_000_000
    assert res.normalized_value == pytest.approx(0.5)


def test_error_corrected_qubit_adjective_parses() -> None:
    res = extract("Factor RSA-2048 with 500,000 error-corrected qubits", "")
    assert res is not None
    assert res.qubits_to_factor == 500_000


# ---------------------------------------------------------------------------
# ECC-256 channel (Google Quantum AI 2026, arXiv 2603.28846)
# ---------------------------------------------------------------------------


def test_ecc_physical_qubits_uses_shared_anchor_map() -> None:
    """ECDLP-256 at <500k physical qubits → ~0.65 on the shared anchor.

    Per THREAT_MODEL.md, ECC-256 is a primary Shor target tracked under
    the same axis-3 anchor map as RSA. 500k physical qubits interpolates
    between the 1M→0.5 and 100k→1.0 anchors.
    """
    res = extract(
        "Securing Elliptic Curve Cryptocurrencies against Quantum Vulnerabilities",
        "Breaking ECDLP-256 on secp256k1 could require fewer than 500,000 "
        "physical qubits.",
    )
    assert res is not None
    assert res.channel == "shor_ecc"
    assert res.qubits_to_factor == 500_000
    assert res.normalized_value == pytest.approx(0.65, abs=0.01)


def test_ecc_secp256k1_keyword_gates_the_axis() -> None:
    assert matches("secp256k1 discrete-log resource estimate", "200,000 qubits")


def test_ecc_logical_qubit_count_is_not_fed_to_physical_anchor() -> None:
    """The ECC paper's "~1450 logical qubits" is Axis 1's scale, not
    Axis 3's physical anchor. With only a logical count present and no
    physical/time numeric, axis-3 fails conservative (returns None)
    rather than pegging to 1.0 off a 1450-count."""
    res = extract(
        "Breaking Bitcoin ECDSA on secp256k1",
        "The optimized circuit needs about 1450 logical qubits.",
    )
    assert res is None


def test_ecc_without_numeric_returns_none() -> None:
    res = extract("Elliptic curve cryptography and the quantum threat", "commentary")
    assert res is None


def test_rsa_and_ecc_both_named_labels_as_rsa() -> None:
    """A paper naming both primitives is labelled by its RSA framing;
    the numeric mapping is identical for either channel."""
    res = extract(
        "Resource estimates for RSA-2048 and ECDLP-256",
        "Both fall with 800,000 physical qubits.",
    )
    assert res is not None
    assert res.channel == "shor_rsa"
    assert res.qubits_to_factor == 800_000

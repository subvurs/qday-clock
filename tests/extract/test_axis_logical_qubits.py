"""Axis-1 (logical qubits) extractor unit tests."""

from __future__ import annotations

from qday_clock.extract.axis_logical_qubits import extract, matches


def test_matches_on_keyword() -> None:
    assert matches("Distance-7 surface code", "")
    assert matches("", "we report a logical qubit demonstration")
    assert not matches("Q3 earnings report", "vendor outlook positive")


def test_extracts_distance_3_to_zero_anchor() -> None:
    # Must include a LOGICAL_QUBIT_KEYWORDS hit ("surface code") so the
    # keyword gate fires before numeric extraction.
    res = extract("Distance-3 surface code demo", "")
    assert res is not None
    assert res.distance == 3
    assert res.normalized_value == 0.0


def test_extracts_distance_7_to_half_anchor() -> None:
    res = extract("Distance-7 surface code below threshold", "")
    assert res is not None
    assert res.distance == 7
    assert res.normalized_value == 0.5


def test_extracts_distance_11() -> None:
    res = extract("d = 11 surface code memory", "")
    assert res is not None
    assert res.distance == 11
    assert res.normalized_value == 0.5  # still in 7..11 band


def test_extracts_n_logical_below_threshold() -> None:
    res = extract(
        "12 logical qubits below threshold using bb code",
        "",
    )
    assert res is not None
    assert res.n_logical == 12
    # 12 logical + below-threshold => 0.85
    assert res.normalized_value == 0.85


def test_no_match_returns_none() -> None:
    assert extract("Stock market update", "no relevant content") is None


def test_keyword_match_without_numeric_returns_none() -> None:
    # Matches keyword "logical qubit" but no numeric to anchor on.
    res = extract("logical qubit advances", "vendor blog post")
    assert res is None


def test_shor_on_rsa_2048_on_hardware_pegs_to_one() -> None:
    res = extract(
        "Shor's algorithm factors RSA-2048 on IBM hardware",
        "distance-25 logical qubits used",
    )
    assert res is not None
    assert res.normalized_value == 1.0

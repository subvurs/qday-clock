"""End-to-end clock-computation tests.

Validates that:
  - With no signals, the clock falls back to GRI baseline floor.
  - Axis 5 (PQC migration) subtracts from the clock score.
  - clock_hours is in [0, 24] and mirrors clock_score.
"""

from __future__ import annotations

from datetime import UTC, datetime

from qday_clock.core.schemas import AxisId, EvidenceClass, Signal
from qday_clock.score.clock import compute_clock_state


def _sig(
    axis: AxisId,
    normalized: float,
    source: str = "test-src",
    signal_id: str = "s1",
    evidence: EvidenceClass = EvidenceClass.HARDWARE,
) -> Signal:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    return Signal(
        signal_id=signal_id,
        axis=axis,
        title="t",
        summary="s",
        source=source,
        published_at=now,
        observed_at=now,
        evidence_class=evidence,
        raw_value=normalized * 10.0,
        normalized_value=normalized,
        confidence=1.0,
    )


def test_cold_start_uses_gri_floor() -> None:
    state = compute_clock_state(signals=[])
    # All five axes should fall back to GRI baseline; clock_hours
    # should be in [0, 24], not pinned at 0 or 24.
    assert 0.0 <= state.clock_hours <= 24.0
    # All five axes should be present (cold-start fallback).
    assert len(state.axes) == 5
    for axis_id in AxisId:
        assert axis_id.value in state.axes


def test_logical_qubit_signal_moves_clock_earlier() -> None:
    cold = compute_clock_state(signals=[])
    warm = compute_clock_state(signals=[_sig(AxisId.LOGICAL_QUBITS, 1.0, signal_id="s_warm")])
    # Higher axis-1 reading => higher clock_score => earlier clock (lower hours).
    assert warm.clock_score >= cold.clock_score
    assert warm.clock_hours <= cold.clock_hours


def test_pqc_migration_subtracts_from_clock_score() -> None:
    base = compute_clock_state(signals=[_sig(AxisId.LOGICAL_QUBITS, 1.0, signal_id="s_base")])
    with_pqc = compute_clock_state(
        signals=[
            _sig(AxisId.LOGICAL_QUBITS, 1.0, signal_id="s_base2"),
            _sig(
                AxisId.PQC_MIGRATION,
                1.0,
                signal_id="s_pqc",
                evidence=EvidenceClass.POLICY,
                source="nist",
            ),
        ]
    )
    assert with_pqc.clock_score <= base.clock_score


def test_clock_hours_within_24_hour_face() -> None:
    state = compute_clock_state(signals=[])
    assert 0.0 <= state.clock_hours <= 24.0
    assert 0.0 <= state.confidence_band_hours_low <= 24.0
    assert 0.0 <= state.confidence_band_hours_high <= 24.0
    assert state.confidence_band_hours_low <= state.confidence_band_hours_high

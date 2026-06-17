"""Pydantic schema unit tests.

Sum-to-1.0 weight invariant, axis-key whitelist, confidence-band
ordering, [0,1] reading clipping.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from qday_clock.core.errors import SchemaError
from qday_clock.core.schemas import (
    AxisId,
    AxisReading,
    EvidenceClass,
    RubricWeights,
    Signal,
)


def test_rubric_weights_must_sum_to_one() -> None:
    with pytest.raises(SchemaError):
        RubricWeights(
            logical_qubits=0.25,
            physical_scaling=0.15,
            resource_estimate=0.30,
            error_rate=0.15,  # totals 0.85
            pqc_subtraction=0.5,
        )


def test_default_weights_validate() -> None:
    weights = RubricWeights.default()
    total = (
        weights.logical_qubits
        + weights.physical_scaling
        + weights.resource_estimate
        + weights.error_rate
    )
    assert abs(total - 1.0) < 1e-9


def test_axis_reading_band_ordering() -> None:
    with pytest.raises(SchemaError):
        AxisReading(
            axis=AxisId.LOGICAL_QUBITS,
            reading=0.5,
            confidence_band_low=0.7,
            confidence_band_high=0.3,
        )


def test_axis_reading_clamps_to_unit() -> None:
    # Reading outside [0,1] should be rejected by pydantic.
    with pytest.raises(ValidationError):
        AxisReading(
            axis=AxisId.LOGICAL_QUBITS,
            reading=1.5,
            confidence_band_low=0.0,
            confidence_band_high=1.0,
        )


def test_signal_is_frozen() -> None:
    s = Signal(
        signal_id="abc",
        axis=AxisId.LOGICAL_QUBITS,
        title="t",
        summary="s",
        source="src",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
        evidence_class=EvidenceClass.HARDWARE,
        raw_value=7.0,
        normalized_value=0.5,
        confidence=1.0,
    )
    with pytest.raises(ValidationError):
        s.normalized_value = 0.9  # type: ignore[misc]

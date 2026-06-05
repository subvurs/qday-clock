"""SVG renderer smoke tests.

Per plan section G: SVG renders without error.

We don't pixel-diff the SVG (font rendering varies by platform); we
only assert the structural invariants:

- Well-formed root <svg> element
- Hand line present
- 24 tick lines present (one per hour)
- aria-label on the root for screen-reader access
- Hand angle matches hours_to_angle()
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

import pytest

from qday_clock.core.schemas import (
    AxisId,
    AxisReading,
    ClockState,
    RubricWeights,
)
from qday_clock.render.svg_clock import hours_to_angle, render_svg


def _stub_state(hours: float) -> ClockState:
    axis_reading = AxisReading(
        axis=AxisId.LOGICAL_QUBITS,
        reading=0.5,
        contributing_signal_ids=[],
        n_independent_sources=0,
        confidence_band_low=0.4,
        confidence_band_high=0.6,
        note="stub",
    )
    axes = {a.value: axis_reading.model_copy(update={"axis": a}) for a in AxisId}
    return ClockState(
        version="0.1.0",
        generated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        clock_score=1.0 - hours / 24.0,
        clock_hours=hours,
        confidence_band_hours_low=max(0.0, hours - 1.0),
        confidence_band_hours_high=min(24.0, hours + 1.0),
        axes=axes,
        weights=RubricWeights.default(),
        gri_baseline_year=2024,
        gri_baseline_label="GRI 2024 - median CRQC arrival ~ 2034",
        gates_fired=[],
        methodology_url="https://example.invalid/methodology",
    )


def test_render_svg_well_formed() -> None:
    state = _stub_state(hours=18.0)
    svg = render_svg(state)
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert 'role="img"' in svg
    assert "aria-label=" in svg


def test_render_svg_has_24_ticks() -> None:
    state = _stub_state(hours=12.0)
    svg = render_svg(state)
    # Tick lines are the only <line> elements that aren't the hand;
    # the hand has stroke-width 4, ticks have stroke-width 1 or 2.
    line_count = len(re.findall(r"<line\b", svg))
    # 24 ticks + 1 clock hand = 25 line elements
    assert line_count == 25, f"expected 25 lines (24 ticks + 1 hand), got {line_count}"


def test_hours_to_angle_midnight() -> None:
    # Midnight (00:00) must point to the top: SVG angle -90 degrees.
    assert hours_to_angle(0.0) == pytest.approx(-90.0)


def test_hours_to_angle_six_oclock() -> None:
    assert hours_to_angle(6.0) == pytest.approx(0.0)


def test_hours_to_angle_noon() -> None:
    assert hours_to_angle(12.0) == pytest.approx(90.0)


def test_render_svg_includes_band_arc() -> None:
    state = _stub_state(hours=22.0)
    svg = render_svg(state)
    # Confidence band is rendered as an <path d="M ... A ... ">.
    assert "<path " in svg
    assert " A " in svg  # SVG arc command


def test_render_svg_extreme_midnight() -> None:
    """Sanity at the boundary: clock at exactly 00:00."""
    state = _stub_state(hours=0.0)
    svg = render_svg(state)
    assert "<svg" in svg
    # Hand endpoint should be near the top of the face.
    # _CY=250, _INNER_R=180  ->  y ~ 70 at midnight.
    # The hand is the unique <line> with stroke-width="4"; attribute
    # order is not contractual so we match either ordering.
    hand_match = None
    for line_match in re.finditer(r"<line\b[^>]*>", svg):
        line = line_match.group(0)
        if 'stroke-width="4"' in line:
            hand_match = line
            break
    assert hand_match is not None, "no hand <line> element with stroke-width=4 found"
    y2_match = re.search(r'y2="([-\d.]+)"', hand_match)
    assert y2_match is not None
    y2 = float(y2_match.group(1))
    assert abs(y2 - 70.0) < 1.0, f"hand y2 at midnight should be ~70, got {y2}"

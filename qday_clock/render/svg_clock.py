"""Symbolic 24-hour Q-day Clock SVG renderer.

Server-rendered SVG; the symbolic clock page must work with JavaScript
disabled (per plan §E). All geometry deterministic.

24-hour face:

- Midnight (00:00) at top = Q-day.
- Noon (12:00) at bottom = "comfortably distant."
- Clock hand sweeps counter-clockwise as evidence accumulates,
  pointing closer to midnight.
- A shaded arc renders the confidence band.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from qday_clock.core.schemas import ClockState

# Display constants
_CX = 250.0
_CY = 250.0
_R = 200.0
_INNER_R = 180.0
_TICK_R = 195.0


@dataclass(frozen=True)
class ClockSVGConfig:
    """Cosmetics for the SVG. Color values are Okabe-Ito + grayscale
    so the palette is color-blind-safe (per plan §E accessibility)."""

    face_color: str = "#f7f7f7"
    rim_color: str = "#222222"
    tick_color: str = "#222222"
    hand_color: str = "#d55e00"  # Okabe-Ito vermillion
    band_color: str = "#d55e0033"  # 20% alpha
    text_color: str = "#111111"
    label_color: str = "#555555"


def hours_to_angle(hours: float) -> float:
    """Convert clock hours (0-24, midnight=0) to SVG angle.

    SVG angles measured clockwise from the positive x-axis (3 o'clock
    position). Midnight should be at the top (-90°). Each hour spans
    360 / 24 = 15°.

    hours = 0 (midnight)   →  -90°
    hours = 6              →    0°  (3 o'clock visually)
    hours = 12 (noon)      →   90°  (6 o'clock visually)
    hours = 18             →  180°
    """
    return -90.0 + hours * 15.0


def _polar(cx: float, cy: float, r: float, angle_deg: float) -> tuple[float, float]:
    theta = math.radians(angle_deg)
    return cx + r * math.cos(theta), cy + r * math.sin(theta)


def render_svg(
    state: ClockState,
    *,
    config: ClockSVGConfig | None = None,
    width: int = 500,
    height: int = 500,
) -> str:
    """Render the clock as an SVG string.

    Includes an aria-label with the verbal reading so screen readers
    convey the clock's content (WCAG 2.1 AA target).
    """
    config = config or ClockSVGConfig()
    hours = state.clock_hours
    angle = hours_to_angle(hours)
    hand_x, hand_y = _polar(_CX, _CY, _INNER_R, angle)

    band_low_angle = hours_to_angle(state.confidence_band_hours_low)
    band_high_angle = hours_to_angle(state.confidence_band_hours_high)
    band_arc = _arc_path(_CX, _CY, _INNER_R, band_low_angle, band_high_angle)

    ticks = _render_ticks(config)
    labels = _render_hour_labels(config)
    aria = _aria_reading(state)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{aria}">
  <title>Q-day Clock — {aria}</title>
  <circle cx="{_CX}" cy="{_CY}" r="{_R}" fill="{config.face_color}" stroke="{config.rim_color}" stroke-width="2"/>
  <path d="{band_arc}" fill="none" stroke="{config.band_color}" stroke-width="14" stroke-linecap="round"/>
  {ticks}
  {labels}
  <line x1="{_CX}" y1="{_CY}" x2="{hand_x:.2f}" y2="{hand_y:.2f}" stroke="{config.hand_color}" stroke-width="4" stroke-linecap="round"/>
  <circle cx="{_CX}" cy="{_CY}" r="6" fill="{config.hand_color}"/>
  <text x="{_CX}" y="{_CY + _R + 30}" text-anchor="middle" fill="{config.label_color}" font-family="-apple-system, system-ui, sans-serif" font-size="14">
    {aria}
  </text>
</svg>"""


def _render_ticks(config: ClockSVGConfig) -> str:
    parts: list[str] = []
    for h in range(24):
        angle = hours_to_angle(h)
        ox, oy = _polar(_CX, _CY, _R, angle)
        ix, iy = _polar(_CX, _CY, _TICK_R - (8 if h % 6 == 0 else 4), angle)
        w = 2 if h % 6 == 0 else 1
        parts.append(
            f'<line x1="{ox:.2f}" y1="{oy:.2f}" x2="{ix:.2f}" y2="{iy:.2f}" '
            f'stroke="{config.tick_color}" stroke-width="{w}"/>'
        )
    return "\n  ".join(parts)


def _render_hour_labels(config: ClockSVGConfig) -> str:
    parts: list[str] = []
    for label_h in (0, 6, 12, 18):
        angle = hours_to_angle(label_h)
        tx, ty = _polar(_CX, _CY, _TICK_R - 26, angle)
        text = {0: "00", 6: "06", 12: "12", 18: "18"}[label_h]
        parts.append(
            f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="middle" '
            f'dominant-baseline="middle" fill="{config.text_color}" '
            f'font-family="-apple-system, system-ui, sans-serif" '
            f'font-size="14" font-weight="bold">{text}</text>'
        )
    return "\n  ".join(parts)


def _arc_path(cx: float, cy: float, r: float, start_angle: float, end_angle: float) -> str:
    """Build an SVG path arc from start_angle to end_angle (degrees)."""
    sx, sy = _polar(cx, cy, r, start_angle)
    ex, ey = _polar(cx, cy, r, end_angle)
    delta = end_angle - start_angle
    large = 1 if delta > 180 else 0
    return f"M {sx:.2f} {sy:.2f} A {r} {r} 0 {large} 1 {ex:.2f} {ey:.2f}"


def _aria_reading(state: ClockState) -> str:
    h = state.clock_hours
    hours = int(h)
    minutes = int((h - hours) * 60)
    return (
        f"Reading: {hours:02d}:{minutes:02d} on a 24-hour Q-day clock "
        f"(midnight = Q-day). Confidence band {state.confidence_band_hours_low:.1f} – "
        f"{state.confidence_band_hours_high:.1f} hours."
    )

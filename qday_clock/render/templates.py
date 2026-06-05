"""Jinja2 template renderer for the static site.

Loads templates from ``site/`` and renders ``index.html``,
``methodology.html``, ``about.html``. Forbidden-language linting is
not performed here (that's a separate test step).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jinja2

from qday_clock.core.schemas import AxisId, ClockState, Signal
from qday_clock.render.svg_clock import render_svg


# Human-readable labels for the 5 axes. Kept here (next to the renderer)
# so the dashboard / sources templates stay declarative and the
# templates themselves don't pin axis-naming policy.
_AXIS_LABELS: dict[str, str] = {
    AxisId.LOGICAL_QUBITS.value: "Axis 1 — Logical qubit progress",
    AxisId.PHYSICAL_SCALING.value: "Axis 2 — Physical qubit scaling",
    AxisId.RESOURCE_ESTIMATE.value: "Axis 3 — Algorithmic / resource estimate",
    AxisId.ERROR_RATE.value: "Axis 4 — Error-rate floor",
    AxisId.PQC_MIGRATION.value: "Axis 5 — PQC migration (inverse)",
}

_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "site"


def _env(template_dir: Path) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=jinja2.select_autoescape(["html", "htm"]),
        undefined=jinja2.StrictUndefined,  # fail-fast: undefined vars = error
    )


def render_index(
    state: ClockState,
    template_dir: Path | None = None,
) -> str:
    """Render the symbolic-clock landing page."""
    template_dir = template_dir or _DEFAULT_TEMPLATE_DIR
    env = _env(template_dir)
    tmpl = env.get_template("index.tmpl.html")
    svg = render_svg(state)
    return tmpl.render(
        clock_svg=svg,
        state=state,
        hours=int(state.clock_hours),
        minutes=int((state.clock_hours - int(state.clock_hours)) * 60),
        verbal_reading=_verbal_reading(state),
    )


def render_methodology(
    methodology_md_text: str,
    template_dir: Path | None = None,
) -> str:
    """Render the methodology page from raw markdown text.

    Markdown is rendered into a <pre>-wrapped block by default to keep
    the MVP free of a markdown-to-HTML dependency. v0.2 can swap in
    a proper markdown renderer (e.g. ``mistune``).
    """
    template_dir = template_dir or _DEFAULT_TEMPLATE_DIR
    env = _env(template_dir)
    tmpl = env.get_template("methodology.tmpl.html")
    return tmpl.render(methodology_text=methodology_md_text)


def render_about(
    pubkey_b64: str,
    template_dir: Path | None = None,
) -> str:
    """Render the About page; the public key is embedded so readers
    can re-verify ``clock_state.json`` independently."""
    template_dir = template_dir or _DEFAULT_TEMPLATE_DIR
    env = _env(template_dir)
    tmpl = env.get_template("about.tmpl.html")
    return tmpl.render(pubkey_b64=pubkey_b64)


def render_dashboard(
    state: ClockState,
    template_dir: Path | None = None,
) -> str:
    """Render the 5-axis dashboard page.

    Per plan §E: per-axis reading + contributing-signal-ID drill-down +
    GRI baseline overlay + Mosca-inequality informational panel +
    gates-fired log. JS is optional; the page renders fully without
    it (drill-downs use ``<details>``).
    """
    template_dir = template_dir or _DEFAULT_TEMPLATE_DIR
    env = _env(template_dir)
    tmpl = env.get_template("dashboard.tmpl.html")

    # Per-axis row table — preserve AxisId enum order so the four
    # forward-contributing axes (1-4) show before the inverse axis (5).
    axis_rows: list[dict[str, Any]] = []
    for axis in AxisId:
        reading = state.axes.get(axis.value)
        if reading is None:
            continue
        weight_attr = {
            AxisId.LOGICAL_QUBITS.value: "logical_qubits",
            AxisId.PHYSICAL_SCALING.value: "physical_scaling",
            AxisId.RESOURCE_ESTIMATE.value: "resource_estimate",
            AxisId.ERROR_RATE.value: "error_rate",
            AxisId.PQC_MIGRATION.value: "pqc_subtraction",
        }[axis.value]
        axis_rows.append(
            {
                "label": _AXIS_LABELS[axis.value],
                "reading": reading,
                "weight": getattr(state.weights, weight_attr),
                "is_inverse": axis is AxisId.PQC_MIGRATION,
            }
        )

    return tmpl.render(
        state=state,
        axis_rows=axis_rows,
        hours=int(state.clock_hours),
        minutes=int((state.clock_hours - int(state.clock_hours)) * 60),
    )


def render_sources(
    state: ClockState,
    signals: list[Signal],
    template_dir: Path | None = None,
) -> str:
    """Render the per-signal provenance page.

    ``signals`` is the explicit list to render; callers pass in the
    same signal corpus that fed ``compute_clock_state``. We do not
    pull signals out of ``ClockState`` because the state only carries
    signal IDs (per the signed-artifact contract — keeping the state
    compact); the full signal records live in the ingest layer.
    """
    template_dir = template_dir or _DEFAULT_TEMPLATE_DIR
    env = _env(template_dir)
    tmpl = env.get_template("sources.tmpl.html")

    signal_rows: list[dict[str, Any]] = []
    # Deterministic order: (axis, -normalized_value, signal_id) so the
    # highest-impact signals per axis surface first.
    sorted_signals = sorted(
        signals,
        key=lambda s: (s.axis.value, -s.normalized_value, s.signal_id),
    )
    for sig in sorted_signals:
        signal_rows.append(
            {
                "signal_id": sig.signal_id,
                "axis_label": _AXIS_LABELS.get(sig.axis.value, sig.axis.value),
                "title": sig.title,
                "summary": sig.summary,
                "source": sig.source,
                "url": sig.url,
                "published_at": sig.published_at,
                "evidence_class": sig.evidence_class.value,
                "normalized_value": sig.normalized_value,
                "confidence": sig.confidence,
            }
        )

    return tmpl.render(state=state, signal_rows=signal_rows)


def _verbal_reading(state: ClockState) -> str:
    h = state.clock_hours
    hours = int(h)
    minutes = int((h - hours) * 60)
    return (
        f"As of {state.generated_at.strftime('%Y-%m-%d')}, public evidence reads "
        f"{hours:02d}:{minutes:02d} on a 24-hour Q-day clock, with the "
        f"GRI {state.gri_baseline_year} threat-timeline median anchored at "
        f"{state.gri_baseline_label.split('~')[-1].strip().rstrip('.')} and "
        f"NSA CNSA 2.0 mandatory at 2033."
    )

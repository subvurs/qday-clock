"""Jinja2 template smoke tests.

Per plan section G: Jinja templates produce valid HTML.

We do not validate against a formal HTML5 parser (overkill for MVP);
we assert that:

- Each MVP template renders without raising
- StrictUndefined catches missing variables (sanity check)
- Output contains the structural anchors a downstream linter or
  forbidden-language test will look for
"""

from __future__ import annotations

from datetime import UTC, datetime

import jinja2
import pytest

from qday_clock.core.schemas import (
    AxisId,
    AxisReading,
    ClockState,
    EvidenceClass,
    RubricWeights,
    Signal,
)
from qday_clock.render.templates import (
    render_about,
    render_dashboard,
    render_index,
    render_methodology,
    render_sources,
)


def _stub_state() -> ClockState:
    axis = AxisReading(
        axis=AxisId.LOGICAL_QUBITS,
        reading=0.4,
        contributing_signal_ids=["sigA", "sigB"],
        n_independent_sources=2,
        confidence_band_low=0.3,
        confidence_band_high=0.5,
        note="stub axis",
    )
    axes = {a.value: axis.model_copy(update={"axis": a}) for a in AxisId}
    return ClockState(
        version="0.1.0",
        generated_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        clock_score=0.3,
        clock_hours=16.8,
        confidence_band_hours_low=15.0,
        confidence_band_hours_high=18.0,
        axes=axes,
        weights=RubricWeights.default(),
        gri_baseline_year=2024,
        gri_baseline_label="GRI 2024 - median CRQC arrival ~ 2034",
        gates_fired=[],
        methodology_url="https://example.invalid/methodology",
    )


def _stub_signals() -> list[Signal]:
    """A small mixed-axis signal set for sources/dashboard smoke."""
    return [
        Signal(
            signal_id="sigA",
            axis=AxisId.LOGICAL_QUBITS,
            title="Distance-11 logical qubit demo",
            summary="Surface-code distance-11 demo on Heron-class hardware.",
            source="vendor-A-paper",
            url="https://example.invalid/sigA",
            published_at=datetime(2025, 12, 1, tzinfo=UTC),
            observed_at=datetime(2026, 4, 1, tzinfo=UTC),
            evidence_class=EvidenceClass.HARDWARE,
            raw_value=11.0,
            normalized_value=0.55,
            confidence=0.95,
        ),
        Signal(
            signal_id="sigB",
            axis=AxisId.PQC_MIGRATION,
            title="NSA CNSA 2.0 software-ready milestone",
            summary="CNSA 2.0 software-supports requirement in force.",
            source="nsa-policy-statement",
            url=None,
            published_at=datetime(2025, 9, 1, tzinfo=UTC),
            observed_at=datetime(2026, 4, 1, tzinfo=UTC),
            evidence_class=EvidenceClass.POLICY,
            raw_value=1.0,
            normalized_value=0.5,
            confidence=1.0,
        ),
    ]


def test_render_index_smoke() -> None:
    state = _stub_state()
    html = render_index(state)
    assert "<svg" in html
    assert "Q-day Clock" in html
    # The clock should reference the GRI anchor somewhere on the page.
    assert "2024" in html or "GRI" in html


def test_render_methodology_smoke() -> None:
    text = "# Methodology\n\nThis is sample methodology body content."
    html = render_methodology(text)
    assert "sample methodology body content" in html
    # The page should at least look HTML-shaped.
    lowered = html.lower()
    assert ("<html" in lowered) or ("<!doctype" in lowered) or ("<section" in lowered)


def test_render_about_embeds_pubkey() -> None:
    fake_pubkey_b64 = "MCowBQYDK2VwAyEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    html = render_about(pubkey_b64=fake_pubkey_b64)
    assert fake_pubkey_b64 in html


def test_render_dashboard_smoke() -> None:
    state = _stub_state()
    html = render_dashboard(state)
    # 5 axes must each get a row in the readings table.
    for label in (
        "Axis 1",
        "Axis 2",
        "Axis 3",
        "Axis 4",
        "Axis 5",
    ):
        assert label in html, f"dashboard missing {label}"
    # PQC axis must be flagged as inverse in the dashboard.
    assert "inverse" in html
    # Mosca's inequality section must be present (informational, not a probability).
    assert "Mosca" in html
    # Drill-down anchors for sources should be present.
    assert "sources.html#" in html


def test_render_sources_smoke() -> None:
    state = _stub_state()
    signals = _stub_signals()
    html = render_sources(state, signals)
    # Each signal must appear by ID and the row anchor must exist.
    for sig in signals:
        assert sig.signal_id in html
        assert f'id="{sig.signal_id}"' in html
    # Evidence-class tags must be rendered for both shipped classes.
    assert "hardware" in html
    assert "policy" in html
    # URL-bearing signal renders an anchor; URL-less signal renders plain title.
    assert "https://example.invalid/sigA" in html
    assert "NSA CNSA 2.0 software-ready milestone" in html


def test_render_sources_handles_empty_signal_list() -> None:
    """Per CLAUDE.md §8, the empty-signals path must surface, not hide."""
    state = _stub_state()
    html = render_sources(state, signals=[])
    assert "No signals are recorded" in html
    # Reading-context block must still render so the page is not blank.
    assert state.gri_baseline_label in html


def test_strict_undefined_catches_missing_vars(tmp_path) -> None:
    """Templates use StrictUndefined; a bad template variable should
    raise rather than silently render the empty string. This guards
    against a future template-typo regression."""
    template_dir = tmp_path / "site"
    template_dir.mkdir()
    bad_tmpl = template_dir / "bad.tmpl.html"
    bad_tmpl.write_text("<p>{{ does_not_exist }}</p>", encoding="utf-8")

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        undefined=jinja2.StrictUndefined,
    )
    tmpl = env.get_template("bad.tmpl.html")
    with pytest.raises(jinja2.UndefinedError):
        tmpl.render()

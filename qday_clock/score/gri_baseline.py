"""GRI Quantum Threat Timeline anchor.

For v0.1.0 MVP we hard-code the most recent GRI median year. v0.2 will
load this from ``data/gri_threat_timeline.csv`` directly so updates do
not require a code change.

Per METHODOLOGY.md §2, the GRI baseline is a *visible anchor*, not
ground truth. The clock may diverge from it; that divergence is itself
a signal and triggers a CHANGELOG entry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GRIBaseline:
    """Single GRI Threat Timeline anchor point."""

    survey_year: int
    median_crqc_year: int
    label: str
    source: str


def latest() -> GRIBaseline:
    """Return the most recent GRI baseline shipped with the repo.

    Per METHODOLOGY.md §2: the GRI Quantum Threat Timeline reports
    cryptographer-elicited intervals for CRQC arrival. We use the
    median 50% confidence year as the headline anchor.

    Note: this is the *survey* year (when the elicitation happened),
    not when the CRQC is expected. The ``median_crqc_year`` is the
    expert-aggregated estimate of when a CRQC is more likely than
    not to exist.
    """
    return GRIBaseline(
        survey_year=2024,
        median_crqc_year=2034,
        label="GRI 2024 — median CRQC arrival ~ 2034",
        source="Global Risk Institute, Quantum Threat Timeline 2024",
    )


def baseline_axis_floor(baseline: GRIBaseline) -> float:
    """Translate a GRI baseline into a reasonable axis-fallback value.

    Used at MVP when only Axis 1 has live signals; the remaining axes
    fall back to a GRI-anchored floor so the clock does not read
    ``0.0`` simply because we haven't wired the extractor yet.

    Mapping is simple: linearly interpolate between
    median_crqc_year=2050 (0.10) and median_crqc_year=2025 (0.85).
    """
    y = baseline.median_crqc_year
    # Clamp
    if y >= 2050:
        return 0.10
    if y <= 2025:
        return 0.85
    # Linear: 2025 -> 0.85, 2050 -> 0.10 (slope -0.03/year)
    return 0.85 - (y - 2025) * 0.03

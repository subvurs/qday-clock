"""Per-axis reading aggregation.

Given a list of :class:`Signal` objects already labelled by axis, produce
one :class:`AxisReading` per axis. This is where per-signal pre-multipliers
(stale-signal decay, roadmap weight cap), per-source caps
(:class:`SingleSourceCapGate`), and per-signal contrast-saturation caps
are applied.

Composition is symmetric: every multiplier is applied to both the
numerator and the denominator of the confidence-weighted mean, so gates
re-weight contributions relative to each other rather than absolutely
dragging the axis down. A signal whose every multiplier is 1.0 produces
the same aggregate as if no gates ran.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable

from qday_clock.core.schemas import AxisId, AxisReading, Signal
from qday_clock.score.gates import (
    ContrastSaturationGate,
    GateVerdict,
    RoadmapWeightCapGate,
    SingleSourceCapGate,
    StaleSignalGate,
)


def aggregate_axis(
    axis: AxisId,
    signals: Iterable[Signal],
    source_cap_gate: SingleSourceCapGate | None = None,
    *,
    stale_gate: StaleSignalGate | None = None,
    roadmap_cap_gate: RoadmapWeightCapGate | None = None,
    contrast_saturation_gate: ContrastSaturationGate | None = None,
    now: datetime | None = None,
) -> tuple[AxisReading, list[GateVerdict]]:
    """Compute :class:`AxisReading` from the signals for one axis.

    Returns the reading together with any gate verdicts emitted while
    aggregating. Gate verdicts that fire are recorded so the caller can
    log them; non-firing verdicts are dropped at the caller's discretion.

    Pipeline (each step preserves the symmetric numerator/denominator
    invariant — multiplier=1.0 is a true no-op):

      1. Per-signal pre-multipliers
         (``stale_gate`` × ``roadmap_cap_gate``). ``stale_gate`` only
         runs when ``now`` is supplied; without ``now`` it is skipped
         entirely (forever-deterministic for the golden replay).
      2. Per-source share is computed using the pre-multipliers, then
         ``source_cap_gate`` produces a per-source multiplier.
      3. Per-signal share (after steps 1 & 2) is fed to
         ``contrast_saturation_gate`` for a final per-signal multiplier.
      4. Final aggregation stacks all three multipliers symmetrically.
    """
    sigs = [s for s in signals if s.axis == axis]
    verdicts: list[GateVerdict] = []

    if not sigs:
        return (
            AxisReading(
                axis=axis,
                reading=0.0,
                contributing_signal_ids=[],
                n_independent_sources=0,
                confidence_band_low=0.0,
                confidence_band_high=1.0,
                note="no signals available — wide confidence band",
            ),
            verdicts,
        )

    # Step 1: per-signal pre-multipliers (stale × roadmap-cap).
    per_signal_pre: dict[str, float] = {s.signal_id: 1.0 for s in sigs}
    for s in sigs:
        m = 1.0
        if stale_gate is not None and now is not None:
            v = stale_gate.check(s, now=now)
            if v.fired:
                verdicts.append(v)
            m *= v.multiplier
        if roadmap_cap_gate is not None:
            v = roadmap_cap_gate.check(s)
            if v.fired:
                verdicts.append(v)
            m *= v.multiplier
        per_signal_pre[s.signal_id] = m

    # Step 2: per-source share computed using per-signal pre-multipliers.
    raw_per_source: dict[str, float] = defaultdict(float)
    total_weight = 0.0
    for s in sigs:
        m_pre = per_signal_pre[s.signal_id]
        w = s.confidence * m_pre
        raw_per_source[s.source] += w * s.normalized_value
        total_weight += w
    if total_weight <= 0:
        return (
            AxisReading(
                axis=axis,
                reading=0.0,
                contributing_signal_ids=[s.signal_id for s in sigs],
                n_independent_sources=len({s.source for s in sigs}),
                confidence_band_low=0.0,
                confidence_band_high=1.0,
                note="zero total confidence — fail conservative",
            ),
            verdicts,
        )

    # Compute pre-cap source share and ask SingleSourceCapGate.
    source_shares = {
        src: contrib / total_weight for src, contrib in raw_per_source.items()
    }
    source_multipliers: dict[str, float] = {src: 1.0 for src in source_shares}
    if source_cap_gate is not None:
        for src, share in source_shares.items():
            verdict = source_cap_gate.check(src, share)
            if verdict.fired:
                verdicts.append(verdict)
                source_multipliers[src] = verdict.multiplier

    # Step 3: per-signal share *after* steps 1 & 2 → contrast-saturation.
    # We compute each signal's normalized contribution to the axis after
    # the pre-multiplier and source-cap have been applied, then ask
    # ContrastSaturationGate whether any one signal dominates.
    per_signal_contrib: dict[str, float] = {}
    contrib_total = 0.0
    for s in sigs:
        c = (
            s.confidence
            * per_signal_pre[s.signal_id]
            * source_multipliers[s.source]
            * s.normalized_value
        )
        per_signal_contrib[s.signal_id] = c
        contrib_total += c

    contrast_multipliers: dict[str, float] = {s.signal_id: 1.0 for s in sigs}
    if contrast_saturation_gate is not None and contrib_total > 0:
        for s in sigs:
            share = per_signal_contrib[s.signal_id] / contrib_total
            verdict = contrast_saturation_gate.check(s.signal_id, share)
            if verdict.fired:
                verdicts.append(verdict)
                contrast_multipliers[s.signal_id] = verdict.multiplier

    # Step 4: final aggregation with all three multipliers stacked
    # symmetrically (numerator and denominator).
    capped_total = 0.0
    capped_weight = 0.0
    for s in sigs:
        m = (
            per_signal_pre[s.signal_id]
            * source_multipliers[s.source]
            * contrast_multipliers[s.signal_id]
        )
        capped_total += s.confidence * s.normalized_value * m
        capped_weight += s.confidence * m
    if capped_weight <= 0:
        reading = 0.0
    else:
        reading = capped_total / capped_weight
    reading = max(0.0, min(1.0, reading))

    # Confidence band: min/max of contributing normalized values,
    # widened by 0.05 when fewer than 3 independent sources.
    values = [s.normalized_value for s in sigs]
    low = min(values)
    high = max(values)
    n_sources = len({s.source for s in sigs})
    if n_sources < 3:
        widen = 0.05 * (3 - n_sources)
        low = max(0.0, low - widen)
        high = min(1.0, high + widen)

    return (
        AxisReading(
            axis=axis,
            reading=reading,
            contributing_signal_ids=[s.signal_id for s in sigs],
            n_independent_sources=n_sources,
            confidence_band_low=low,
            confidence_band_high=high,
            note=None,
        ),
        verdicts,
    )

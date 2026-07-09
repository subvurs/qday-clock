"""Top-level clock combination.

Given per-axis readings + GRI baseline fallback, compute the final
:class:`ClockState`. This is the only place that combines axes into
a single number; everything else is per-axis.

v0.2 wires the five new Goodhart gates (StaleSignalGate,
RoadmapWeightCapGate, ContrastSaturationGate per-signal/per-axis;
MultiSourceConfirmationGate + AntiStiffnessGate as step-change
observers when ``previous_axes_readings`` is supplied). Every gate is
defaulted to its METHODOLOGY.md §5 parameters; callers can pass
``apply_gates=False`` for replay against a strictly-pre-gate
``clock_state.json``.
"""

from __future__ import annotations

from datetime import datetime

from qday_clock.core.schemas import (
    AxisId,
    AxisReading,
    ClockState,
    RubricWeights,
    Signal,
)
from qday_clock.core.time import utcnow
from qday_clock.score.axes import aggregate_axis
from qday_clock.score.gates import (
    AntiStiffnessGate,
    ContrastSaturationGate,
    GateVerdict,
    MultiSourceConfirmationGate,
    RoadmapWeightCapGate,
    SingleSourceCapGate,
    StaleSignalGate,
)
from qday_clock.score.gri_baseline import (
    GRIBaseline,
    baseline_axis_floor,
)
from qday_clock.score.gri_baseline import (
    latest as latest_gri,
)

METHODOLOGY_URL = "https://icqubit.com/methodology.html"


def compute_clock_state(
    signals: list[Signal],
    weights: RubricWeights | None = None,
    gri: GRIBaseline | None = None,
    *,
    schema_version: str = "0.1.0",
    methodology_url: str = METHODOLOGY_URL,
    apply_gates: bool = True,
    threshold_lock_thresholds: dict[str, float] | None = None,
    threshold_guard=None,  # ThresholdGuard | None
    now: datetime | None = None,
    previous_axes_readings: dict[str, float] | None = None,
) -> ClockState:
    """Aggregate ``signals`` into a fully-formed :class:`ClockState`.

    For axes with no live signals (v0.1.0: axes 2, 3, 4, 5), the
    GRI baseline floor is used as a stand-in so the clock does not
    read ``0.0`` simply because the extractor for that axis is not
    wired yet. This fallback is documented in METHODOLOGY.md and
    flagged in the per-axis ``note`` field.

    Parameters
    ----------
    now : datetime | None
        Reference clock-time for time-dependent gates
        (StaleSignalGate, MultiSourceConfirmationGate). If ``None``,
        the stale-signal gate is skipped entirely (forever-deterministic
        replay) and the multi-source gate is given ``utcnow()``. Tests
        and the golden replay should pass an explicit ``now`` so they
        remain byte-identical across calendar time.
    previous_axes_readings : dict[str, float] | None
        Mapping ``axis_value -> previous_reading`` from the most recent
        signed ``clock_state.json``. When supplied, step-change gates
        (MultiSourceConfirmationGate, AntiStiffnessGate) are run as
        observers — they record their verdicts but do not retroactively
        edit the new axis readings. This matches the gh_eval pattern:
        gates that record fire-events feed downstream review rather
        than silently mutate scores.
    """
    weights = weights or RubricWeights.default()
    gri = gri or latest_gri()

    # Instantiate the gate set. Each gate uses its METHODOLOGY.md §5
    # default. `apply_gates=False` is the only way to obtain a
    # strictly-pre-gate reading (used by the v0.1 golden replay path).
    source_cap = SingleSourceCapGate() if apply_gates else None
    stale_gate = StaleSignalGate() if apply_gates else None
    roadmap_cap = RoadmapWeightCapGate() if apply_gates else None
    contrast_gate = ContrastSaturationGate() if apply_gates else None
    multi_source = MultiSourceConfirmationGate() if apply_gates else None
    anti_stiffness = AntiStiffnessGate() if apply_gates else None

    axis_readings: dict[str, AxisReading] = {}
    all_verdicts: list[GateVerdict] = []

    floor = baseline_axis_floor(gri)
    for axis in AxisId:
        reading, verdicts = aggregate_axis(
            axis,
            signals,
            source_cap_gate=source_cap,
            stale_gate=stale_gate,
            roadmap_cap_gate=roadmap_cap,
            contrast_saturation_gate=contrast_gate,
            now=now,
        )
        if not reading.contributing_signal_ids:
            # Cold-start fallback — see METHODOLOGY.md §3 cold-start clause.
            # The GRI floor is threat-NEUTRAL on the four additive axes
            # (1-4), but axis 5 (PQC migration) is SUBTRACTED in the final
            # combination. Applying the same positive floor there assumes
            # unevidenced defensive deployment and backs the clock off. The
            # threat-conservative default for "no evidence of PQC migration"
            # is 0.0 (assume none deployed), so the clock is not credited for
            # readiness we cannot observe.
            if axis is AxisId.PQC_MIGRATION:
                axis_floor = 0.0
                cold_note = (
                    "axis cold-start — inverse axis, no PQC-migration "
                    "evidence (0.0, threat-conservative)"
                )
            else:
                axis_floor = floor
                cold_note = f"axis cold-start — GRI {gri.survey_year} baseline floor"
            reading = AxisReading(
                axis=axis,
                reading=axis_floor,
                contributing_signal_ids=[],
                n_independent_sources=0,
                confidence_band_low=max(0.0, axis_floor - 0.15),
                confidence_band_high=min(1.0, axis_floor + 0.15),
                note=cold_note,
            )
        axis_readings[axis.value] = reading
        all_verdicts.extend(verdicts)

    # Step-change observers: run only when a previous reading is supplied
    # and gates are active. These do not retroactively edit axis values;
    # they record verdicts so a human reviewer can see whether the step
    # was confirmed and within stiffness limits before the new state is
    # promoted to ``site/data/clock_state.json``.
    if (
        apply_gates
        and previous_axes_readings is not None
        and multi_source is not None
        and anti_stiffness is not None
    ):
        check_now = now if now is not None else utcnow()
        for axis in AxisId:
            axis_key = axis.value
            if axis_key not in previous_axes_readings:
                continue
            current = axis_readings[axis_key].reading
            prev = previous_axes_readings[axis_key]
            contributing = [s for s in signals if s.axis == axis]
            ms_verdict = multi_source.check(
                axis=axis_key,
                previous_reading=prev,
                proposed_reading=current,
                contributing_signals=contributing,
                now=check_now,
            )
            if ms_verdict.fired:
                all_verdicts.append(ms_verdict)
            as_verdict = anti_stiffness.check(
                axis=axis_key,
                previous_reading=prev,
                proposed_reading=current,
            )
            if as_verdict.fired:
                all_verdicts.append(as_verdict)

    # Threshold guard runs *after* aggregation; its verdict is recorded
    # but does not modify the clock value. The CI step that asserts
    # locked thresholds is the actual enforcement point.
    if apply_gates and threshold_guard is not None and threshold_lock_thresholds is not None:
        all_verdicts.append(threshold_guard.check(threshold_lock_thresholds))

    # Combine axes 1-4 with weights; axis 5 subtracts.
    a1 = axis_readings[AxisId.LOGICAL_QUBITS.value].reading
    a2 = axis_readings[AxisId.PHYSICAL_SCALING.value].reading
    a3 = axis_readings[AxisId.RESOURCE_ESTIMATE.value].reading
    a4 = axis_readings[AxisId.ERROR_RATE.value].reading
    a5 = axis_readings[AxisId.PQC_MIGRATION.value].reading

    raw_score = (
        weights.logical_qubits * a1
        + weights.physical_scaling * a2
        + weights.resource_estimate * a3
        + weights.error_rate * a4
    )
    clock_score = raw_score - weights.pqc_subtraction * a5
    clock_score = max(0.0, min(1.0, clock_score))

    clock_hours = 24.0 * (1.0 - clock_score)

    # Confidence band on the clock face, mirroring the axes' bands.
    a1 = axis_readings[AxisId.LOGICAL_QUBITS.value]
    a2 = axis_readings[AxisId.PHYSICAL_SCALING.value]
    a3 = axis_readings[AxisId.RESOURCE_ESTIMATE.value]
    a4 = axis_readings[AxisId.ERROR_RATE.value]
    a5_band = axis_readings[AxisId.PQC_MIGRATION.value]

    low_score = (
        weights.logical_qubits * a1.confidence_band_low
        + weights.physical_scaling * a2.confidence_band_low
        + weights.resource_estimate * a3.confidence_band_low
        + weights.error_rate * a4.confidence_band_low
    ) - weights.pqc_subtraction * a5_band.confidence_band_high

    high_score = (
        weights.logical_qubits * a1.confidence_band_high
        + weights.physical_scaling * a2.confidence_band_high
        + weights.resource_estimate * a3.confidence_band_high
        + weights.error_rate * a4.confidence_band_high
    ) - weights.pqc_subtraction * a5_band.confidence_band_low

    low_score = max(0.0, min(1.0, low_score))
    high_score = max(0.0, min(1.0, high_score))
    band_high_hours = 24.0 * (1.0 - low_score)  # lower score → later clock
    band_low_hours = 24.0 * (1.0 - high_score)  # higher score → earlier clock
    # Ensure ordering
    if band_low_hours > band_high_hours:
        band_low_hours, band_high_hours = band_high_hours, band_low_hours

    return ClockState(
        version=schema_version,
        generated_at=utcnow(),
        clock_score=clock_score,
        clock_hours=clock_hours,
        confidence_band_hours_low=band_low_hours,
        confidence_band_hours_high=band_high_hours,
        axes=axis_readings,
        weights=weights,
        gri_baseline_year=gri.survey_year,
        gri_baseline_label=gri.label,
        gates_fired=[v.to_dict() for v in all_verdicts if v.fired],
        methodology_url=methodology_url,
    )

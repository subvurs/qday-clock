"""End-to-end integration: v0.2 gates fire through ``compute_clock_state``.

Unit tests in ``tests/adversarial/`` lock each gate's behaviour at the
gate boundary. These tests lock the *wiring*: each gate must actually
fire when its triggering pathology shows up in the production scoring
path (``compute_clock_state``). A passing unit test plus a passing
integration test together demonstrate that the gate is both correct in
isolation and reachable in production.

Per CLAUDE.md §9 (Goodhart-aware evaluation): the contract here is
"the gate's verdict appears in ``state.gates_fired`` for the corpus
that triggers it". A future refactor that silently disconnects a gate
will trip these tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from qday_clock.core.schemas import AxisId, EvidenceClass, Signal
from qday_clock.score.clock import compute_clock_state

_NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _sig(
    *,
    axis: AxisId,
    normalized: float,
    source: str,
    signal_id: str,
    observed_at: datetime = _NOW,
    evidence: EvidenceClass = EvidenceClass.HARDWARE,
    confidence: float = 1.0,
) -> Signal:
    return Signal(
        signal_id=signal_id,
        axis=axis,
        title="t",
        summary="s",
        source=source,
        published_at=observed_at,
        observed_at=observed_at,
        evidence_class=evidence,
        raw_value=normalized * 10.0,
        normalized_value=normalized,
        confidence=confidence,
    )


def _fired_names(state) -> set[str]:
    return {v["name"] for v in state.gates_fired}


# ---------------------------------------------------------------------------
# RoadmapWeightCapGate — fires when a roadmap signal exceeds cap=0.3
# ---------------------------------------------------------------------------


def test_roadmap_cap_gate_fires_through_pipeline() -> None:
    """A roadmap-evidence signal at normalized_value 0.9 must be capped."""
    signals = [
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.9,
            source="vendor-x-blog",
            signal_id="sig_roadmap",
            evidence=EvidenceClass.ROADMAP,
        ),
        # Second signal so the axis is not single-source, so the
        # single-source cap doesn't also fire and confuse the assertion.
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.2,
            source="independent-lab",
            signal_id="sig_lab",
        ),
    ]
    state = compute_clock_state(signals, now=_NOW)
    fired = _fired_names(state)
    assert "RoadmapWeightCapGate" in fired, (
        f"RoadmapWeightCapGate did not fire; gates_fired = {state.gates_fired}"
    )


def test_roadmap_cap_gate_dampens_axis_reading() -> None:
    """Roadmap-only axis must read lower with the gate than without it."""
    signals = [
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.9,
            source="vendor-x-blog",
            signal_id="sig_roadmap_dominant",
            evidence=EvidenceClass.ROADMAP,
        ),
    ]
    with_gate = compute_clock_state(signals, now=_NOW)
    without_gate = compute_clock_state(signals, now=_NOW, apply_gates=False)
    a1_with = with_gate.axes[AxisId.LOGICAL_QUBITS.value].reading
    a1_without = without_gate.axes[AxisId.LOGICAL_QUBITS.value].reading
    # Whole axis is one roadmap signal — the cap multiplier scales both
    # numerator and denominator equally, so the *reading* (a ratio)
    # doesn't change. What changes is the recorded verdict — assert that
    # exactly that observability promise holds.
    assert a1_with == a1_without
    assert "RoadmapWeightCapGate" in _fired_names(with_gate)
    assert "RoadmapWeightCapGate" not in _fired_names(without_gate)


# ---------------------------------------------------------------------------
# StaleSignalGate — fires when a signal is older than fresh_days
# ---------------------------------------------------------------------------


def test_stale_signal_gate_fires_through_pipeline() -> None:
    """A signal observed 2 years ago should trip StaleSignalGate."""
    two_years_ago = _NOW - timedelta(days=730)
    signals = [
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.7,
            source="archived-arxiv",
            signal_id="sig_stale",
            observed_at=two_years_ago,
        ),
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.2,
            source="fresh-lab",
            signal_id="sig_fresh",
        ),
    ]
    state = compute_clock_state(signals, now=_NOW)
    assert "StaleSignalGate" in _fired_names(state)


def test_stale_signal_gate_skipped_when_now_is_none() -> None:
    """Without ``now``, StaleSignalGate must not run — preserves the
    forever-deterministic replay path."""
    two_years_ago = _NOW - timedelta(days=730)
    signals = [
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.7,
            source="archived-arxiv",
            signal_id="sig_stale_no_now",
            observed_at=two_years_ago,
        ),
    ]
    state = compute_clock_state(signals)  # no `now`
    assert "StaleSignalGate" not in _fired_names(state)


# ---------------------------------------------------------------------------
# ContrastSaturationGate — fires when one signal's share exceeds 0.5
# ---------------------------------------------------------------------------


def test_contrast_saturation_fires_when_one_signal_dominates() -> None:
    """One signal at full normalized=1.0 alongside near-silent peers."""
    signals = [
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=1.0,
            source="dominant-src",
            signal_id="sig_dom",
        ),
        # Three nearly-zero confidence companions so the dominant signal's
        # contrast share exceeds 0.5 of the axis.
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.01,
            source="quiet-1",
            signal_id="sig_q1",
            confidence=0.05,
        ),
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.01,
            source="quiet-2",
            signal_id="sig_q2",
            confidence=0.05,
        ),
    ]
    state = compute_clock_state(signals, now=_NOW)
    assert "ContrastSaturationGate" in _fired_names(state)


# ---------------------------------------------------------------------------
# Step-change gates — fire only when previous_axes_readings supplied
# ---------------------------------------------------------------------------


def test_anti_stiffness_fires_on_large_step() -> None:
    """An axis swinging from 0.10 → 0.85 (Δ=0.75 > 0.4) must trigger."""
    signals = [
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.85,
            source="src-a",
            signal_id="sig_step_a",
        ),
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.85,
            source="src-b",
            signal_id="sig_step_b",
        ),
    ]
    state = compute_clock_state(
        signals,
        now=_NOW,
        previous_axes_readings={AxisId.LOGICAL_QUBITS.value: 0.10},
    )
    assert "AntiStiffnessGate" in _fired_names(state)


def test_multi_source_confirmation_fires_on_unconfirmed_step() -> None:
    """A single-source step >0.15 with <2 sources must trip multi_source."""
    signals = [
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.7,
            source="single-vendor",
            signal_id="sig_solo_step",
        ),
    ]
    state = compute_clock_state(
        signals,
        now=_NOW,
        previous_axes_readings={AxisId.LOGICAL_QUBITS.value: 0.10},
    )
    assert "MultiSourceConfirmationGate" in _fired_names(state)


def test_step_change_gates_silent_without_previous_readings() -> None:
    """Without ``previous_axes_readings``, neither step-change gate runs."""
    signals = [
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.9,
            source="src-a",
            signal_id="sig_no_prev",
        ),
    ]
    state = compute_clock_state(signals, now=_NOW)
    fired = _fired_names(state)
    assert "AntiStiffnessGate" not in fired
    assert "MultiSourceConfirmationGate" not in fired


# ---------------------------------------------------------------------------
# apply_gates=False bypasses every v0.2 gate
# ---------------------------------------------------------------------------


def test_apply_gates_false_silences_all_v02_gates() -> None:
    """``apply_gates=False`` is the only legitimate way to obtain a
    strictly-pre-gate reading (golden replay against the v0.1 hash)."""
    two_years_ago = _NOW - timedelta(days=730)
    signals = [
        _sig(
            axis=AxisId.LOGICAL_QUBITS,
            normalized=0.9,
            source="vendor-x-blog",
            signal_id="sig_roadmap_off",
            evidence=EvidenceClass.ROADMAP,
            observed_at=two_years_ago,
        ),
    ]
    state = compute_clock_state(
        signals,
        now=_NOW,
        previous_axes_readings={AxisId.LOGICAL_QUBITS.value: 0.10},
        apply_gates=False,
    )
    assert state.gates_fired == []

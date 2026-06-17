"""Adversarial fixture — RoadmapWeightCapGate.

Attack scenario: a vendor publishes a five-year roadmap announcing a
million-qubit machine "by 2033". Without a cap, that press-release
artifact would be treated as equivalent to a peer-reviewed hardware
demonstration and could push an axis reading toward 1.0 on slide-deck
evidence alone.

Expectation: RoadmapWeightCapGate caps any signal with
``evidence_class == ROADMAP`` to a normalized contribution of at most
``cap`` (default 0.3). Hardware, theory, simulation, policy, and
survey signals pass through unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime

from qday_clock.core.schemas import AxisId, EvidenceClass, Signal
from qday_clock.score.gates import RoadmapWeightCapGate

_NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _signal(
    *,
    evidence_class: EvidenceClass,
    normalized_value: float,
    signal_id: str = "sig_x",
) -> Signal:
    return Signal(
        signal_id=signal_id,
        axis=AxisId.PHYSICAL_SCALING,
        title="Vendor announces multi-year qubit roadmap",
        summary="Plan to ship 1M qubits by 2033",
        source="Vendor X PR",
        url=None,
        published_at=_NOW,
        observed_at=_NOW,
        evidence_class=evidence_class,
        raw_value=1_000_000.0,
        normalized_value=normalized_value,
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# Roadmap signal above cap → fires
# ---------------------------------------------------------------------------


def test_roadmap_signal_above_cap_triggers_gate() -> None:
    gate = RoadmapWeightCapGate(cap=0.3)
    sig = _signal(evidence_class=EvidenceClass.ROADMAP, normalized_value=0.9)
    verdict = gate.check(sig)
    assert verdict.fired is True
    # multiplier == cap / normalized = 0.3 / 0.9
    assert abs(verdict.multiplier - (0.3 / 0.9)) < 1e-9
    # Post-cap contribution exactly at cap.
    assert abs((0.9 * verdict.multiplier) - 0.3) < 1e-9


# ---------------------------------------------------------------------------
# Roadmap signal under cap → no-op
# ---------------------------------------------------------------------------


def test_roadmap_signal_under_cap_does_not_fire() -> None:
    gate = RoadmapWeightCapGate(cap=0.3)
    sig = _signal(evidence_class=EvidenceClass.ROADMAP, normalized_value=0.2)
    verdict = gate.check(sig)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


# ---------------------------------------------------------------------------
# Hardware signal above cap is NOT capped (asymmetry preserved)
# ---------------------------------------------------------------------------


def test_hardware_signal_passes_through_uncapped() -> None:
    """A measured hardware demo of equivalent magnitude must NOT be
    capped — the whole point of the gate is the evidence-class
    asymmetry (CLAUDE.md §3)."""
    gate = RoadmapWeightCapGate(cap=0.3)
    sig = _signal(evidence_class=EvidenceClass.HARDWARE, normalized_value=0.9)
    verdict = gate.check(sig)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


# ---------------------------------------------------------------------------
# Coverage of every non-roadmap evidence class
# ---------------------------------------------------------------------------


def test_no_other_evidence_class_is_capped() -> None:
    gate = RoadmapWeightCapGate(cap=0.3)
    for ec in [
        EvidenceClass.THEORY,
        EvidenceClass.SIMULATION,
        EvidenceClass.HARDWARE,
        EvidenceClass.POLICY,
        EvidenceClass.SURVEY,
    ]:
        sig = _signal(evidence_class=ec, normalized_value=0.95)
        verdict = gate.check(sig)
        assert verdict.fired is False, f"gate fired on {ec.value}"
        assert verdict.multiplier == 1.0


# ---------------------------------------------------------------------------
# Roadmap signal exactly at cap → no-op (boundary check)
# ---------------------------------------------------------------------------


def test_roadmap_signal_exactly_at_cap_does_not_fire() -> None:
    gate = RoadmapWeightCapGate(cap=0.3)
    sig = _signal(evidence_class=EvidenceClass.ROADMAP, normalized_value=0.3)
    verdict = gate.check(sig)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0

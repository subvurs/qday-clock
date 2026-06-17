"""Adversarial fixture — StaleSignalGate.

Attack scenario: a vendor's three-year-old "we will have a million-qubit
machine" announcement remains visible in the corpus indefinitely.
Without aging, that stale claim would hold the same weight in 2029 that
it had in 2026 — letting unverified promises permanently inflate the
clock reading.

Expectation: StaleSignalGate retains full weight up to ``fresh_days``
(~18 months), linearly decays to zero between ``fresh_days`` and
``stale_days`` (~36 months), and contributes nothing beyond
``stale_days``. The decay is symmetric: this is an aging policy, not
an evidence-class judgment, so it applies to every signal class
equally.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from qday_clock.core.schemas import AxisId, EvidenceClass, Signal
from qday_clock.score.gates import StaleSignalGate

_NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _signal(
    *,
    days_ago: int,
    signal_id: str = "sig_x",
    evidence_class: EvidenceClass = EvidenceClass.HARDWARE,
) -> Signal:
    observed = _NOW - timedelta(days=days_ago)
    return Signal(
        signal_id=signal_id,
        axis=AxisId.LOGICAL_QUBITS,
        title="vendor roadmap claim",
        summary="",
        source="Vendor X",
        url=None,
        published_at=observed,
        observed_at=observed,
        evidence_class=evidence_class,
        raw_value=1.0,
        normalized_value=0.5,
        confidence=0.8,
    )


# ---------------------------------------------------------------------------
# Fresh signal — full weight
# ---------------------------------------------------------------------------


def test_fresh_signal_passes_through_unchanged() -> None:
    gate = StaleSignalGate()  # 18-month / 36-month defaults
    sig = _signal(days_ago=30)  # 1 month old
    verdict = gate.check(sig, now=_NOW)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


def test_signal_exactly_at_fresh_boundary_still_full_weight() -> None:
    """Boundary: age == fresh_days → still full weight (≤, not <)."""
    gate = StaleSignalGate()
    sig = _signal(days_ago=gate.fresh_days)
    verdict = gate.check(sig, now=_NOW)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


# ---------------------------------------------------------------------------
# Mid-decay — linear interpolation
# ---------------------------------------------------------------------------


def test_signal_in_decay_window_gets_linear_multiplier() -> None:
    """At halfway through the decay window the multiplier is 0.5."""
    gate = StaleSignalGate()
    midpoint = (gate.fresh_days + gate.stale_days) // 2
    sig = _signal(days_ago=midpoint)
    verdict = gate.check(sig, now=_NOW)
    assert verdict.fired is True
    assert abs(verdict.multiplier - 0.5) < 1e-6


def test_signal_one_quarter_into_decay_gets_three_quarter_multiplier() -> None:
    gate = StaleSignalGate()
    span = gate.stale_days - gate.fresh_days
    age = gate.fresh_days + span // 4
    sig = _signal(days_ago=age)
    verdict = gate.check(sig, now=_NOW)
    assert verdict.fired is True
    # 1 - 0.25 = 0.75
    assert abs(verdict.multiplier - 0.75) < 1e-6


# ---------------------------------------------------------------------------
# Stale floor — zero contribution
# ---------------------------------------------------------------------------


def test_signal_exactly_at_stale_boundary_floors_to_zero() -> None:
    gate = StaleSignalGate()
    sig = _signal(days_ago=gate.stale_days)
    verdict = gate.check(sig, now=_NOW)
    assert verdict.fired is True
    assert verdict.multiplier == 0.0


def test_signal_well_beyond_stale_floors_to_zero() -> None:
    gate = StaleSignalGate()
    sig = _signal(days_ago=gate.stale_days * 2)
    verdict = gate.check(sig, now=_NOW)
    assert verdict.fired is True
    assert verdict.multiplier == 0.0


# ---------------------------------------------------------------------------
# Evidence-class agnosticism — aging is symmetric (CLAUDE.md §1)
# ---------------------------------------------------------------------------


def test_aging_applies_equally_to_every_evidence_class() -> None:
    """A 3-year-old hardware demo decays the same way a 3-year-old
    roadmap does. The gate is not an evidence-class judgment — it is
    purely a freshness policy. Distinct class-level treatment is the
    RoadmapWeightCapGate's job (CLAUDE.md §3)."""
    gate = StaleSignalGate()
    age = gate.stale_days  # fully stale
    for ec in [
        EvidenceClass.THEORY,
        EvidenceClass.SIMULATION,
        EvidenceClass.HARDWARE,
        EvidenceClass.ROADMAP,
        EvidenceClass.POLICY,
        EvidenceClass.SURVEY,
    ]:
        sig = _signal(days_ago=age, evidence_class=ec)
        verdict = gate.check(sig, now=_NOW)
        assert verdict.fired is True, f"gate silent on stale {ec.value}"
        assert verdict.multiplier == 0.0


# ---------------------------------------------------------------------------
# Custom-window configuration
# ---------------------------------------------------------------------------


def test_custom_decay_window_respected() -> None:
    """Operators can shorten the freshness window for fast-moving axes."""
    gate = StaleSignalGate(fresh_days=90, stale_days=180)
    # 135 days = midpoint of [90, 180]
    sig = _signal(days_ago=135)
    verdict = gate.check(sig, now=_NOW)
    assert verdict.fired is True
    assert abs(verdict.multiplier - 0.5) < 1e-6


def test_misconfigured_window_collapses_to_zero_beyond_fresh() -> None:
    """If stale_days ≤ fresh_days, the decay span is degenerate; the
    gate fails closed (zero contribution) rather than dividing by
    zero."""
    gate = StaleSignalGate(fresh_days=100, stale_days=100)
    sig = _signal(days_ago=200)
    verdict = gate.check(sig, now=_NOW)
    assert verdict.fired is True
    assert verdict.multiplier == 0.0

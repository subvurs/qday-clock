"""Adversarial fixture — ContrastSaturationGate.

Attack scenario: one signal — even from a unique source — has a
normalized contribution so large that any tiny change in that single
observation would swing the whole clock. Either an extractor
overfit on a single article, or a source whose evidence class
genuinely warrants high weight but whose mere presence eclipses
everything else on the axis.

Expectation: ContrastSaturationGate caps any *individual signal's*
share of its axis to ``cap`` (default 0.5). Distinct from
SingleSourceCapGate (which caps per source name, allowing a vendor
that produces five signals to still dominate by aggregate share):
this gate caps per-signal, catching the structurally identical
pathology at the observation level.
"""

from __future__ import annotations

from qday_clock.score.gates import ContrastSaturationGate


# ---------------------------------------------------------------------------
# Over-cap signal fires
# ---------------------------------------------------------------------------


def test_dominant_signal_share_triggers_gate() -> None:
    gate = ContrastSaturationGate(cap=0.5)
    verdict = gate.check(signal_id="sig_a", signal_share=0.9)
    assert verdict.fired is True
    # multiplier == cap / share = 0.5 / 0.9
    assert abs(verdict.multiplier - (0.5 / 0.9)) < 1e-9
    # Post-cap contribution exactly at cap.
    assert abs((0.9 * verdict.multiplier) - 0.5) < 1e-9


def test_signal_at_full_axis_clamps_to_half() -> None:
    """A signal claiming 100% of its axis is the worst case — gets
    halved by the default cap."""
    gate = ContrastSaturationGate(cap=0.5)
    verdict = gate.check(signal_id="sig_solo", signal_share=1.0)
    assert verdict.fired is True
    assert verdict.multiplier == 0.5


# ---------------------------------------------------------------------------
# Under-cap signal is a no-op
# ---------------------------------------------------------------------------


def test_signal_share_under_cap_does_not_fire() -> None:
    gate = ContrastSaturationGate(cap=0.5)
    verdict = gate.check(signal_id="sig_b", signal_share=0.3)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


def test_signal_share_exactly_at_cap_does_not_fire() -> None:
    """Boundary: share == cap → no-op (≤, not <)."""
    gate = ContrastSaturationGate(cap=0.5)
    verdict = gate.check(signal_id="sig_c", signal_share=0.5)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


# ---------------------------------------------------------------------------
# Zero-share signal is a no-op (regression guard)
# ---------------------------------------------------------------------------


def test_zero_share_signal_does_not_fire() -> None:
    gate = ContrastSaturationGate(cap=0.5)
    verdict = gate.check(signal_id="sig_silent", signal_share=0.0)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


# ---------------------------------------------------------------------------
# Custom-cap configuration
# ---------------------------------------------------------------------------


def test_custom_cap_respected() -> None:
    """Operators can tighten the cap for axes where no single signal
    should ever exceed e.g. 25% of the reading."""
    gate = ContrastSaturationGate(cap=0.25)
    verdict = gate.check(signal_id="sig_d", signal_share=0.5)
    assert verdict.fired is True
    assert abs(verdict.multiplier - 0.5) < 1e-9  # 0.25 / 0.5


# ---------------------------------------------------------------------------
# Pathology marker: the gate does NOT care about evidence class —
# that asymmetry is RoadmapWeightCapGate's job
# ---------------------------------------------------------------------------


def test_gate_does_not_depend_on_evidence_class() -> None:
    """ContrastSaturationGate evaluates magnitude only; it does not
    accept a Signal object. Evidence-class judgment belongs to
    RoadmapWeightCapGate (CLAUDE.md §3 separation of concerns)."""
    gate = ContrastSaturationGate(cap=0.5)
    # Same share → same verdict regardless of caller context.
    v1 = gate.check(signal_id="sig_e", signal_share=0.8)
    v2 = gate.check(signal_id="sig_f", signal_share=0.8)
    assert v1.fired == v2.fired
    assert v1.multiplier == v2.multiplier

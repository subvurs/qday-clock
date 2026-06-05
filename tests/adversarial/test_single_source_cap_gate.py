"""Adversarial fixture — SingleSourceCapGate.

Attack scenario: a single vendor publishes five blog posts in one week,
each claiming a different logical-qubit milestone. Without a cap, that
one source dominates the axis reading even though no independent
party has corroborated any of the claims.

Expectation: SingleSourceCapGate caps any source whose pre-cap share
exceeds 0.6, returning a multiplier that brings post-cap share down
to exactly 0.6.
"""

from __future__ import annotations

from qday_clock.score.gates import SingleSourceCapGate


def test_dominant_source_triggers_cap() -> None:
    gate = SingleSourceCapGate(cap=0.6)
    # Hypothetical: vendor X contributes 90% of an axis pre-cap.
    verdict = gate.check("vendor-X", source_share=0.9)
    assert verdict.fired is True
    # multiplier == cap / share => 0.6 / 0.9 = 0.666...
    assert abs(verdict.multiplier - (0.6 / 0.9)) < 1e-9
    # Post-cap share = pre * multiplier == cap.
    assert abs((0.9 * verdict.multiplier) - 0.6) < 1e-9


def test_under_cap_does_not_fire() -> None:
    gate = SingleSourceCapGate(cap=0.6)
    verdict = gate.check("vendor-Y", source_share=0.4)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


def test_at_cap_does_not_fire() -> None:
    gate = SingleSourceCapGate(cap=0.6)
    verdict = gate.check("vendor-Z", source_share=0.6)
    assert verdict.fired is False
    assert verdict.multiplier == 1.0

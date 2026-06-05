"""Adversarial fixture — StaticPointGate.

Attack scenario: a vendor repeats the same announcement every quarter
("we have N logical qubits, distance d"). The headline value never
changes, but if our pipeline treated every republish as a fresh signal
the axis reading would freeze at the vendor's preferred value.

Expectation: StaticPointGate fires when the same signal_id has had
the same normalized_value across the last `window_readings` readings,
capping its contribution by the multiplier.
"""

from __future__ import annotations

from qday_clock.score.gates import StaticPointGate


def test_static_value_across_window_triggers_gate() -> None:
    gate = StaticPointGate(window_readings=5, multiplier=0.5)
    # Five identical readings — classic "freeze" pattern.
    verdict = gate.check("vendor-quarterly-republish", [0.4, 0.4, 0.4, 0.4, 0.4])
    assert verdict.fired is True
    assert verdict.multiplier == 0.5


def test_varying_value_does_not_trigger_gate() -> None:
    gate = StaticPointGate(window_readings=5, multiplier=0.5)
    verdict = gate.check("real-progress", [0.40, 0.42, 0.45, 0.48, 0.50])
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


def test_short_history_does_not_trigger_gate() -> None:
    gate = StaticPointGate(window_readings=5, multiplier=0.5)
    # Only two readings observed so far — not enough evidence for "static".
    verdict = gate.check("new-signal", [0.4, 0.4])
    assert verdict.fired is False

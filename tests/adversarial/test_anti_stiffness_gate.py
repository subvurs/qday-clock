"""Adversarial fixture — AntiStiffnessGate.

Attack scenario: a single overnight signal pile-on (e.g. coordinated
announcement day, paper-bomb on arXiv, conference keynote) tries to
slam an axis reading from 0.30 to 0.85 in one refresh. Even when
multi-source confirmation is satisfied, a step that large is brittle
by construction — it bakes "today's news" into the headline reading
before the second day's evidence can land.

Expectation: AntiStiffnessGate halves any single-refresh axis step
greater than ``max_step`` (default 0.4). The gate fires on magnitude
alone, independent of source count — that is its distinguishing
behavior versus MultiSourceConfirmationGate (which fires on
source-count). Both gates can fire on the same step.
"""

from __future__ import annotations

from qday_clock.score.gates import AntiStiffnessGate


# ---------------------------------------------------------------------------
# Big step fires (positive direction)
# ---------------------------------------------------------------------------


def test_large_positive_step_triggers_gate() -> None:
    gate = AntiStiffnessGate(max_step=0.4, multiplier=0.5)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.30,
        proposed_reading=0.85,  # +0.55
    )
    assert verdict.fired is True
    assert verdict.multiplier == 0.5
    assert "0.550" in verdict.reason


# ---------------------------------------------------------------------------
# Big step fires (negative direction — CLAUDE.md §1 parity)
# ---------------------------------------------------------------------------


def test_large_negative_step_triggers_gate() -> None:
    """A dramatic downward swing (clock walking back) is also brittle."""
    gate = AntiStiffnessGate(max_step=0.4, multiplier=0.5)
    verdict = gate.check(
        axis="error_rate",
        previous_reading=0.80,
        proposed_reading=0.10,  # −0.70
    )
    assert verdict.fired is True
    assert verdict.multiplier == 0.5


# ---------------------------------------------------------------------------
# Step below threshold is a no-op
# ---------------------------------------------------------------------------


def test_step_under_max_step_does_not_fire() -> None:
    gate = AntiStiffnessGate(max_step=0.4)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.30,
        proposed_reading=0.55,  # +0.25
    )
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


def test_step_exactly_at_max_step_does_not_fire() -> None:
    """Boundary is ≤: a step exactly equal to max_step is allowed."""
    gate = AntiStiffnessGate(max_step=0.4)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.30,
        proposed_reading=0.70,  # exactly +0.40
    )
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


# ---------------------------------------------------------------------------
# Zero-step is a no-op (regression guard)
# ---------------------------------------------------------------------------


def test_zero_step_does_not_fire() -> None:
    gate = AntiStiffnessGate(max_step=0.4)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.42,
        proposed_reading=0.42,
    )
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


# ---------------------------------------------------------------------------
# Custom configuration
# ---------------------------------------------------------------------------


def test_custom_max_step_respected() -> None:
    """Operators can tighten the gate for slow-moving axes."""
    gate = AntiStiffnessGate(max_step=0.1, multiplier=0.25)
    verdict = gate.check(
        axis="pqc_migration",
        previous_reading=0.20,
        proposed_reading=0.40,  # +0.20
    )
    assert verdict.fired is True
    assert verdict.multiplier == 0.25

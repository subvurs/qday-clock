"""Adversarial fixture — MultiSourceConfirmationGate.

Attack scenario: a single vendor or arXiv author publishes a dramatic
result that, taken at face value, would jump an axis by >0.15 in a
single refresh. Without confirmation, that one source moves the
public clock hand.

Expectation: MultiSourceConfirmationGate fires (multiplier 0.5) when
a proposed step-change exceeds ``min_step`` and fewer than
``min_sources`` independent sources have spoken within the
``window_days`` window. The gate stays silent when corroboration
arrives, when the step is small, or when independent sources confirm.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from qday_clock.core.schemas import AxisId, EvidenceClass, Signal
from qday_clock.score.gates import MultiSourceConfirmationGate

_NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _signal(
    *,
    signal_id: str,
    source: str,
    days_ago: int = 1,
    normalized_value: float = 0.6,
) -> Signal:
    observed = _NOW - timedelta(days=days_ago)
    return Signal(
        signal_id=signal_id,
        axis=AxisId.LOGICAL_QUBITS,
        title=f"signal {signal_id}",
        summary="",
        source=source,
        url=None,
        published_at=observed,
        observed_at=observed,
        evidence_class=EvidenceClass.HARDWARE,
        raw_value=11.0,
        normalized_value=normalized_value,
        confidence=0.8,
    )


# ---------------------------------------------------------------------------
# Fires when step is large and only one source has spoken
# ---------------------------------------------------------------------------


def test_unconfirmed_big_step_triggers_gate() -> None:
    gate = MultiSourceConfirmationGate(min_step=0.15, min_sources=2, window_days=30, multiplier=0.5)
    # Only one source corroborating a +0.25 jump.
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.30,
        proposed_reading=0.55,
        contributing_signals=[_signal(signal_id="s1", source="Vendor X")],
        now=_NOW,
    )
    assert verdict.fired is True
    assert verdict.multiplier == 0.5
    assert "1 independent source" in verdict.reason


# ---------------------------------------------------------------------------
# Silent when two distinct sources confirm
# ---------------------------------------------------------------------------


def test_two_sources_within_window_do_not_trigger_gate() -> None:
    gate = MultiSourceConfirmationGate(min_step=0.15, min_sources=2, window_days=30, multiplier=0.5)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.30,
        proposed_reading=0.55,
        contributing_signals=[
            _signal(signal_id="s1", source="Vendor X", days_ago=2),
            _signal(signal_id="s2", source="Independent Lab Y", days_ago=10),
        ],
        now=_NOW,
    )
    assert verdict.fired is False
    assert verdict.multiplier == 1.0


# ---------------------------------------------------------------------------
# Same source twice does not count as confirmation
# ---------------------------------------------------------------------------


def test_same_source_twice_still_triggers_gate() -> None:
    """An attacker republishing under the same source name does NOT
    count as independent corroboration — the gate compares distinct
    source strings."""
    gate = MultiSourceConfirmationGate(min_step=0.15, min_sources=2, window_days=30, multiplier=0.5)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.30,
        proposed_reading=0.55,
        contributing_signals=[
            _signal(signal_id="s1", source="Vendor X", days_ago=1),
            _signal(signal_id="s2", source="Vendor X", days_ago=5),
        ],
        now=_NOW,
    )
    assert verdict.fired is True


# ---------------------------------------------------------------------------
# Old confirmation outside window does not count
# ---------------------------------------------------------------------------


def test_stale_corroboration_outside_window_does_not_help() -> None:
    """A second source from 60 days ago doesn't rescue today's big jump."""
    gate = MultiSourceConfirmationGate(min_step=0.15, min_sources=2, window_days=30, multiplier=0.5)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.30,
        proposed_reading=0.55,
        contributing_signals=[
            _signal(signal_id="s1", source="Vendor X", days_ago=2),
            _signal(signal_id="s2", source="Old Lab", days_ago=60),
        ],
        now=_NOW,
    )
    assert verdict.fired is True
    assert "1 independent source" in verdict.reason


# ---------------------------------------------------------------------------
# Small step never requires confirmation
# ---------------------------------------------------------------------------


def test_small_step_below_threshold_does_not_trigger() -> None:
    gate = MultiSourceConfirmationGate(min_step=0.15, min_sources=2, window_days=30, multiplier=0.5)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.30,
        proposed_reading=0.40,  # +0.10, below 0.15 threshold
        contributing_signals=[_signal(signal_id="s1", source="Vendor X")],
        now=_NOW,
    )
    assert verdict.fired is False
    assert "no confirmation required" in verdict.reason


def test_step_exactly_at_threshold_does_not_trigger() -> None:
    """Threshold is strictly greater-than, not greater-or-equal."""
    gate = MultiSourceConfirmationGate(min_step=0.15, min_sources=2, window_days=30, multiplier=0.5)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.30,
        proposed_reading=0.45,  # exactly +0.15
        contributing_signals=[_signal(signal_id="s1", source="Vendor X")],
        now=_NOW,
    )
    assert verdict.fired is False


# ---------------------------------------------------------------------------
# Negative step (clock walking back) is treated symmetrically
# ---------------------------------------------------------------------------


def test_negative_step_also_subject_to_confirmation() -> None:
    """A sudden DROP of >0.15 (clock walking back) also requires
    multi-source confirmation. Per CLAUDE.md §1, reversals get the
    same scrutiny as advances."""
    gate = MultiSourceConfirmationGate(min_step=0.15, min_sources=2, window_days=30, multiplier=0.5)
    verdict = gate.check(
        axis="logical_qubits",
        previous_reading=0.60,
        proposed_reading=0.35,  # −0.25
        contributing_signals=[_signal(signal_id="s1", source="Skeptic Blog")],
        now=_NOW,
    )
    assert verdict.fired is True

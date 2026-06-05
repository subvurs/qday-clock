"""Adversarial fixture — ThresholdGuard.

Attack scenario: someone edits the runtime display thresholds (which
determine clock-hand colors and alert bands) without going through
the CHANGELOG / signed-release process. ThresholdGuard must fail-closed:
its assert_locked() must raise ThresholdDriftError so the CI step
blocks the release.

Per CLAUDE.md §7 (no silent test weakening) and §8 (no silent error
swallowing).
"""

from __future__ import annotations

import pytest

from qday_clock.core.errors import ThresholdDriftError
from qday_clock.score.gates import ThresholdGuard, lock_thresholds


def test_matching_thresholds_pass(tmp_path) -> None:
    thresholds = {"alert": 0.5, "warn": 0.3}
    lock_path = tmp_path / "lock.json"
    lock_thresholds(thresholds, lock_path)
    guard = ThresholdGuard(lock_path=lock_path)
    verdict = guard.check(thresholds)
    assert verdict.fired is False


def test_drifted_thresholds_fire_gate(tmp_path) -> None:
    locked = {"alert": 0.5, "warn": 0.3}
    drifted = {"alert": 0.4, "warn": 0.3}  # someone moved a threshold
    lock_path = tmp_path / "lock.json"
    lock_thresholds(locked, lock_path)
    guard = ThresholdGuard(lock_path=lock_path)
    verdict = guard.check(drifted)
    assert verdict.fired is True
    assert "drift detected" in verdict.reason.lower()


def test_assert_locked_raises_on_drift(tmp_path) -> None:
    locked = {"alert": 0.5, "warn": 0.3}
    drifted = {"alert": 0.99, "warn": 0.3}
    lock_path = tmp_path / "lock.json"
    lock_thresholds(locked, lock_path)
    guard = ThresholdGuard(lock_path=lock_path)
    with pytest.raises(ThresholdDriftError):
        guard.assert_locked(drifted)


def test_missing_lock_file_fires_gate(tmp_path) -> None:
    lock_path = tmp_path / "does_not_exist.json"
    guard = ThresholdGuard(lock_path=lock_path)
    verdict = guard.check({"alert": 0.5})
    assert verdict.fired is True
    assert "missing" in verdict.reason.lower()

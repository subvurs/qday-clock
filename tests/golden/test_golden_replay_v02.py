"""Golden replay test — v0.2 gate-fire fixture.

Companion to ``test_golden_replay.py``:

* ``manifest_2026_q1.json`` locks v0.1 *pre-gate* scoring (no v0.2 gate
  fires; that hash must stay stable through any v0.2 refactor that
  preserves the "no triggering pathology" path).
* ``manifest_2026_v02.json`` locks v0.2 *gate-reachable* scoring: the
  fixture deterministically triggers ``RoadmapWeightCapGate`` (one
  roadmap-evidence signal at normalized_value 0.9 above the 0.3 cap)
  and ``StaleSignalGate`` (one signal with explicit ``observed_at``
  ~730 days before the fixture's ``now`` — inside the [540, 1080] day
  decay window).

Per CLAUDE.md §7 this hash MUST NOT be silently bumped. If this test
fails, either (a) a real change to v0.2 scoring or gate behavior
shifted the output — update the expected hash in the same PR that
documents the change in CHANGELOG.md, or (b) drift was introduced —
investigate before bypassing.

Per CLAUDE.md §9 the gate-fire assertions are the Goodhart contract:
the same v0.2 fixture must continue to fire the same gates by name.
Silently dropping a gate from the pipeline will trip this test even if
the hash happens to coincide (which it would not, but the explicit
verdict-name check makes the regression obvious).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from qday_clock.core.canonical import canonicalize
from qday_clock.core.schemas import AxisId, EvidenceClass, Signal
from qday_clock.ingest.seed_signals import _stable_signal_id
from qday_clock.score.clock import compute_clock_state
from qday_clock.score.gri_baseline import GRIBaseline


FIXTURE_PATH = Path(__file__).resolve().parent / "manifest_2026_v02.json"

# Locked expected canonical-hash of the unsigned ClockState body produced
# by replaying ``manifest_2026_v02.json``. Computed once at lock time and
# pinned here; any drift causes CI to fail.
#
# To re-lock (only when CHANGELOG documents the change), set this to
# ``None`` and run pytest with -s; the test will print the actual hash.
EXPECTED_CANONICAL_HASH = (
    "96eb797b8a006bf93eae7026b4d49837867c329cd0d767f30e058f6a01ce14b1"
)  # re-locked in v0.2.4 after methodology_url rename to https://icqubit.com/methodology.html

# Locked set of gate names that MUST fire on this fixture. Per
# CLAUDE.md §9 this is the Goodhart contract: a silent disconnection of
# RoadmapWeightCapGate or StaleSignalGate from compute_clock_state must
# trip this test even if hashes happen to coincide.
REQUIRED_GATE_FIRES = {
    "RoadmapWeightCapGate": 1,
    "StaleSignalGate": 1,
}


def _parse_dt(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def _signals_from_fixture(fixture: dict, observed_at: datetime) -> list[Signal]:
    """Reconstruct Signal objects honoring optional per-signal
    ``observed_at`` override (used here to age the d=3 archival signal
    so StaleSignalGate fires deterministically).
    """
    out: list[Signal] = []
    for entry in fixture["signals"]:
        published_at = _parse_dt(entry["published_at"])
        entry_observed_at = (
            _parse_dt(entry["observed_at"]) if "observed_at" in entry else observed_at
        )
        out.append(
            Signal(
                signal_id=_stable_signal_id(
                    entry["source"], entry["title"], published_at
                ),
                axis=AxisId(entry["axis"]),
                title=entry["title"],
                summary=entry["summary"],
                source=entry["source"],
                url=entry.get("url"),
                published_at=published_at,
                observed_at=entry_observed_at,
                evidence_class=EvidenceClass(entry["evidence_class"]),
                raw_value=float(entry["raw_value"]),
                normalized_value=float(entry["normalized_value"]),
                confidence=float(entry.get("confidence", 1.0)),
            )
        )
    return out


def _gri_from_fixture(fixture: dict) -> GRIBaseline:
    g = fixture["gri_baseline"]
    return GRIBaseline(
        survey_year=int(g["survey_year"]),
        median_crqc_year=int(g["median_crqc_year"]),
        label=g["label"],
        source=g["source"],
    )


def _canonical_unsigned_hash(state_dict: dict) -> str:
    body = {
        k: v for k, v in state_dict.items() if k not in ("signature", "signing_pubkey")
    }
    return hashlib.sha256(canonicalize(body)).hexdigest()


def test_golden_replay_v02_byte_for_byte() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    observed_at = _parse_dt(fixture["observed_at"])
    generated_at = _parse_dt(fixture["generated_at"])

    signals = _signals_from_fixture(fixture, observed_at=observed_at)
    gri = _gri_from_fixture(fixture)

    # Pin ``now`` to the fixture's observed_at — same forever-deterministic
    # discipline as test_golden_replay.py; per-signal observed_at overrides
    # are what age the stale signal, not a moving ``now``.
    state = compute_clock_state(signals, gri=gri, now=observed_at)
    state = state.model_copy(update={"generated_at": generated_at})

    body = state.model_dump(mode="json")
    actual_hash = _canonical_unsigned_hash(body)

    if EXPECTED_CANONICAL_HASH is None:
        print(f"\nGOLDEN REPLAY HASH v0.2 (lock this): {actual_hash}")
        pytest.skip(
            "EXPECTED_CANONICAL_HASH is None; rerun with the printed hash "
            "pinned in this file (CHANGELOG entry required)."
        )

    assert actual_hash == EXPECTED_CANONICAL_HASH, (
        f"Golden v0.2 replay hash drift!\n"
        f"  expected: {EXPECTED_CANONICAL_HASH}\n"
        f"  actual:   {actual_hash}\n"
        f"Per CLAUDE.md §7 do not silently update this hash; "
        f"investigate the cause and document in CHANGELOG before re-locking."
    )


def test_golden_replay_v02_required_gates_fire() -> None:
    """The v0.2 fixture must trigger the v0.2 gates it was built to
    exercise. Locks the Goodhart contract per CLAUDE.md §9.
    """
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    observed_at = _parse_dt(fixture["observed_at"])
    signals = _signals_from_fixture(fixture, observed_at=observed_at)
    gri = _gri_from_fixture(fixture)

    state = compute_clock_state(signals, gri=gri, now=observed_at)

    fire_counts = Counter(v["name"] for v in state.gates_fired)
    for gate_name, required_count in REQUIRED_GATE_FIRES.items():
        actual = fire_counts.get(gate_name, 0)
        assert actual >= required_count, (
            f"v0.2 golden fixture expected at least {required_count} "
            f"{gate_name} fire(s); got {actual}. "
            f"gates_fired = {state.gates_fired}"
        )


def test_golden_replay_v02_clock_hours_in_range() -> None:
    """Independent of hash-locking: the replay must produce a clock
    reading inside the 24-hour face. Catches catastrophic regressions
    (e.g. score = NaN) even when EXPECTED_CANONICAL_HASH is None."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    observed_at = _parse_dt(fixture["observed_at"])
    signals = _signals_from_fixture(fixture, observed_at=observed_at)
    gri = _gri_from_fixture(fixture)

    state = compute_clock_state(signals, gri=gri, now=observed_at)
    assert 0.0 <= state.clock_hours <= 24.0
    assert 0.0 <= state.clock_score <= 1.0
    # All 5 axes are populated in this fixture; none should be cold-start.
    for axis in AxisId:
        a = state.axes[axis.value]
        assert len(a.contributing_signal_ids) > 0, (
            f"axis {axis.value} unexpectedly cold-start in v0.2 fixture"
        )

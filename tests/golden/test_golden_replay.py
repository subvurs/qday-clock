"""Golden replay test.

Per plan section G:

    Locked input fixture (5 representative articles + GRI 2024 row)
    produces a locked clock_state.json. Hash-locked so any drift triggers
    CI fail.

This test:

1. Loads ``manifest_2026_q1.json`` (the locked input)
2. Reconstructs Signal objects with fixed observed_at (so the run is
   fully deterministic — the seed loader uses datetime.now() which
   would defeat byte-for-byte comparison)
3. Calls ``compute_clock_state()``
4. Pins ``generated_at`` to the fixture's deterministic timestamp
5. Canonicalizes (RFC 8785) and computes the SHA-256 hash
6. Asserts the hash matches the locked expected hash

If this test fails, either:

  (a) A real change to the scoring pipeline shifted the output —
      update the expected hash in the same PR that documents the
      change in CHANGELOG.md, OR
  (b) Drift was introduced — investigate before bypassing.

Per CLAUDE.md section 7, do not silently weaken this test.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from qday_clock.core.canonical import canonicalize
from qday_clock.core.schemas import AxisId, EvidenceClass, Signal
from qday_clock.ingest.seed_signals import _stable_signal_id
from qday_clock.score.clock import compute_clock_state
from qday_clock.score.gri_baseline import GRIBaseline


FIXTURE_PATH = Path(__file__).resolve().parent / "manifest_2026_q1.json"

# Locked expected canonical-hash of the unsigned ClockState body produced
# by replaying ``manifest_2026_q1.json``. Computed once at lock time and
# pinned here; any drift causes CI to fail.
#
# To re-lock (only when CHANGELOG documents the change), set this to
# ``None`` and run pytest with -s; the test will print the actual hash.
EXPECTED_CANONICAL_HASH = "aa5a8c11dd0981ce19a191aa74eadeb7ec51211f7efe7793aff0b5bbee242fe9"


def _parse_dt(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def _signals_from_fixture(fixture: dict, observed_at: datetime) -> list[Signal]:
    """Reconstruct Signal objects with a *fixed* observed_at.

    The seed-signal loader uses ``datetime.now()`` for ``observed_at``
    which is fine for production but kills determinism in golden replay.
    We bypass it here.
    """
    out: list[Signal] = []
    for entry in fixture["signals"]:
        published_at = _parse_dt(entry["published_at"])
        # Optional per-signal ``observed_at`` override — see
        # qday_clock/verify/replay.py for rationale.
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
    body = {k: v for k, v in state_dict.items() if k not in ("signature", "signing_pubkey")}
    return hashlib.sha256(canonicalize(body)).hexdigest()


def test_golden_replay_byte_for_byte() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    observed_at = _parse_dt(fixture["observed_at"])
    generated_at = _parse_dt(fixture["generated_at"])

    signals = _signals_from_fixture(fixture, observed_at=observed_at)
    gri = _gri_from_fixture(fixture)

    # Pin ``now`` to the fixture's observed_at so the v0.2 StaleSignalGate
    # is evaluated against a fixed reference. Without this, the gate's
    # decay multiplier would silently drift the canonical hash once the
    # signals cross the 18-month fresh window (~2027-09-29). Per
    # CLAUDE.md §7 the test stays forever-deterministic.
    state = compute_clock_state(signals, gri=gri, now=observed_at)
    # Pin generated_at so the canonical output is fully deterministic.
    state = state.model_copy(update={"generated_at": generated_at})

    body = state.model_dump(mode="json")
    actual_hash = _canonical_unsigned_hash(body)

    if EXPECTED_CANONICAL_HASH is None:
        # Bootstrap mode: print so the operator can lock the value.
        print(f"\nGOLDEN REPLAY HASH (lock this): {actual_hash}")
        pytest.skip(
            "EXPECTED_CANONICAL_HASH is None; rerun with the printed hash "
            "pinned in this file (CHANGELOG entry required)."
        )

    assert actual_hash == EXPECTED_CANONICAL_HASH, (
        f"Golden replay hash drift!\n"
        f"  expected: {EXPECTED_CANONICAL_HASH}\n"
        f"  actual:   {actual_hash}\n"
        f"Per CLAUDE.md section 7 do not silently update this hash; "
        f"investigate the cause and document in CHANGELOG before re-locking."
    )


def test_golden_replay_clock_hours_in_range() -> None:
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
    # Axis 1 should not be cold-start (we provided 5 signals for it).
    a1 = state.axes[AxisId.LOGICAL_QUBITS.value]
    assert len(a1.contributing_signal_ids) > 0

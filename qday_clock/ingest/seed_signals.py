"""Seed signal loader.

For MVP we ship a small hand-curated set of anchor signals so the clock
has something to read on day 1. These are *not* sourced from the Curator
corpus — they come from the data/ directory and are reviewed by Mark
before merge.

The seed set is intentionally small (≤ 10 entries) and biased toward
well-known peer-reviewed milestones (Gidney-Ekera, Google distance-7
surface code, IBM Condor announcement, NIST FIPS 203 publication) so
the cold-start reading is anchored to facts that already passed
external review.

Anything pulled from press releases or roadmaps is tagged
``EvidenceClass.ROADMAP`` so the v0.2 ``RoadmapWeightCapGate`` can
cap its contribution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from qday_clock.core.errors import IngestError
from qday_clock.core.schemas import AxisId, EvidenceClass, Signal
from qday_clock.core.time import to_utc


def _stable_signal_id(source: str, title: str, published_at: datetime) -> str:
    """Hash-based deterministic signal ID. No randomness.

    The ID is stable across re-runs given the same inputs, which is
    required for golden-test replay (CLAUDE.md §4 reproducibility).
    """
    h = hashlib.sha256()
    h.update(source.encode("utf-8"))
    h.update(b"\x00")
    h.update(title.encode("utf-8"))
    h.update(b"\x00")
    h.update(to_utc(published_at).isoformat().encode("utf-8"))
    return h.hexdigest()[:16]


def load_seed_signals(path: Path | str) -> list[Signal]:
    """Load seed signals from a JSON file at ``path``.

    The expected file shape::

        {
          "version": "1.0",
          "signals": [
            {
              "axis": "logical_qubits",
              "title": "...",
              "summary": "...",
              "source": "...",
              "url": "...",
              "published_at": "2024-12-09T00:00:00Z",
              "evidence_class": "hardware",
              "raw_value": 7.0,
              "normalized_value": 0.5,
              "confidence": 1.0
            }
          ]
        }

    Errors propagate as :class:`IngestError` per CLAUDE.md §8 — never
    silently swallowed.
    """
    path = Path(path)
    if not path.exists():
        raise IngestError(
            f"seed signals file does not exist: {path}",
            error_code="ingest.seed_missing",
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestError(
            f"seed signals file is not valid JSON: {exc}",
            error_code="ingest.seed_bad_json",
        ) from exc

    if not isinstance(data, dict) or "signals" not in data:
        raise IngestError(
            "seed signals file must be {'version': ..., 'signals': [...]}",
            error_code="ingest.seed_bad_shape",
        )

    out: list[Signal] = []
    observed_at = datetime.now(tz=timezone.utc)

    for idx, entry in enumerate(data["signals"]):
        try:
            axis = AxisId(entry["axis"])
            evidence_class = EvidenceClass(entry["evidence_class"])
            published_at = _parse_dt(entry["published_at"])
            signal = Signal(
                signal_id=_stable_signal_id(
                    entry["source"], entry["title"], published_at
                ),
                axis=axis,
                title=entry["title"],
                summary=entry["summary"],
                source=entry["source"],
                url=entry.get("url"),
                published_at=published_at,
                observed_at=observed_at,
                evidence_class=evidence_class,
                raw_value=float(entry["raw_value"]),
                normalized_value=float(entry["normalized_value"]),
                confidence=float(entry.get("confidence", 1.0)),
            )
        except KeyError as exc:
            raise IngestError(
                f"seed signal #{idx} missing field: {exc}",
                error_code="ingest.seed_missing_field",
            ) from exc
        except ValueError as exc:
            # Explicitly captured (not swallowed): bad enum / cast failure.
            raise IngestError(
                f"seed signal #{idx} has invalid value: {exc}",
                error_code="ingest.seed_bad_value",
            ) from exc
        out.append(signal)

    return out


def _parse_dt(raw: str) -> datetime:
    """Parse an ISO-8601 datetime string, accept trailing Z."""
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise IngestError(
            f"invalid datetime: {raw!r}",
            error_code="ingest.bad_datetime",
        ) from exc

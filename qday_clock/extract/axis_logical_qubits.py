"""Axis 1 — Logical qubit progress extractor.

Deterministic. Given an article (title + summary), decide whether it
contributes a logical-qubit signal and, if so, extract a numeric
distance and normalize to ``[0, 1]`` per the anchor map in METHODOLOGY.md
§3 Axis 1:

- ``0.0`` ← d=3
- ``0.5`` ← d=7..11
- ``0.9`` ← multi-logical-qubit algorithms at low logical error rate
- ``1.0`` ← Shor on > 2048-bit RSA on real hardware

This extractor is conservative: it returns ``None`` when no robust
distance can be extracted (CLAUDE.md §10 — calibrated uncertainty;
don't pretend to know what we don't).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from qday_clock.extract.keywords import LOGICAL_QUBIT_KEYWORDS

#: Match e.g. "distance-7", "d = 7", "code distance 11"
_DISTANCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"distance[\s\-_]*(\d{1,2})", re.IGNORECASE),
    re.compile(r"\bd[\s=]+(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"code distance\s+(\d{1,2})", re.IGNORECASE),
)

#: Match e.g. "12 logical qubits", "multiple logical qubits"
_LOGICAL_COUNT_PATTERN = re.compile(
    r"(\d{1,3})\s+logical\s+qubits?", re.IGNORECASE
)


@dataclass(frozen=True)
class LogicalQubitExtraction:
    """Result of running the logical-qubit extractor on an article."""

    distance: Optional[int]
    n_logical: Optional[int]
    normalized_value: float
    rationale: str


def matches(title: str, summary: str) -> bool:
    """Return True if the article's text contains any logical-qubit keyword."""
    blob = f"{title}\n{summary}".lower()
    return any(kw in blob for kw in LOGICAL_QUBIT_KEYWORDS)


def extract(title: str, summary: str) -> Optional[LogicalQubitExtraction]:
    """Extract a logical-qubit signal from ``title + summary``.

    Returns ``None`` when the article matches a keyword but yields no
    extractable numeric value — that is a deliberate fail-conservative
    behavior (per CLAUDE.md §10).
    """
    if not matches(title, summary):
        return None

    blob = f"{title}\n{summary}"
    distance = _first_distance(blob)
    n_logical = _logical_count(blob)

    if distance is None and n_logical is None:
        return None

    normalized, rationale = _map_to_unit(distance, n_logical, blob)
    return LogicalQubitExtraction(
        distance=distance,
        n_logical=n_logical,
        normalized_value=normalized,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_distance(blob: str) -> Optional[int]:
    for pat in _DISTANCE_PATTERNS:
        m = pat.search(blob)
        if m:
            try:
                d = int(m.group(1))
            except ValueError:
                # Explicitly caught: a malformed digit group (group 1 not int).
                # Fall through to other patterns rather than blowing up.
                continue
            if 1 <= d <= 99:
                return d
    return None


def _logical_count(blob: str) -> Optional[int]:
    m = _LOGICAL_COUNT_PATTERN.search(blob)
    if m:
        try:
            n = int(m.group(1))
        except ValueError:
            return None
        if 1 <= n <= 999:
            return n
    return None


def _map_to_unit(
    distance: Optional[int],
    n_logical: Optional[int],
    blob: str,
) -> tuple[float, str]:
    """Map an extracted (distance, n_logical, text-hints) tuple to ``[0,1]``.

    Anchor map from METHODOLOGY.md §3 Axis 1:

    - d=3 → 0.0
    - d=5 → 0.35 (linear interp between d=3 and d=7)
    - d=7..11 → 0.5
    - multi-logical (n_logical >= 4) and "below threshold" hint → 0.65
    - n_logical >= 10 with code-family note → 0.8
    - explicit Shor on RSA-2048 mention → 1.0
    """
    lower = blob.lower()

    # Strongest signal: a literal claim of Shor-on-RSA-2048 on hardware.
    if "shor" in lower and ("rsa-2048" in lower or "rsa 2048" in lower):
        if "hardware" in lower or "device" in lower or "ibm" in lower or "google" in lower:
            return 1.0, "literal Shor-on-RSA-2048 claim on hardware"

    # Multi-logical at low error rate (the "0.9" anchor).
    if n_logical is not None and n_logical >= 10:
        if "below threshold" in lower or "below the threshold" in lower:
            return 0.85, f"{n_logical} logical qubits below threshold"
        return 0.7, f"{n_logical} logical qubits"

    # Multi-logical (4-9) with hint of error suppression.
    if n_logical is not None and n_logical >= 4:
        if "below threshold" in lower or "below the threshold" in lower:
            return 0.65, f"{n_logical} logical qubits below threshold"
        return 0.55, f"{n_logical} logical qubits"

    # Single logical qubit, distance-anchored mapping.
    if distance is not None:
        if distance <= 3:
            return 0.0, f"distance-{distance} (historical baseline)"
        if distance <= 5:
            # linear interp d=3 -> 0.0, d=7 -> 0.5; d=5 -> ~0.35
            return 0.35, f"distance-{distance} (early FT)"
        if distance <= 11:
            return 0.5, f"distance-{distance} (small-scale FT)"
        if distance <= 17:
            return 0.6, f"distance-{distance} (mid-scale FT)"
        return 0.7, f"distance-{distance} (large-scale FT)"

    return 0.0, "no extractable numeric — fail conservative"

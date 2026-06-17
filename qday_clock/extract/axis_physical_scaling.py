"""Axis 2 — Physical qubit scaling extractor.

Deterministic. Given an article (title + summary), decide whether it
contributes a physical-qubit-count signal and, if so, extract a numeric
qubit count and normalize to ``[0, 1]`` per the anchor map in
METHODOLOGY.md §3 Axis 2:

- ``0.0`` ← 100 physical qubits  (NISQ baseline)
- ``0.4`` ← 10,000 physical qubits
- ``0.7`` ← 1,000,000 physical qubits
- ``1.0`` ← 20,000,000 physical qubits  (Gidney-Ekera 2019 RSA-2048 estimate)

The mapping is log-linear in qubit count: every ~10× in physical scale
moves the axis ~0.2 toward Q-day. Below 100 qubits floors at 0.0; above
20M floors at 1.0.

Per CLAUDE.md §10 (calibrated uncertainty) this extractor returns
``None`` when no numeric qubit count can be extracted, even if the
keyword catalogue matches — a vendor *naming* a roadmap milestone
without a number is not enough. Vendor names with publicly-known
qubit counts (Condor=1121, Willow=105, etc.) are intentionally NOT
auto-substituted; we want the article to cite the number.

Per CLAUDE.md §3 (evidence-class distinction) the caller (classifier)
is responsible for tagging roadmap announcements as
``EvidenceClass.ROADMAP`` — this extractor is evidence-class blind.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from qday_clock.extract.keywords import PHYSICAL_SCALING_KEYWORDS

#: Patterns for "N qubit(s)" / "N-qubit" / "N physical qubits" with
#: thousands-comma tolerance. The qubit count is anchored to its unit
#: word so vendor-version numbers (e.g. "v2.0") don't false-positive.
_QUBIT_COUNT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(\d{1,3}(?:,\d{3})+|\d{2,8})\s*[-\s]?physical[\s\-]?qubits?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,3}(?:,\d{3})+|\d{2,8})\s*[-\s]?qubit\s+(?:processor|chip|device|machine|system|computer)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,3}(?:,\d{3})+|\d{2,8})[-\s]qubit\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,3}(?:,\d{3})+|\d{2,8})\s+qubits?\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class PhysicalScalingExtraction:
    """Result of running the physical-scaling extractor on an article."""

    n_qubits: int
    normalized_value: float
    rationale: str


def matches(title: str, summary: str) -> bool:
    """Return True if the article's text contains any axis-2 keyword."""
    blob = f"{title}\n{summary}".lower()
    return any(kw in blob for kw in PHYSICAL_SCALING_KEYWORDS)


def extract(title: str, summary: str) -> PhysicalScalingExtraction | None:
    """Extract a physical-qubit-count signal from ``title + summary``.

    Returns ``None`` when the article matches a keyword but yields no
    extractable numeric value — fail-conservative per CLAUDE.md §10.
    """
    if not matches(title, summary):
        return None

    blob = f"{title}\n{summary}"
    n = _largest_qubit_count(blob)
    if n is None:
        return None

    normalized, rationale = _map_to_unit(n)
    return PhysicalScalingExtraction(
        n_qubits=n,
        normalized_value=normalized,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _largest_qubit_count(blob: str) -> int | None:
    """Return the largest plausible qubit count found in ``blob``.

    Plausibility floor: 10. Anything smaller (e.g. "5 qubits demo") is a
    NISQ-era demo unrelated to scaling and floors the axis anyway, so
    we don't bother emitting a signal — fail-conservative.
    """
    candidates: list[int] = []
    for pat in _QUBIT_COUNT_PATTERNS:
        for m in pat.finditer(blob):
            raw = m.group(1).replace(",", "")
            try:
                n = int(raw)
            except ValueError:
                # Explicitly handled: malformed digit group. Skip.
                continue
            if 10 <= n <= 100_000_000:
                candidates.append(n)
    if not candidates:
        return None
    return max(candidates)


# Anchor points (qubits, normalized). Log-linear between adjacent anchors.
_ANCHORS: tuple[tuple[float, float], ...] = (
    (math.log10(100.0), 0.0),
    (math.log10(10_000.0), 0.4),
    (math.log10(1_000_000.0), 0.7),
    (math.log10(20_000_000.0), 1.0),
)


def _map_to_unit(n_qubits: int) -> tuple[float, str]:
    """Map ``n_qubits`` to ``[0, 1]`` via log-linear interpolation."""
    if n_qubits <= 100:
        return 0.0, f"{n_qubits} qubits (≤ NISQ baseline 100)"
    if n_qubits >= 20_000_000:
        return 1.0, f"{n_qubits} qubits (≥ Gidney-Ekera RSA-2048 estimate)"

    x = math.log10(float(n_qubits))
    for (x0, y0), (x1, y1) in zip(_ANCHORS, _ANCHORS[1:], strict=False):
        if x0 <= x <= x1:
            frac = (x - x0) / (x1 - x0)
            y = y0 + frac * (y1 - y0)
            # Clamp defensively — anchors are sorted but rounding could
            # produce a value microscopically outside [0, 1].
            y = max(0.0, min(1.0, y))
            return y, f"{n_qubits} physical qubits (log-interp)"

    # Fall-through: shouldn't happen given the floors above, but stay
    # conservative.
    return 0.0, f"{n_qubits} qubits (out-of-anchor)"

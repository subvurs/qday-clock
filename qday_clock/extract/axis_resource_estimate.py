"""Axis 3 — Algorithmic / resource-estimate extractor (weight 0.30).

Tracks two distinct attack channels against the threat-modelled
primitives (per ``THREAT_MODEL.md``):

* **Shor against RSA-2048** — qubit / time resource estimates for
  factoring RSA-2048. Anchored to Gidney-Ekera 2019 (~20M qubits,
  ~8 hours).
* **Grover against AES-128** — sub-channel, folded with a 0.3
  sub-weight inside this axis so a "Grover weakens AES-128"
  announcement contributes at most ``0.3`` to the axis reading. This
  matches the framing of AES being *weakened* (effective security
  ~2⁶⁴) rather than broken outright.

Anchor map (Shor channel) from METHODOLOGY.md §3 Axis 3:

- ``0.0`` ← 20,000,000 qubits OR 8 hours (Gidney-Ekera baseline)
- ``0.5`` ← ≤ 1,000,000 qubits OR ≤ 1 hour
- ``1.0`` ← ≤ 100,000 qubits OR ≤ 1 minute

Anchor map (AES sub-channel):

- ``0.0`` ← theoretical Grover-on-AES-128 baseline (2⁶⁴ queries,
  no practical advantage announced)
- ``0.5`` ← constant-factor or T-count improvement on Grover-on-AES-128
- ``1.0`` ← AES-128 practically broken

Per CLAUDE.md §10, fail-conservative: returns ``None`` when keywords
hit but no extractable numeric value or no sub-channel claim is found.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional

from qday_clock.extract.keywords import RESOURCE_ESTIMATE_KEYWORDS

#: Sub-weight applied to AES-only signals — fold AES contribution to
#: at most 0.3 of the axis. See module docstring + METHODOLOGY.md §3.
AES_SUB_WEIGHT: float = 0.3

# Magnitude suffix → multiplier. Lower-cased before lookup.
_MAGNITUDE_SUFFIXES: dict[str, float] = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "million": 1e6,
    "b": 1e9,
    "billion": 1e9,
}

# "20 million qubits", "1.5 million qubits", "100,000 qubits",
# "100k qubits", "20M qubits", "100,000 physical qubits"
_QUBITS_TO_FACTOR_PATTERN = re.compile(
    r"(\d+(?:[\.,]\d+)?)\s*(million|billion|thousand|k|m|b)?\s*(?:physical\s*)?qubits"
    r"(?:\s+(?:to\s+)?(?:factor|break|attack))?",
    re.IGNORECASE,
)

_HOURS_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b",
    re.IGNORECASE,
)

_MINUTES_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?)\b",
    re.IGNORECASE,
)

_DAYS_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*days?\b",
    re.IGNORECASE,
)

_RSA_2048_MENTIONS: tuple[str, ...] = (
    "rsa-2048",
    "rsa 2048",
    "rsa2048",
    "factor rsa",
    "factoring rsa",
    "2048-bit rsa",
    "2048 bit rsa",
)

_AES_128_MENTIONS: tuple[str, ...] = (
    "aes-128",
    "aes 128",
    "aes128",
)

_GROVER_MENTIONS: tuple[str, ...] = (
    "grover",
)


@dataclass(frozen=True)
class ResourceEstimateExtraction:
    """Result of running the axis-3 extractor on an article."""

    channel: str  # "shor" or "aes_grover"
    qubits_to_factor: Optional[int]
    time_to_factor_minutes: Optional[float]
    normalized_value: float
    rationale: str


def matches(title: str, summary: str) -> bool:
    """Return True if the article's text contains any axis-3 keyword."""
    blob = f"{title}\n{summary}".lower()
    return any(kw in blob for kw in RESOURCE_ESTIMATE_KEYWORDS)


def extract(title: str, summary: str) -> Optional[ResourceEstimateExtraction]:
    """Extract a resource-estimate signal from ``title + summary``.

    Returns ``None`` when the keyword gate matches but no resource
    estimate can be extracted — fail-conservative per CLAUDE.md §10.
    """
    if not matches(title, summary):
        return None

    blob = f"{title}\n{summary}"
    lower = blob.lower()

    is_rsa = any(m in lower for m in _RSA_2048_MENTIONS)
    is_aes = any(m in lower for m in _AES_128_MENTIONS)
    is_grover = any(m in lower for m in _GROVER_MENTIONS)

    # Shor-on-RSA-2048 channel: try qubits-to-factor or time-to-factor.
    if is_rsa:
        qubits = _extract_qubits(blob)
        minutes = _extract_minutes(blob)
        if qubits is None and minutes is None:
            return None
        shor_value, rationale = _map_shor(qubits, minutes)
        return ResourceEstimateExtraction(
            channel="shor",
            qubits_to_factor=qubits,
            time_to_factor_minutes=minutes,
            normalized_value=shor_value,
            rationale=rationale,
        )

    # AES/Grover sub-channel: fold with 0.3 sub-weight.
    if is_aes and is_grover:
        severity, rationale = _map_aes_grover(blob)
        return ResourceEstimateExtraction(
            channel="aes_grover",
            qubits_to_factor=None,
            time_to_factor_minutes=None,
            normalized_value=severity * AES_SUB_WEIGHT,
            rationale=f"AES/Grover sub-channel × {AES_SUB_WEIGHT}: {rationale}",
        )

    return None


# ---------------------------------------------------------------------------
# Numeric extraction helpers
# ---------------------------------------------------------------------------


def _extract_qubits(blob: str) -> Optional[int]:
    """Return the largest plausible qubit count appearing alongside
    a factoring/breaking/attacking verb or "qubits to factor"-style phrase.

    Plausibility window: ``[1_000, 1e10]`` — anything below 1k qubits is
    not a credible RSA-2048 attack claim and anything above 10⁹ is a
    typo.
    """
    candidates: list[int] = []
    for m in _QUBITS_TO_FACTOR_PATTERN.finditer(blob):
        raw_num = m.group(1).replace(",", "")
        suffix = (m.group(2) or "").lower()
        try:
            base = float(raw_num)
        except ValueError:
            # Explicitly handled: malformed decimal.
            continue
        multiplier = _MAGNITUDE_SUFFIXES.get(suffix, 1.0)
        n = int(round(base * multiplier))
        if 1_000 <= n <= 10_000_000_000:
            candidates.append(n)
    if not candidates:
        return None
    return max(candidates)


def _extract_minutes(blob: str) -> Optional[float]:
    """Return the smallest plausible factoring time, in minutes.

    Smallest because faster = worse (closer to Q-day). Accepts minutes,
    hours, and days.
    """
    candidates: list[float] = []
    for m in _MINUTES_PATTERN.finditer(blob):
        try:
            candidates.append(float(m.group(1)))
        except ValueError:
            continue
    for m in _HOURS_PATTERN.finditer(blob):
        try:
            candidates.append(float(m.group(1)) * 60.0)
        except ValueError:
            continue
    for m in _DAYS_PATTERN.finditer(blob):
        try:
            candidates.append(float(m.group(1)) * 60.0 * 24.0)
        except ValueError:
            continue
    if not candidates:
        return None
    return min(candidates)


# ---------------------------------------------------------------------------
# Anchor maps
# ---------------------------------------------------------------------------

# Qubits-to-factor anchors in log10 space:
#   20M qubits → 0.0  (Gidney-Ekera baseline)
#   1M qubits  → 0.5
#   100k qubits→ 1.0
_QUBIT_ANCHORS: tuple[tuple[float, float], ...] = (
    (math.log10(100_000.0), 1.0),
    (math.log10(1_000_000.0), 0.5),
    (math.log10(20_000_000.0), 0.0),
)

# Time-to-factor anchors in log10(minutes) space:
#   1 minute   → 1.0
#   60 minutes → 0.5
#   480 minutes → 0.0  (8h Gidney-Ekera)
_TIME_ANCHORS: tuple[tuple[float, float], ...] = (
    (math.log10(1.0), 1.0),
    (math.log10(60.0), 0.5),
    (math.log10(480.0), 0.0),
)


def _interp_descending(x: float, anchors: tuple[tuple[float, float], ...]) -> float:
    """Piecewise-linear interp; clamps below first anchor to its value
    and above last anchor to last value."""
    # Anchors here are ordered ascending in x (severity decreasing).
    if x <= anchors[0][0]:
        return anchors[0][1]
    if x >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x0 <= x <= x1:
            frac = (x - x0) / (x1 - x0)
            y = y0 + frac * (y1 - y0)
            return max(0.0, min(1.0, y))
    return 0.0  # unreachable given the clamps above


def _map_shor(
    qubits: Optional[int], minutes: Optional[float]
) -> tuple[float, str]:
    """Combine the qubits and/or time channels into one ``[0, 1]`` reading.

    When both are present, take the MAX (whichever is closer to Q-day).
    """
    qubit_value: Optional[float] = None
    time_value: Optional[float] = None
    rationales: list[str] = []

    if qubits is not None:
        qubit_value = _interp_descending(math.log10(float(qubits)), _QUBIT_ANCHORS)
        rationales.append(f"{qubits:,} qubits → {qubit_value:.2f}")

    if minutes is not None:
        time_value = _interp_descending(math.log10(float(minutes)), _TIME_ANCHORS)
        rationales.append(f"{minutes:g} min → {time_value:.2f}")

    if qubit_value is None and time_value is None:
        # Defensive: the caller already ensured at least one is set.
        return 0.0, "no extractable resource estimate"
    if qubit_value is None:
        return time_value or 0.0, "; ".join(rationales)
    if time_value is None:
        return qubit_value, "; ".join(rationales)
    return max(qubit_value, time_value), "; ".join(rationales)


def _map_aes_grover(blob: str) -> tuple[float, str]:
    """Score the AES/Grover sub-channel before the 0.3 fold-in.

    Conservative defaults: an article that just mentions "Grover on
    AES-128" with no quantitative improvement claim earns 0.5 (Grover
    is the theoretical baseline; the article saying so is informational
    but not new information).
    """
    lower = blob.lower()
    if "broken" in lower or "practical break" in lower:
        return 1.0, "claims AES-128 practical break"
    if (
        "improved" in lower
        or "constant factor" in lower
        or "t-count" in lower
        or "t-depth" in lower
        or "speedup" in lower
        or "speed-up" in lower
    ):
        return 0.5, "constant-factor / T-count improvement claim"
    # Bare Grover-on-AES-128 mention with no improvement framing.
    return 0.3, "Grover-on-AES-128 mention without quantitative improvement"

"""Axis 4 — Physical error-rate floor extractor (weight 0.15).

Tracks the best (smallest) reported physical two-qubit gate error rate.
The anchor map (METHODOLOGY.md §3 Axis 4) is log-linear in error rate:

- ``0.0`` ← 1 × 10⁻² (1% — NISQ baseline)
- ``1.0`` ← 1 × 10⁻⁵ (well below typical surface-code threshold)

The extractor accepts both **explicit error rates** (e.g. "0.5 % gate
error", "two-qubit error 5 × 10⁻³") and **fidelities** (e.g. "99.9 %
gate fidelity", "fidelity 0.9995"), converting the latter to an
implicit error ``1 − F``.

Per CLAUDE.md §10 (calibrated uncertainty), T1 / T2 coherence numbers
trigger the keyword gate but are NOT auto-converted to an axis value —
the gate-error / fidelity reading is the load-bearing claim and the
extractor falls back to ``None`` when only T1/T2 is cited.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from qday_clock.extract.keywords import ERROR_RATE_KEYWORDS

# Error-rate keyword fragment. The numeric can appear EITHER side of the
# keyword in real article text, so each pattern is checked in both
# orientations.
_ERR_KW = r"(?:gate\s+error|two[-\s]?qubit\s+(?:gate\s+)?error|2q\s+error|error\s+rate)"
_FID_KW = r"(?:gate\s+)?fidelity"

# Explicit error rate as a percent. Examples:
#   "two-qubit gate error 0.5 %"
#   "0.5 % two-qubit gate error"
_ERROR_PERCENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(_ERR_KW + r"[^0-9%]{0,40}?(\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*%[^0-9]{0,40}?" + _ERR_KW, re.IGNORECASE),
)

# Scientific-notation error rate ("gate error 5e-3", "1.2 × 10^-3 error").
_ERROR_SCIENTIFIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        _ERR_KW
        + r"[^0-9eE×x10]{0,40}?(\d+(?:\.\d+)?)\s*(?:e|[eE]|×\s*10\^?|x\s*10\^?)\s*[-−]\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:e|[eE]|×\s*10\^?|x\s*10\^?)\s*[-−]\s*(\d+)[^0-9]{0,40}?" + _ERR_KW,
        re.IGNORECASE,
    ),
)

# Decimal-form error rate ("gate error 0.001", "0.001 gate error").
_ERROR_DECIMAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(_ERR_KW + r"[^0-9]{0,40}?(0\.\d{2,6})\b", re.IGNORECASE),
    re.compile(r"(0\.\d{2,6})\b[^0-9]{0,40}?" + _ERR_KW, re.IGNORECASE),
)

# Fidelity-percent ("gate fidelity 99.9 %", "99.9 % gate fidelity").
_FIDELITY_PERCENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(_FID_KW + r"[^0-9]{0,40}?(\d{2}(?:\.\d+)?)\s*%", re.IGNORECASE),
    re.compile(r"(\d{2}(?:\.\d+)?)\s*%[^0-9]{0,40}?" + _FID_KW, re.IGNORECASE),
)

# Fidelity-decimal ("fidelity 0.9999", "0.9999 fidelity").
_FIDELITY_DECIMAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(_FID_KW + r"[^0-9]{0,40}?(0\.\d{2,6})\b", re.IGNORECASE),
    re.compile(r"(0\.\d{2,6})\b[^0-9]{0,40}?" + _FID_KW, re.IGNORECASE),
)


@dataclass(frozen=True)
class ErrorRateExtraction:
    """Result of running the axis-4 extractor on an article."""

    error_rate: float
    normalized_value: float
    rationale: str
    source_kind: str  # "explicit_error" or "fidelity_conversion"


def matches(title: str, summary: str) -> bool:
    """Return True if the article's text contains any axis-4 keyword."""
    blob = f"{title}\n{summary}".lower()
    return any(kw in blob for kw in ERROR_RATE_KEYWORDS)


def extract(title: str, summary: str) -> ErrorRateExtraction | None:
    """Extract an error-rate signal from ``title + summary``.

    Strategy:
      1. Find every plausible error rate (explicit or via fidelity
         conversion).
      2. Pick the SMALLEST plausible error — best reported result.
      3. Map to ``[0, 1]`` log-linearly between 1e-2 (0.0) and 1e-5 (1.0).

    Returns ``None`` when keyword gate fires but no plausible numeric
    error rate is extracted (e.g. T1/T2-only articles).
    """
    if not matches(title, summary):
        return None

    blob = f"{title}\n{summary}"

    explicit = _extract_explicit_errors(blob)
    from_fid = _extract_errors_from_fidelity(blob)

    candidates: list[tuple[float, str]] = []
    candidates.extend((e, "explicit_error") for e in explicit)
    candidates.extend((e, "fidelity_conversion") for e in from_fid)

    if not candidates:
        return None

    # Best (smallest) error wins. Tie-break (within ~1e-9 relative): prefer
    # explicit reading over fidelity-derived reading. The tolerance handles
    # the fact that "fidelity 99.9 %" parses to 0.0009999... ≠ exactly 1e-3.
    def _sort_key(pair: tuple[float, str]) -> tuple[float, int]:
        # Bucket values so near-ties collapse to the same primary key.
        bucketed = round(pair[0], 9)
        return (bucketed, 0 if pair[1] == "explicit_error" else 1)

    candidates.sort(key=_sort_key)
    error_rate, source_kind = candidates[0]
    normalized, rationale = _map_to_unit(error_rate)
    return ErrorRateExtraction(
        error_rate=error_rate,
        normalized_value=normalized,
        rationale=rationale,
        source_kind=source_kind,
    )


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


# Plausibility window for a physical 2-qubit gate error: [1e-7, 0.05].
# The upper bound is set below 0.5 so that a "50 % fidelity" reading
# (implausibly low for an axis-4 claim, and likely a fidelity figure
# being misread as an explicit error via reverse-orientation regex)
# is rejected rather than recorded as a 50 % gate error.
_ERROR_MIN = 1e-7
_ERROR_MAX = 0.05


def _record_if_plausible(value: float, out: list[float]) -> None:
    if _ERROR_MIN <= value <= _ERROR_MAX:
        out.append(value)


def _extract_explicit_errors(blob: str) -> list[float]:
    """Find explicit error rates in the blob."""
    out: list[float] = []

    for pat in _ERROR_PERCENT_PATTERNS:
        for m in pat.finditer(blob):
            try:
                pct = float(m.group(1))
            except ValueError:
                continue
            _record_if_plausible(pct / 100.0, out)

    for pat in _ERROR_SCIENTIFIC_PATTERNS:
        for m in pat.finditer(blob):
            try:
                mantissa = float(m.group(1))
                exponent = int(m.group(2))
            except ValueError:
                continue
            _record_if_plausible(mantissa * (10**-exponent), out)

    for pat in _ERROR_DECIMAL_PATTERNS:
        for m in pat.finditer(blob):
            try:
                val = float(m.group(1))
            except ValueError:
                continue
            _record_if_plausible(val, out)

    return out


def _extract_errors_from_fidelity(blob: str) -> list[float]:
    """Find fidelities, convert each to an implied error ``1 - F``."""
    out: list[float] = []

    for pat in _FIDELITY_PERCENT_PATTERNS:
        for m in pat.finditer(blob):
            try:
                pct = float(m.group(1))
            except ValueError:
                continue
            # Only credit fidelity >= 90 %; anything lower is implausible
            # for the kind of demo this axis tracks.
            if 90.0 <= pct <= 100.0:
                implied_error = 1.0 - (pct / 100.0)
                _record_if_plausible(max(implied_error, 1e-9), out)

    for pat in _FIDELITY_DECIMAL_PATTERNS:
        for m in pat.finditer(blob):
            try:
                val = float(m.group(1))
            except ValueError:
                continue
            if 0.9 <= val < 1.0:
                implied_error = 1.0 - val
                _record_if_plausible(max(implied_error, 1e-9), out)

    return out


# ---------------------------------------------------------------------------
# Anchor map
# ---------------------------------------------------------------------------


def _map_to_unit(error_rate: float) -> tuple[float, str]:
    """Log-linear interp: 1e-2 → 0.0, 1e-5 → 1.0."""
    if error_rate >= 1e-2:
        return 0.0, f"gate error {error_rate:.2e} ≥ NISQ baseline 1e-2"
    if error_rate <= 1e-5:
        return 1.0, f"gate error {error_rate:.2e} ≤ floor 1e-5"

    log_e = math.log10(error_rate)  # in (-5, -2)
    # y = (-2 - log_e) / (-2 - (-5)) = (-2 - log_e) / 3
    y = (-2.0 - log_e) / 3.0
    y = max(0.0, min(1.0, y))
    return y, f"gate error {error_rate:.2e} (log-interp)"

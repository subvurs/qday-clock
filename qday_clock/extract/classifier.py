"""Manifest → Signal classifier.

Takes a verified :class:`CuratorManifest` and routes each article
through every per-axis extractor that is live for the current Q-day
Clock version. v0.2.0 wires all five axes:

* Axis 1 — logical qubit progress (``axis_logical_qubits``)
* Axis 2 — physical qubit scaling (``axis_physical_scaling``)
* Axis 3 — resource estimate / AES+Grover (``axis_resource_estimate``)
* Axis 4 — error rate floor (``axis_error_rate``)
* Axis 5 — PQC migration friction, inverse (``axis_pqc_migration``)

Design choices (per CLAUDE.md §3 evidence-class and §10 calibrated
uncertainty):

* An article that yields no extractable numeric for *any* active axis
  is silently dropped from that axis (fail-conservative). The same
  article may still contribute to other axes — multi-axis articles
  are normal (e.g. a hardware demo cites both a qubit count and a
  gate error).
* Evidence class is derived from Curator topic tags. The mapping is
  deliberately conservative: only ``hardware`` topic earns
  ``EvidenceClass.HARDWARE``; everything else degrades to ``THEORY``
  unless explicitly policy-tagged. Mark can tighten this in a later
  release when per-article evidence-class extraction lands in Curator.
* Signal IDs are content-hashed (post_id + axis) so the same article
  re-exported on different days produces the same signal id
  (idempotent refreshes).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from qday_clock.core.schemas import (
    AxisId,
    CuratorArticleRef,
    CuratorManifest,
    EvidenceClass,
    Signal,
)
from qday_clock.extract import (
    axis_error_rate,
    axis_logical_qubits,
    axis_physical_scaling,
    axis_pqc_migration,
    axis_resource_estimate,
)

# Topic-tag → evidence-class mapping. Lookups are case-insensitive
# against the Curator-side ContentTopic enum string values.
_TOPIC_TO_EVIDENCE: dict[str, EvidenceClass] = {
    "hardware": EvidenceClass.HARDWARE,
    "algorithms": EvidenceClass.THEORY,
    "error_correction": EvidenceClass.THEORY,
    "cryptography": EvidenceClass.POLICY,
    "policy": EvidenceClass.POLICY,
    "simulation": EvidenceClass.SIMULATION,
    "research": EvidenceClass.THEORY,
}


def _classify_evidence(article: CuratorArticleRef) -> EvidenceClass:
    """Pick the strongest-evidence class implied by an article's topics.

    Priority order matters: an article tagged both ``hardware`` and
    ``research`` is treated as ``HARDWARE`` because hardware demos
    carry more weight than research-class context. This priority
    matches METHODOLOGY.md §4 weight intent (hardware > theory >
    policy > simulation, with HARDWARE the only tag that's actually
    diagnostic of CRQC progress).
    """
    topics = {t.lower() for t in article.topics}
    if "hardware" in topics:
        return EvidenceClass.HARDWARE
    for key in ("policy", "cryptography", "error_correction", "algorithms", "simulation", "research"):
        if key in topics:
            return _TOPIC_TO_EVIDENCE[key]
    # Default fail-conservative bucket — gate stack treats THEORY less
    # aggressively than HARDWARE, which is the right side to err on.
    return EvidenceClass.THEORY


def _signal_id(article: CuratorArticleRef, axis: AxisId) -> str:
    """Stable opaque id derived from post_id + axis."""
    h = hashlib.sha256(f"{article.post_id}|{axis.value}".encode("utf-8")).hexdigest()
    return f"sig_{h[:16]}"


def _build_signal(
    article: CuratorArticleRef,
    axis: AxisId,
    raw_value: float,
    normalized_value: float,
    observed_at: datetime,
) -> Signal:
    return Signal(
        signal_id=_signal_id(article, axis),
        axis=axis,
        title=article.title,
        summary=article.summary,
        source=article.source,
        url=article.url,
        published_at=article.published_at,
        observed_at=observed_at,
        evidence_class=_classify_evidence(article),
        raw_value=raw_value,
        normalized_value=normalized_value,
        confidence=article.relevance_score,
    )


# ---------------------------------------------------------------------------
# Per-axis routers
# ---------------------------------------------------------------------------


def classify_article_axis1(
    article: CuratorArticleRef,
    *,
    observed_at: datetime,
) -> Signal | None:
    """Route one article through the axis-1 (logical qubits) extractor.

    Returns ``None`` when the article matches an axis-1 keyword but no
    extractable numeric is present (deliberate fail-conservative —
    CLAUDE.md §10).
    """
    extraction = axis_logical_qubits.extract(article.title, article.summary)
    if extraction is None:
        return None

    # Prefer distance for raw_value when available, else n_logical.
    raw_value: float
    if extraction.distance is not None:
        raw_value = float(extraction.distance)
    elif extraction.n_logical is not None:
        raw_value = float(extraction.n_logical)
    else:
        # Defensive: extract() promises distance OR n_logical when it
        # returns non-None. If neither is present, that's an upstream
        # bug — surface it rather than silently dropping the article.
        return None

    return _build_signal(
        article,
        AxisId.LOGICAL_QUBITS,
        raw_value=raw_value,
        normalized_value=extraction.normalized_value,
        observed_at=observed_at,
    )


def classify_article_axis2(
    article: CuratorArticleRef,
    *,
    observed_at: datetime,
) -> Signal | None:
    """Route one article through the axis-2 (physical scaling) extractor."""
    extraction = axis_physical_scaling.extract(article.title, article.summary)
    if extraction is None:
        return None
    return _build_signal(
        article,
        AxisId.PHYSICAL_SCALING,
        raw_value=float(extraction.n_qubits),
        normalized_value=extraction.normalized_value,
        observed_at=observed_at,
    )


def classify_article_axis3(
    article: CuratorArticleRef,
    *,
    observed_at: datetime,
) -> Signal | None:
    """Route one article through the axis-3 (resource estimate) extractor.

    Raw value preference: qubits-to-factor if present, else
    time-to-factor minutes, else fall back to the normalized severity
    (AES/Grover sub-channel case — no qubit/time numeric exists).
    """
    extraction = axis_resource_estimate.extract(article.title, article.summary)
    if extraction is None:
        return None

    if extraction.qubits_to_factor is not None:
        raw_value = float(extraction.qubits_to_factor)
    elif extraction.time_to_factor_minutes is not None:
        raw_value = float(extraction.time_to_factor_minutes)
    else:
        # AES/Grover sub-channel case: no qubit or time numeric. Use
        # the normalized severity (already folded by AES_SUB_WEIGHT)
        # as the raw value so the signal still carries provenance.
        raw_value = float(extraction.normalized_value)

    return _build_signal(
        article,
        AxisId.RESOURCE_ESTIMATE,
        raw_value=raw_value,
        normalized_value=extraction.normalized_value,
        observed_at=observed_at,
    )


def classify_article_axis4(
    article: CuratorArticleRef,
    *,
    observed_at: datetime,
) -> Signal | None:
    """Route one article through the axis-4 (error rate floor) extractor."""
    extraction = axis_error_rate.extract(article.title, article.summary)
    if extraction is None:
        return None
    return _build_signal(
        article,
        AxisId.ERROR_RATE,
        raw_value=float(extraction.error_rate),
        normalized_value=extraction.normalized_value,
        observed_at=observed_at,
    )


def classify_article_axis5(
    article: CuratorArticleRef,
    *,
    observed_at: datetime,
) -> Signal | None:
    """Route one article through the axis-5 (PQC migration) extractor.

    Unlike axes 1-4, axis 5 returns a non-None reading on every
    keyword-gate match (even bare mentions floor at 0.1). The clock
    combination layer subtracts axis_5 (inverse polarity); raw_value
    here is the severity tier's float magnitude.
    """
    extraction = axis_pqc_migration.extract(article.title, article.summary)
    if extraction is None:
        return None
    return _build_signal(
        article,
        AxisId.PQC_MIGRATION,
        raw_value=float(extraction.normalized_value),
        normalized_value=extraction.normalized_value,
        observed_at=observed_at,
    )


# ---------------------------------------------------------------------------
# Manifest-level routing
# ---------------------------------------------------------------------------


_PER_ARTICLE_ROUTERS = (
    classify_article_axis1,
    classify_article_axis2,
    classify_article_axis3,
    classify_article_axis4,
    classify_article_axis5,
)


def classify_manifest(
    manifest: CuratorManifest,
    *,
    observed_at: datetime | None = None,
) -> list[Signal]:
    """Route every article in ``manifest`` through every live axis extractor.

    v0.2.0: all five axes wired. One article may yield multiple
    signals (different axes); we do not break after the first hit.

    Parameters
    ----------
    manifest
        Verified :class:`CuratorManifest` from
        :func:`qday_clock.ingest.curator_client.fetch_manifest`.
    observed_at
        UTC timestamp recorded on each Signal. Defaults to
        ``datetime.now(tz=timezone.utc)``. Tests pin this to a fixed
        value for golden-replay determinism.
    """
    if observed_at is None:
        observed_at = datetime.now(tz=timezone.utc)

    signals: list[Signal] = []
    for article in manifest.articles:
        for router in _PER_ARTICLE_ROUTERS:
            sig = router(article, observed_at=observed_at)
            if sig is not None:
                signals.append(sig)
    return signals

"""Manifest → Signal classifier tests.

Covers:

* axis-1 routing through a synthetic manifest
* evidence-class mapping for each topic priority
* idempotent signal_id derivation
* fail-conservative behavior when no extractor matches
* full end-to-end: manifest → signals → ClockState
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from qday_clock.core.schemas import (
    AxisId,
    CuratorArticleRef,
    CuratorManifest,
    EvidenceClass,
)
from qday_clock.extract.classifier import (
    _classify_evidence,
    _signal_id,
    classify_article_axis1,
    classify_article_axis2,
    classify_article_axis3,
    classify_article_axis4,
    classify_article_axis5,
    classify_manifest,
)


def _article(
    *,
    post_id: str = "p1",
    title: str = "Distance-7 surface code below threshold",
    summary: str = "We demonstrate a small fault-tolerant logical qubit.",
    topics: list[str] | None = None,
    relevance: float = 0.8,
    published: datetime | None = None,
) -> CuratorArticleRef:
    return CuratorArticleRef(
        post_id=post_id,
        title=title,
        url=f"https://example.org/{post_id}",
        source="Example Lab",
        topics=topics or ["hardware"],
        published_at=published or datetime(2026, 5, 15, tzinfo=timezone.utc),
        relevance_score=relevance,
        summary=summary,
    )


_FIXED_OBS = datetime(2026, 6, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Single-article routing
# ---------------------------------------------------------------------------


def test_classify_article_axis1_extracts_distance_7() -> None:
    sig = classify_article_axis1(_article(), observed_at=_FIXED_OBS)
    assert sig is not None
    assert sig.axis == AxisId.LOGICAL_QUBITS
    assert sig.normalized_value == 0.5
    assert sig.raw_value == 7.0
    assert sig.evidence_class == EvidenceClass.HARDWARE


def test_classify_article_axis1_returns_none_for_unrelated_text() -> None:
    sig = classify_article_axis1(
        _article(
            title="Quantum startup raises Series B",
            summary="Funding round announcement; no technical details.",
        ),
        observed_at=_FIXED_OBS,
    )
    assert sig is None


def test_classify_article_axis1_returns_none_when_keyword_but_no_number() -> None:
    """Fail-conservative: keyword hit but no extractable numeric → None."""
    sig = classify_article_axis1(
        _article(
            title="Progress on logical qubit error correction",
            summary="A general discussion of fault tolerance trends.",
        ),
        observed_at=_FIXED_OBS,
    )
    assert sig is None


# ---------------------------------------------------------------------------
# Evidence-class mapping (one assertion per priority slot)
# ---------------------------------------------------------------------------


def test_evidence_hardware_wins_over_research() -> None:
    a = _article(topics=["research", "hardware"])
    assert _classify_evidence(a) == EvidenceClass.HARDWARE


def test_evidence_policy_when_no_hardware() -> None:
    a = _article(topics=["policy", "research"])
    assert _classify_evidence(a) == EvidenceClass.POLICY


def test_evidence_cryptography_maps_to_policy() -> None:
    a = _article(topics=["cryptography"])
    assert _classify_evidence(a) == EvidenceClass.POLICY


def test_evidence_error_correction_maps_to_theory() -> None:
    a = _article(topics=["error_correction"])
    assert _classify_evidence(a) == EvidenceClass.THEORY


def test_evidence_algorithms_maps_to_theory() -> None:
    a = _article(topics=["algorithms"])
    assert _classify_evidence(a) == EvidenceClass.THEORY


def test_evidence_simulation_maps_to_simulation() -> None:
    a = _article(topics=["simulation"])
    assert _classify_evidence(a) == EvidenceClass.SIMULATION


def test_evidence_unknown_topic_defaults_to_theory() -> None:
    a = _article(topics=["machine_learning"])
    assert _classify_evidence(a) == EvidenceClass.THEORY


# ---------------------------------------------------------------------------
# signal_id stability
# ---------------------------------------------------------------------------


def test_signal_id_is_deterministic() -> None:
    a = _article(post_id="abc")
    s1 = _signal_id(a, AxisId.LOGICAL_QUBITS)
    s2 = _signal_id(a, AxisId.LOGICAL_QUBITS)
    assert s1 == s2
    assert s1.startswith("sig_")


def test_signal_id_differs_across_axes() -> None:
    a = _article(post_id="abc")
    assert _signal_id(a, AxisId.LOGICAL_QUBITS) != _signal_id(a, AxisId.PHYSICAL_SCALING)


# ---------------------------------------------------------------------------
# Manifest-level routing
# ---------------------------------------------------------------------------


def _manifest(*articles: CuratorArticleRef) -> CuratorManifest:
    return CuratorManifest(
        version="1.0",
        generated_at=_FIXED_OBS,
        curator_commit="deadbeef",
        articles=list(articles),
        db_row_counts={"raw_articles": len(articles)},
    )


def test_classify_manifest_extracts_only_articles_with_signals() -> None:
    m = _manifest(
        _article(post_id="hit", title="Distance-11 surface code memory"),
        _article(
            post_id="miss",
            title="Quantum startup funding",
            summary="Series B announced.",
        ),
    )
    signals = classify_manifest(m, observed_at=_FIXED_OBS)
    assert len(signals) == 1
    assert signals[0].title.startswith("Distance-11")


def test_classify_manifest_observed_at_default_uses_now(monkeypatch) -> None:
    """When observed_at is omitted, it defaults to current UTC time."""
    m = _manifest(_article(title="Distance-7 surface code"))
    signals = classify_manifest(m)
    assert len(signals) == 1
    # Just confirm tzinfo is UTC; we don't pin the absolute time here.
    assert signals[0].observed_at.tzinfo == timezone.utc


def test_classify_manifest_preserves_relevance_as_confidence() -> None:
    m = _manifest(
        _article(title="Distance-7 surface code memory", relevance=0.42),
    )
    signals = classify_manifest(m, observed_at=_FIXED_OBS)
    assert signals[0].confidence == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# End-to-end: manifest → classifier → clock pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline_from_manifest_to_clock_state() -> None:
    """A synthetic manifest with three hardware demos drives a non-zero
    axis-1 reading and a deterministic clock score."""
    from qday_clock.score.clock import compute_clock_state

    m = _manifest(
        _article(post_id="a", title="Distance-7 surface code below threshold"),
        _article(post_id="b", title="Distance-11 surface code memory"),
        _article(post_id="c", title="12 logical qubits below threshold demonstration"),
    )
    signals = classify_manifest(m, observed_at=_FIXED_OBS)
    assert len(signals) == 3
    state = compute_clock_state(signals)
    axis1 = state.axes["logical_qubits"]
    assert axis1.n_independent_sources == 1  # all from "Example Lab"
    assert axis1.reading > 0.5
    assert 0.0 <= state.clock_score <= 1.0


# ---------------------------------------------------------------------------
# Axes 2-5 routing (v0.2)
# ---------------------------------------------------------------------------


def test_classify_article_axis2_extracts_physical_qubits() -> None:
    sig = classify_article_axis2(
        _article(
            post_id="ibm_condor",
            title="IBM Condor 1,121 qubit processor announced",
            summary="Largest physical-qubit milestone to date.",
        ),
        observed_at=_FIXED_OBS,
    )
    assert sig is not None
    assert sig.axis == AxisId.PHYSICAL_SCALING
    assert sig.raw_value == 1_121.0


def test_classify_article_axis3_shor_channel() -> None:
    sig = classify_article_axis3(
        _article(
            post_id="ge2019",
            title="Gidney-Ekera RSA-2048 estimate: 20 million qubits",
            summary="Resource estimate baseline.",
        ),
        observed_at=_FIXED_OBS,
    )
    assert sig is not None
    assert sig.axis == AxisId.RESOURCE_ESTIMATE
    assert sig.raw_value == 20_000_000.0
    assert sig.normalized_value == pytest.approx(0.0)


def test_classify_article_axis3_aes_subchannel() -> None:
    """AES/Grover sub-channel produces no qubit/time numeric — raw
    falls back to the (sub-weighted) normalized value."""
    sig = classify_article_axis3(
        _article(
            post_id="aes1",
            title="AES-128 practical break demonstrated via Grover",
            summary="",
        ),
        observed_at=_FIXED_OBS,
    )
    assert sig is not None
    assert sig.axis == AxisId.RESOURCE_ESTIMATE
    # AES_SUB_WEIGHT = 0.3 ⇒ normalized = 1.0 × 0.3 = 0.3.
    assert sig.normalized_value == pytest.approx(0.3)
    assert sig.raw_value == pytest.approx(0.3)


def test_classify_article_axis4_extracts_error_rate() -> None:
    sig = classify_article_axis4(
        _article(
            post_id="err1",
            title="Two-qubit gate error 0.1% demonstrated",
            summary="Calibration data attached.",
        ),
        observed_at=_FIXED_OBS,
    )
    assert sig is not None
    assert sig.axis == AxisId.ERROR_RATE
    assert sig.raw_value == pytest.approx(1e-3)
    assert sig.normalized_value == pytest.approx(1.0 / 3.0, abs=1e-6)


def test_classify_article_axis5_extracts_pqc_pilot() -> None:
    sig = classify_article_axis5(
        _article(
            post_id="cf_pilot",
            title="Cloudflare piloting ML-KEM in TLS handshake",
            summary="Initial customer rollout this quarter.",
            topics=["policy"],
        ),
        observed_at=_FIXED_OBS,
    )
    assert sig is not None
    assert sig.axis == AxisId.PQC_MIGRATION
    assert sig.normalized_value == pytest.approx(0.5)
    assert sig.evidence_class == EvidenceClass.POLICY


def test_classify_article_axis5_bare_mention_floors_at_one_tenth() -> None:
    """Axis-5 is the only axis that always produces a reading once the
    keyword gate fires — bare mentions floor at 0.1, not None."""
    sig = classify_article_axis5(
        _article(
            post_id="bare1",
            title="Researchers analyze Kyber side-channel attack surface",
            summary="No deployment claim.",
            topics=["cryptography"],
        ),
        observed_at=_FIXED_OBS,
    )
    assert sig is not None
    assert sig.normalized_value == pytest.approx(0.1)


def test_classify_manifest_emits_multi_axis_signals_per_article() -> None:
    """A single article may carry signal for multiple axes."""
    m = _manifest(
        _article(
            post_id="multi1",
            title="IBM Condor 1,121 qubit processor with 0.5% two-qubit gate error",
            summary="Hardware and calibration in one release.",
            topics=["hardware"],
        ),
    )
    signals = classify_manifest(m, observed_at=_FIXED_OBS)
    axes = {s.axis for s in signals}
    assert AxisId.PHYSICAL_SCALING in axes
    assert AxisId.ERROR_RATE in axes


def test_classify_manifest_drops_articles_with_no_axis_hit() -> None:
    """An article hitting no extractor at all yields no signals."""
    m = _manifest(
        _article(
            post_id="empty",
            title="Quarterly earnings beat expectations",
            summary="Generic finance news.",
        )
    )
    assert classify_manifest(m, observed_at=_FIXED_OBS) == []


def test_classify_manifest_axis5_polarity_recorded_on_signal() -> None:
    """Even though the clock combination layer subtracts axis_5, the
    signal itself carries a *positive* normalized value (the polarity
    is enforced downstream, not at extraction time)."""
    m = _manifest(
        _article(
            post_id="pqc_default",
            title="ML-KEM now default in Chrome stable",
            summary="Hybrid TLS rollout complete for desktop browsers.",
            topics=["policy"],
        )
    )
    signals = classify_manifest(m, observed_at=_FIXED_OBS)
    pqc_sigs = [s for s in signals if s.axis == AxisId.PQC_MIGRATION]
    assert len(pqc_sigs) == 1
    assert pqc_sigs[0].normalized_value > 0.5

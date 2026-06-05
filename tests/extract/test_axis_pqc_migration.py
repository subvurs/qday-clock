"""Axis-5 (PQC migration friction, inverse) extractor unit tests."""

from __future__ import annotations

import pytest

from qday_clock.extract.axis_pqc_migration import extract, matches


# ---------------------------------------------------------------------------
# Keyword gate
# ---------------------------------------------------------------------------


def test_matches_on_keyword() -> None:
    assert matches("NIST publishes ML-KEM FIPS 203", "")
    assert matches("", "Cloudflare deploys Kyber in TLS handshake")
    assert not matches("Earnings call commentary", "no PQ content")


def test_no_keyword_returns_none() -> None:
    assert extract("Generic tech roundup", "no quantum or crypto content") is None


# ---------------------------------------------------------------------------
# Severity tiers
# ---------------------------------------------------------------------------


def test_mandate_anchors_at_one() -> None:
    res = extract(
        "Federal agencies report CNSA 2.0 mandatory deployment achieved", ""
    )
    assert res is not None
    assert res.severity == "mandate"
    assert res.normalized_value == pytest.approx(1.0)


def test_broad_deployment_anchors_at_seven_tenths() -> None:
    res = extract("ML-KEM now default in Chrome stable", "")
    assert res is not None
    assert res.severity == "broad"
    assert res.normalized_value == pytest.approx(0.7)


def test_pilot_anchors_at_half() -> None:
    res = extract("Cloudflare piloting Kyber across edge", "")
    assert res is not None
    assert res.severity == "pilot"
    assert res.normalized_value == pytest.approx(0.5)


def test_standardization_anchors_at_three_tenths() -> None:
    res = extract("NIST publishes FIPS 203 (ML-KEM standard)", "")
    assert res is not None
    assert res.severity == "standardization"
    assert res.normalized_value == pytest.approx(0.3)


def test_bare_mention_floors_at_one_tenth() -> None:
    """A bare 'Kyber' mention with no adoption-action phrase still
    registers — at the informational floor of 0.1."""
    res = extract("Researchers discuss Kyber implementation details", "")
    assert res is not None
    assert res.severity == "mention"
    assert res.normalized_value == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Tier precedence — highest matched tier wins
# ---------------------------------------------------------------------------


def test_mandate_beats_broad_deployment() -> None:
    res = extract(
        "CNSA 2.0 mandatory deployment achieved across federal agencies",
        "Already rolled out to all branches",
    )
    assert res is not None
    assert res.severity == "mandate"
    assert res.normalized_value == pytest.approx(1.0)


def test_broad_beats_pilot() -> None:
    res = extract(
        "ML-KEM widely deployed across cloud providers",
        "Initial pilot expanded into broad rollout",
    )
    assert res is not None
    assert res.severity == "broad"


def test_pilot_beats_standardization() -> None:
    res = extract(
        "Cloudflare piloting ML-KEM in TLS",
        "Built on the FIPS 203 standard",
    )
    assert res is not None
    assert res.severity == "pilot"


def test_standardization_beats_mention() -> None:
    res = extract(
        "Kyber selected for standardization by NIST",
        "Dilithium and SPHINCS+ also finalized",
    )
    assert res is not None
    assert res.severity == "standardization"


# ---------------------------------------------------------------------------
# Monotonicity sanity
# ---------------------------------------------------------------------------


def test_severity_tiers_monotone() -> None:
    """Each higher tier must produce a strictly higher reading."""
    mention = extract("Kyber discussion", "")
    standard = extract("FIPS 203 published", "")
    pilot = extract("Pilot deployment of ML-KEM at Google", "")
    broad = extract("Widely deployed PQC migration", "")
    mandate = extract("Mandatory deployment of CNSA 2.0", "")
    assert all(r is not None for r in [mention, standard, pilot, broad, mandate])
    assert (
        mention.normalized_value  # type: ignore[union-attr]
        < standard.normalized_value  # type: ignore[union-attr]
        < pilot.normalized_value  # type: ignore[union-attr]
        < broad.normalized_value  # type: ignore[union-attr]
        < mandate.normalized_value  # type: ignore[union-attr]
    )


# ---------------------------------------------------------------------------
# Rationale string
# ---------------------------------------------------------------------------


def test_rationale_present_and_describes_match() -> None:
    res = extract("FIPS 203 published", "")
    assert res is not None
    assert res.rationale
    assert "fips 203" in res.rationale.lower() or "standardization" in res.rationale.lower()


# ---------------------------------------------------------------------------
# Keyword coverage spot-checks
# ---------------------------------------------------------------------------


def test_keyword_coverage_matches() -> None:
    """Each public PQC keyword should make ``matches`` return True."""
    for kw in [
        "Kyber",
        "Dilithium",
        "SPHINCS+",
        "ML-KEM",
        "ML-DSA",
        "CRYSTALS",
        "PQC migration",
        "post-quantum migration",
        "crypto-agility",
        "hybrid TLS",
        "FIPS 203",
        "FIPS 204",
        "FIPS 205",
        "CNSA 2.0",
    ]:
        assert matches(kw, ""), f"keyword should match: {kw!r}"

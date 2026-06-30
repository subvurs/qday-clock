"""Axis 5 — PQC migration friction (inverse axis, weight 0.15).

This axis is the only INVERSE axis on the clock: a higher reading
means MORE post-quantum cryptography (PQC) has been deployed in the
wild, which in turn moves the clock hand AWAY from Q-day. The clock
combination layer subtracts ``axis_5`` per plan §C:

    clock_score = sum_{i in 1..4} w_i · a_i  −  0.5 · a_5

So the extractor still returns a value in ``[0, 1]`` where ``0`` means
no PQC adoption signal and ``1`` means a mandatory-deployment-met
signal. The *defensive* polarity is enforced downstream, not here.

Anchor rubric (METHODOLOGY.md §3 Axis 5):

- ``0.0`` ← keyword hit but no adoption/policy action
- ``0.3`` ← standardization announcement (e.g. FIPS 203 published)
- ``0.5`` ← pilot / partial deployment (e.g. "Cloudflare piloting
  ML-KEM in TLS 1.3")
- ``0.7`` ← broad deployment ("default in Chrome", "rolled out across
  Apple platforms", "ubiquitous hybrid TLS handshake")
- ``1.0`` ← mandate met / deadline cleared (e.g. "CNSA 2.0 mandatory
  deployment achieved")

Per CLAUDE.md §10 (calibrated uncertainty): the extractor is
fail-conservative. When a PQC keyword hits but no adoption-strength
phrase can be matched, the bare-mention floor of 0.1 fires (a
mention is information; it is not deployment).
"""

from __future__ import annotations

from dataclasses import dataclass

from qday_clock.extract.keywords import PQC_MIGRATION_KEYWORDS, keyword_hit

# Severity-tier keyword sets. Highest tier matched wins. All matched
# against the lower-cased blob, so entries are lower-cased here.

_MANDATE_KEYWORDS: tuple[str, ...] = (
    "mandatory deployment",
    "deadline met",
    "deadline cleared",
    "fully migrated",
    "universally deployed",
    "cnsa 2.0 met",
)

_BROAD_DEPLOYMENT_KEYWORDS: tuple[str, ...] = (
    "default in chrome",
    "default in firefox",
    "default in safari",
    "default in edge",
    "rolled out",
    "wide deployment",
    "widely deployed",
    "ubiquitous",
    "production deployment",
    "in production",
    "shipped to all",
    "general availability",
    "ga release",
    "ga rollout",
)

_PILOT_KEYWORDS: tuple[str, ...] = (
    "pilot",
    "piloting",
    "trial",
    "preview",
    "beta",
    "partial deployment",
    "early adopter",
    "experimental support",
    "testing in",
    "deployed by",
    "now supports",
    "added support for",
    "enabling",
)

_STANDARDIZATION_KEYWORDS: tuple[str, ...] = (
    "fips 203",
    "fips 204",
    "fips 205",
    "ml-kem finalized",
    "ml-dsa finalized",
    "standard published",
    "standardized",
    "draft standard",
    "selected for standardization",
    "nist selects",
    "cnsa 2.0",
)


@dataclass(frozen=True)
class PQCMigrationExtraction:
    """Result of running the axis-5 extractor on an article."""

    severity: str  # "mention" | "standardization" | "pilot" | "broad" | "mandate"
    normalized_value: float
    rationale: str


def matches(title: str, summary: str) -> bool:
    """Return True if the article's text contains any axis-5 keyword."""
    blob = f"{title}\n{summary}".lower()
    return keyword_hit(blob, PQC_MIGRATION_KEYWORDS)


def extract(title: str, summary: str) -> PQCMigrationExtraction | None:
    """Extract a PQC-adoption signal from ``title + summary``.

    Strategy (highest-tier-wins):
      1. mandate / deadline-met language → 1.0
      2. broad deployment language → 0.7
      3. pilot / preview / partial-deployment language → 0.5
      4. standardization / FIPS-published language → 0.3
      5. bare keyword mention without action verb → 0.1

    Returns ``None`` only when the keyword gate itself does not fire.
    Unlike axes 1-4, axis 5 always produces *some* reading once a PQC
    keyword is present, because a bare mention is still evidence that
    PQC is on the policy radar.
    """
    if not matches(title, summary):
        return None

    blob = f"{title}\n{summary}".lower()

    if _any_match(blob, _MANDATE_KEYWORDS):
        return PQCMigrationExtraction(
            severity="mandate",
            normalized_value=1.0,
            rationale=f"mandate/deadline-met phrase: {_first_hit(blob, _MANDATE_KEYWORDS)}",
        )

    if _any_match(blob, _BROAD_DEPLOYMENT_KEYWORDS):
        return PQCMigrationExtraction(
            severity="broad",
            normalized_value=0.7,
            rationale=f"broad-deployment phrase: {_first_hit(blob, _BROAD_DEPLOYMENT_KEYWORDS)}",
        )

    if _any_match(blob, _PILOT_KEYWORDS):
        return PQCMigrationExtraction(
            severity="pilot",
            normalized_value=0.5,
            rationale=f"pilot/partial-deployment phrase: {_first_hit(blob, _PILOT_KEYWORDS)}",
        )

    if _any_match(blob, _STANDARDIZATION_KEYWORDS):
        return PQCMigrationExtraction(
            severity="standardization",
            normalized_value=0.3,
            rationale=f"standardization phrase: {_first_hit(blob, _STANDARDIZATION_KEYWORDS)}",
        )

    # Bare keyword mention floor — informational only.
    return PQCMigrationExtraction(
        severity="mention",
        normalized_value=0.1,
        rationale="bare PQC keyword mention; no adoption action phrase",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _any_match(blob_lower: str, needles: tuple[str, ...]) -> bool:
    return any(needle in blob_lower for needle in needles)


def _first_hit(blob_lower: str, needles: tuple[str, ...]) -> str:
    for needle in needles:
        if needle in blob_lower:
            return needle
    return ""

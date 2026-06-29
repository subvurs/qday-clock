"""Token-boundary keyword matching (Fix A) + fidelity admission (Fix B).

Fix A: ``keyword_hit`` replaces the old ``kw in blob`` substring test so a
keyword only fires when it is NOT flanked by alphanumerics. Punctuation
(hyphen, ``+``, space, comma) still counts as a boundary, so real
compound terms ("CRYSTALS-Kyber", "SPHINCS+", "FIPS 203", "ecc-256")
keep matching while substring accidents ("shorten"→shor,
"quasicrystals"→crystals, "Rebecca"→ecc) are rejected.

Fix B: "fidelity" is admitted into ``ERROR_RATE_KEYWORDS`` so the axis-4
extractor — which already converts a reported fidelity F to an implied
error 1−F — actually receives fidelity-only articles at its keyword gate.
"""

from __future__ import annotations

from qday_clock.extract import axis_error_rate, axis_pqc_migration, axis_resource_estimate
from qday_clock.extract.keywords import ERROR_RATE_KEYWORDS, keyword_hit

# ---------------------------------------------------------------------------
# Fix A — substring accidents are rejected
# ---------------------------------------------------------------------------


def test_keyword_hit_rejects_embedded_substrings() -> None:
    # "shor" must not fire inside "shorten" / "offshore".
    assert not keyword_hit("we shorten the runtime", ("shor",))
    assert not keyword_hit("an offshore data centre", ("shor",))
    # "ecc" must not fire inside "Rebecca" / "ecclesiastical".
    assert not keyword_hit("rebecca published the result", ("ecc",))
    # "crystals" must not fire inside "quasicrystals".
    assert not keyword_hit("a study of quasicrystals", ("crystals",))


def test_keyword_hit_accepts_boundary_flanked_tokens() -> None:
    # Whitespace / apostrophe / start-of-string boundaries.
    assert keyword_hit("shor's algorithm runs", ("shor",))
    assert keyword_hit("ecc is broken", ("ecc",))
    # Punctuation counts as a boundary: hyphen, plus, space.
    assert keyword_hit("ecc-256 attacked", ("ecc",))
    assert keyword_hit("crystals-kyber selected", ("crystals",))
    assert keyword_hit("sphincs+ finalized", ("sphincs+",))
    assert keyword_hit("nist publishes fips 203", ("fips 203",))


def test_keyword_hit_is_case_insensitive() -> None:
    assert keyword_hit("SHOR factored the number", ("shor",))
    assert keyword_hit("CRYSTALS-Kyber", ("crystals",))


# ---------------------------------------------------------------------------
# Fix A — the change is wired through the real axis ``matches`` gates
# ---------------------------------------------------------------------------


def test_resource_axis_rejects_shorten_but_accepts_shor() -> None:
    assert not axis_resource_estimate.matches("We shorten the circuit", "")
    assert axis_resource_estimate.matches("Shor's algorithm on RSA-2048", "")


def test_pqc_axis_rejects_quasicrystals_materials_article() -> None:
    # Live-manifest regression: a quasicrystals materials-science article
    # used to trip the axis-5 gate via the "crystals" substring.
    title = "New quantum algorithm solves impossible materials problem"
    summary = "materials known as quasicrystals, opening the door to power"
    assert not axis_pqc_migration.matches(title, summary)
    assert axis_pqc_migration.extract(title, summary) is None


def test_pqc_axis_still_accepts_real_crystals_kyber() -> None:
    assert axis_pqc_migration.matches("CRYSTALS-Kyber deployed in TLS", "")


# ---------------------------------------------------------------------------
# Fix B — fidelity admission into the axis-4 gate
# ---------------------------------------------------------------------------


def test_fidelity_is_an_error_rate_keyword() -> None:
    assert "fidelity" in ERROR_RATE_KEYWORDS


def test_axis4_gate_fires_on_fidelity_only_article() -> None:
    # No explicit "gate error" phrase — only a fidelity figure.
    assert axis_error_rate.matches("Two-qubit gate fidelity reaches 99.9%", "")


def test_axis4_converts_fidelity_only_article_to_error() -> None:
    res = axis_error_rate.extract(
        "Two-qubit gate fidelity reaches 99.9%",
        "team reports 99.9 % gate fidelity on hardware",
    )
    assert res is not None
    assert res.source_kind == "fidelity_conversion"
    # 99.9 % fidelity → implied error 1e-3.
    assert abs(res.error_rate - 1e-3) < 1e-6

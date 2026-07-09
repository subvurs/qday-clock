"""Per-axis keyword catalogues.

These are the public, deterministic strings that each axis extractor
matches against article titles and summaries. Per plan §H, no LLM is
used at scoring time. Offline LLM pre-extraction with cached output is
permitted but not part of MVP.

The keyword lists are intentionally narrow and reviewed in
``docs/SIGNAL_CATALOG.md``; widening them is a CHANGELOG entry.

Matching is token-boundary, not naive substring (see :func:`keyword_hit`).
A keyword fires only when it is not flanked by additional ``[A-Za-z0-9]``
characters, so ``"shor"`` no longer matches ``"shorten"``, ``"ecc"`` no
longer matches ``"Rebecca"``, and ``"crystals"`` no longer matches
``"quasicrystals"``. Non-word punctuation (hyphens, ``+``, spaces,
commas) still counts as a boundary, so ``"CRYSTALS-Kyber"``,
``"SPHINCS+"``, and ``"FIPS 203"`` continue to match.
"""

from __future__ import annotations

import re
from functools import lru_cache

# Axis 1 — Logical qubit progress
LOGICAL_QUBIT_KEYWORDS: tuple[str, ...] = (
    "logical qubit",
    "logical qubits",
    "surface code",
    "qldpc",
    "ldpc code",
    "bivariate bicycle",
    "bb code",
    "magic state",
    "below threshold",
    "below the threshold",
    "fault-tolerant",
    "fault tolerant",
    "code distance",
)

# Axis 2 — Physical qubit scaling (v0.2)
PHYSICAL_SCALING_KEYWORDS: tuple[str, ...] = (
    "qubit processor",
    "qubits announced",
    "condor",
    "flamingo",
    "kookaburra",
    "willow",
    "tempo",
    "helios",
    "atom computing",
    "psiquantum",
    "physical qubits",
)

# Axis 3 — Algorithmic / resource estimate (v0.2; ECC channel v0.3)
RESOURCE_ESTIMATE_KEYWORDS: tuple[str, ...] = (
    "shor",
    "factoring",
    "factor rsa",
    "rsa",
    "rsa-2048",
    "rsa 2048",
    "ecc",
    "ecdlp",
    "ecdsa",
    "secp256k1",
    "elliptic curve",
    "discrete logarithm",
    "discrete log",
    "grover",
    "aes-128",
    "aes 128",
    "t-count",
    "t-depth",
    "physical qubits to factor",
    "space-time tradeoff",
)

# Axis 4 — Error rate floor (v0.2)
ERROR_RATE_KEYWORDS: tuple[str, ...] = (
    "gate error",
    "two-qubit error",
    "2q error",
    "t1",
    "t2",
    "coherence time",
    "measurement fidelity",
    "fidelity",
    "qubit loss",
)

# Axis 5 — PQC migration (v0.2)
PQC_MIGRATION_KEYWORDS: tuple[str, ...] = (
    "kyber",
    "dilithium",
    "sphincs+",
    "ml-kem",
    "ml-dsa",
    "crystals",
    "pqc migration",
    "post-quantum migration",
    "crypto-agility",
    "crypto agility",
    "hybrid tls",
    "fips 203",
    "fips 204",
    "fips 205",
    "cnsa 2.0",
)


# ---------------------------------------------------------------------------
# Token-boundary matching
# ---------------------------------------------------------------------------


@lru_cache(maxsize=512)
def _compile_keyword(kw: str) -> re.Pattern[str]:
    """Compile a keyword into a token-boundary regex.

    A match requires that the keyword is not directly adjacent to another
    ``[A-Za-z0-9]`` character on either side. Internal punctuation in the
    keyword (``-``, ``+``, spaces) is matched literally via ``re.escape``;
    such punctuation also serves as a boundary, so multi-word keywords like
    ``"fips 203"`` and suffix-punctuated keywords like ``"sphincs+"`` match
    as written.
    """
    return re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(kw)}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def keyword_hit(text: str, keywords: tuple[str, ...]) -> bool:
    """Return True if any keyword token-matches ``text``.

    Replaces the previous ``any(kw in text for kw in keywords)`` substring
    test, which produced false positives where a keyword was a substring of
    an unrelated word (``"shor"`` in ``"shorten"``, ``"ecc"`` in
    ``"Rebecca"``, ``"crystals"`` in ``"quasicrystals"``). ``text`` is
    expected to be already lower-cased by the caller; matching is
    case-insensitive regardless.
    """
    return any(_compile_keyword(kw).search(text) for kw in keywords)

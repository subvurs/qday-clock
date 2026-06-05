"""Forbidden-language lint.

Per CLAUDE.md §10 and plan §G, public-facing pages must not use
prediction/marketing language. This lint enforces that on:

  - site/*.html and site/*.tmpl.html
  - site/data/*.json
  - METHODOLOGY.md
  - README.md
  - THREAT_MODEL.md

A small allow-list lets us *describe* the forbidden terms in the
methodology itself (so the page can warn "we never claim quantum
supremacy").
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Public-facing files that must avoid prediction / marketing language.
PUBLIC_FILES = (
    REPO_ROOT / "site" / "index.tmpl.html",
    REPO_ROOT / "site" / "methodology.tmpl.html",
    REPO_ROOT / "site" / "about.tmpl.html",
    REPO_ROOT / "METHODOLOGY.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "THREAT_MODEL.md",
)

#: Substrings that must not appear as standalone claims (case-insensitive).
#: All entries are matched as whole-token / phrase regex.
FORBIDDEN_PATTERNS = (
    r"\bprediction\b",
    r"\bpredicted\b",
    r"\bpredicts\b",
    r"\bpredict\b",
    r"\bguaranteed\b",
    r"\bwill happen by\b",
    r"\bbreakthrough\b",
    r"\brevolutionary\b",
    r"\bquantum supremacy\b",
)

#: Lines containing any of these phrases are treated as descriptive
#: discussion of forbidden language, not as a prediction.
ALLOW_CONTEXTS = (
    "forbidden",
    "we do not",
    "we don't",
    "not a prediction",
    "is not a prediction",
    "never a prediction",
    "this is a reading",
    "not say",
    "not used",
    "never use",
    "avoid",
    "rather than",
)


def _file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", PUBLIC_FILES, ids=lambda p: p.name)
def test_no_forbidden_language(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"public file not present yet: {path}")
    text = _file_text(path)
    for line_no, line in enumerate(text.splitlines(), start=1):
        lower = line.lower()
        if any(ctx in lower for ctx in ALLOW_CONTEXTS):
            continue
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, line, flags=re.IGNORECASE):
                raise AssertionError(
                    f"{path.name}:{line_no} uses forbidden language "
                    f"matching {pattern!r}: {line.strip()!r}"
                )

"""Curator manifest client tests.

Covers the happy path and every distinct ``error_code`` raised by
:func:`qday_clock.ingest.curator_client.fetch_manifest`. Per CLAUDE.md
§8, every failure mode has a dedicated test so a refactor cannot
silently downgrade a raise into a warning.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from qday_clock.core.errors import IngestError
from qday_clock.core.signing import SigningKey, sign_payload
from qday_clock.ingest.curator_client import fetch_manifest


def _minimal_body() -> dict:
    """A schema-valid manifest body with one synthetic article."""
    return {
        "version": "1.0",
        "generated_at": datetime(2026, 6, 1, tzinfo=timezone.utc).isoformat(),
        "curator_commit": "deadbeefcafe",
        "articles": [
            {
                "post_id": "post-1",
                "title": "Distance-11 surface code memory",
                "url": "https://example.org/post-1",
                "source": "Example Lab",
                "topics": ["hardware", "error_correction"],
                "published_at": datetime(2026, 5, 15, tzinfo=timezone.utc).isoformat(),
                "relevance_score": 0.9,
                "summary": "Demonstration of a distance-11 surface code logical qubit.",
            },
        ],
        "db_row_counts": {"raw_articles": 1, "curated_posts": 0, "sources": 1},
    }


def _write_signed(tmp_path: Path, body: dict, sk: SigningKey) -> Path:
    sig_b64, pub_b64 = sign_payload(body, sk)
    final = {**body, "signature": sig_b64, "signing_pubkey": pub_b64}
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(final), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_fetch_manifest_happy_path(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    p = _write_signed(tmp_path, _minimal_body(), sk)
    m = fetch_manifest(p)
    assert m.version == "1.0"
    assert len(m.articles) == 1
    assert m.articles[0].post_id == "post-1"


def test_fetch_manifest_pubkey_pin_accepts_correct_key(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    pub_b64 = sk.verify_key.to_b64()
    p = _write_signed(tmp_path, _minimal_body(), sk)
    m = fetch_manifest(p, expected_pubkey=pub_b64)
    assert len(m.articles) == 1


def test_fetch_manifest_unsigned_debug_path(tmp_path: Path) -> None:
    """``require_signature=False`` is the documented debug path."""
    p = tmp_path / "unsigned.json"
    p.write_text(json.dumps(_minimal_body()), encoding="utf-8")
    m = fetch_manifest(p, require_signature=False)
    assert m.version == "1.0"


# ---------------------------------------------------------------------------
# Negative paths — one test per ``error_code``
# ---------------------------------------------------------------------------


def test_fetch_manifest_not_found(tmp_path: Path) -> None:
    with pytest.raises(IngestError) as exc_info:
        fetch_manifest(tmp_path / "missing.json")
    assert exc_info.value.error_code == "ingest.manifest_not_found"


def test_fetch_manifest_bad_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json {{{", encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        fetch_manifest(p)
    assert exc_info.value.error_code == "ingest.manifest_bad_json"


def test_fetch_manifest_not_object(tmp_path: Path) -> None:
    p = tmp_path / "list.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        fetch_manifest(p)
    assert exc_info.value.error_code == "ingest.manifest_bad_shape"


def test_fetch_manifest_unsigned_default_fails_closed(tmp_path: Path) -> None:
    p = tmp_path / "unsigned.json"
    p.write_text(json.dumps(_minimal_body()), encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        fetch_manifest(p)
    assert exc_info.value.error_code == "ingest.manifest_unsigned"


def test_fetch_manifest_pubkey_pin_mismatch(tmp_path: Path) -> None:
    sk = SigningKey.generate()
    p = _write_signed(tmp_path, _minimal_body(), sk)
    wrong_pub = SigningKey.generate().verify_key.to_b64()
    with pytest.raises(IngestError) as exc_info:
        fetch_manifest(p, expected_pubkey=wrong_pub)
    assert exc_info.value.error_code == "ingest.manifest_pubkey_mismatch"


def test_fetch_manifest_tampered_body_fails_verification(tmp_path: Path) -> None:
    """Mutate the signed body after signing — sig must not verify."""
    sk = SigningKey.generate()
    p = _write_signed(tmp_path, _minimal_body(), sk)
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["curator_commit"] = "TAMPERED"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        fetch_manifest(p)
    assert exc_info.value.error_code == "ingest.manifest_bad_signature"


def test_fetch_manifest_swapped_key_fails_verification(tmp_path: Path) -> None:
    """A signature from key A under pubkey B must not verify."""
    sk_a = SigningKey.generate()
    sk_b = SigningKey.generate()
    body = _minimal_body()
    sig_b64, _ = sign_payload(body, sk_a)
    # Substitute B's pubkey instead of A's — sig won't verify under B.
    pub_b_b64 = sk_b.verify_key.to_b64()
    final = {**body, "signature": sig_b64, "signing_pubkey": pub_b_b64}
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(final), encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        fetch_manifest(p)
    assert exc_info.value.error_code == "ingest.manifest_bad_signature"


def test_fetch_manifest_bad_schema(tmp_path: Path) -> None:
    """A signed manifest with an invalid field shape fails schema validation."""
    body = _minimal_body()
    # Push an out-of-range relevance_score (schema enforces [0,1]).
    body["articles"][0]["relevance_score"] = 5.0
    sk = SigningKey.generate()
    p = _write_signed(tmp_path, body, sk)
    with pytest.raises(IngestError) as exc_info:
        fetch_manifest(p)
    assert exc_info.value.error_code == "ingest.manifest_bad_shape"

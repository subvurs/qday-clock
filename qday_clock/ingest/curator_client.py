"""Curator manifest client.

Q-day Clock never reads the Quantum Curator SQLite database directly.
The contract between the two projects is a signed JSON manifest
produced by the Curator's ``qday-export`` command and consumed here.

Per plan §B "Key coupling decision":

* Loose coupling at the data layer — Curator schema can change without
  breaking Q-day Clock.
* Tight coupling at the canonicalization layer — both sides import the
  same ``qday_clock.core.canonical`` + ``signing`` modules so signature
  bytes never silently diverge. The Curator's export command depends on
  Q-day Clock being importable.

Failure modes (per CLAUDE.md §8 — no silent error swallowing) all
surface as ``IngestError`` with distinct ``error_code`` values:

* ``ingest.manifest_not_found`` — file does not exist
* ``ingest.manifest_bad_json`` — file is not valid JSON
* ``ingest.manifest_unsigned`` — signature or pubkey field missing
* ``ingest.manifest_bad_signature`` — signature does not verify
* ``ingest.manifest_pubkey_mismatch`` — pinned pubkey check failed
* ``ingest.manifest_bad_shape`` — schema validation failed
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from qday_clock.core.errors import IngestError, SignatureError
from qday_clock.core.schemas import CuratorManifest
from qday_clock.core.signing import verify_payload


def fetch_manifest(
    path: Path | str,
    expected_pubkey: str | None = None,
    *,
    require_signature: bool = True,
) -> CuratorManifest:
    """Load and verify a Curator manifest JSON from disk.

    Parameters
    ----------
    path
        Filesystem path to the signed manifest JSON.
    expected_pubkey
        If provided, the manifest's ``signing_pubkey`` MUST equal this
        base64 string. Use this to pin the production Curator key in
        ``refresh.yml``. Per CLAUDE.md §8 a mismatch raises rather than
        silently accepting a different signer.
    require_signature
        Default ``True`` — per CLAUDE.md fail-closed posture. Set
        ``False`` only for offline debugging of unsigned manifests
        produced for testing.

    Returns
    -------
    CuratorManifest
        Pydantic-validated manifest with signature already verified.

    Raises
    ------
    IngestError
        On any failure with a distinct ``error_code`` so refresh.yml /
        tests can branch on the specific failure mode.
    """
    p = Path(path)
    if not p.exists():
        raise IngestError(
            f"Curator manifest not found: {p}",
            error_code="ingest.manifest_not_found",
        )

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # Explicitly caught: a partially-written manifest mid-deploy or
        # a corrupted artifact. We surface rather than swallow so the
        # daily refresh PR shows the failure.
        raise IngestError(
            f"Curator manifest is not valid JSON: {exc}",
            error_code="ingest.manifest_bad_json",
        ) from exc

    if not isinstance(raw, dict):
        raise IngestError(
            f"Curator manifest must be a JSON object, got {type(raw).__name__}",
            error_code="ingest.manifest_bad_shape",
        )

    signature = raw.get("signature")
    pubkey = raw.get("signing_pubkey")

    if require_signature:
        if not signature or not pubkey:
            raise IngestError(
                "Curator manifest is unsigned (signature and/or signing_pubkey missing)",
                error_code="ingest.manifest_unsigned",
            )

        if expected_pubkey is not None and pubkey != expected_pubkey:
            raise IngestError(
                f"Curator manifest signing_pubkey does not match pinned key "
                f"(expected={expected_pubkey[:16]}…, got={str(pubkey)[:16]}…)",
                error_code="ingest.manifest_pubkey_mismatch",
            )

        # Verify against the body with signature fields stripped, since
        # that is the exact form the Curator-side export signed.
        body = {k: v for k, v in raw.items() if k not in ("signature", "signing_pubkey")}
        try:
            ok = verify_payload(body, signature, pubkey)
        except SignatureError as exc:
            # Re-raise as IngestError so refresh.yml only has to catch
            # one exception family at the ingest boundary.
            raise IngestError(
                f"Curator manifest signature could not be parsed: {exc}",
                error_code="ingest.manifest_bad_signature",
            ) from exc
        if not ok:
            raise IngestError(
                "Curator manifest signature did not verify under signing_pubkey",
                error_code="ingest.manifest_bad_signature",
            )

    try:
        return CuratorManifest.model_validate(raw)
    except ValidationError as exc:
        raise IngestError(
            f"Curator manifest failed schema validation: {exc.errors()}",
            error_code="ingest.manifest_bad_shape",
        ) from exc

"""Signed clock-state manifest writer.

Writes ``site/data/clock_state.json`` with:

- RFC 8785 canonical body (sorted keys, no whitespace)
- Detached Ed25519 signature embedded under ``signature``
- Public key embedded under ``signing_pubkey``

The ``history.jsonl`` append-only log is a separate file; each line is
one canonical :class:`ClockState` snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

from qday_clock.core.canonical import canonicalize
from qday_clock.core.schemas import ClockState
from qday_clock.core.signing import SigningKey, sign_payload


def clock_state_to_dict(state: ClockState) -> dict:
    """Convert a :class:`ClockState` to the JSON-serializable dict that
    gets canonicalized and signed.

    Datetime fields are serialized as ISO-8601 UTC. Pydantic's
    :meth:`model_dump` with ``mode='json'`` handles enum unwrapping
    and datetime ISO serialization.
    """
    return state.model_dump(mode="json")


def write_signed_manifest(
    state: ClockState,
    out_path: Path,
    signing_key: SigningKey,
) -> str:
    """Sign ``state`` with ``signing_key`` and write the canonical JSON
    to ``out_path``. Returns the canonical hash for logging.
    """
    body = clock_state_to_dict(state)
    # Remove signature fields before signing (signing over self would
    # be a circular dependency); then re-attach them after.
    body.pop("signature", None)
    body.pop("signing_pubkey", None)

    signature_b64, pubkey_b64 = sign_payload(body, signing_key)
    body["signature"] = signature_b64
    body["signing_pubkey"] = pubkey_b64

    canonical_bytes = canonicalize(body)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(canonical_bytes)

    # Return the unsigned-body hash for logging (matches what verify
    # would re-derive).
    body_unsigned = {k: v for k, v in body.items() if k not in ("signature", "signing_pubkey")}
    import hashlib

    return hashlib.sha256(canonicalize(body_unsigned)).hexdigest()


def append_history(
    state: ClockState,
    history_path: Path,
) -> None:
    """Append one canonical :class:`ClockState` snapshot to the history
    JSON-lines log.

    history.jsonl is append-only by convention. Per CLAUDE.md §1
    failures and reversals are recorded equally; nothing is rewritten."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    body = clock_state_to_dict(state)
    line = json.dumps(body, separators=(",", ":"), sort_keys=True)
    with history_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

"""Ed25519 signing for Q-day Clock manifests and clock-state artifacts.

Thin wrapper over ``cryptography``'s Ed25519 primitives. Q-day Clock
rolls no crypto. Errors are surfaced via :class:`SignatureError`.

The signing strategy is symmetric to qwashed's: every artifact carries
the verifier public key as base64, plus a base64 detached signature
over the artifact's RFC-8785 canonical form.
"""

from __future__ import annotations

import base64
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from qday_clock.core.canonical import canonicalize
from qday_clock.core.errors import SignatureError

__all__ = [
    "ED25519_PUBKEY_LEN",
    "ED25519_SIGNATURE_LEN",
    "SigningKey",
    "VerifyKey",
    "sign_payload",
    "verify_payload",
]

ED25519_PUBKEY_LEN: Final[int] = 32
ED25519_SIGNATURE_LEN: Final[int] = 64


class VerifyKey:
    """Ed25519 public key wrapper."""

    __slots__ = ("_pk",)

    def __init__(self, pk: Ed25519PublicKey) -> None:
        self._pk = pk

    @classmethod
    def from_bytes(cls, raw: bytes) -> "VerifyKey":
        if len(raw) != ED25519_PUBKEY_LEN:
            raise SignatureError(
                f"Ed25519 public key must be {ED25519_PUBKEY_LEN} bytes, got {len(raw)}",
                error_code="signing.bad_pubkey_length",
            )
        try:
            pk = Ed25519PublicKey.from_public_bytes(raw)
        except Exception as exc:
            raise SignatureError(
                f"failed to parse Ed25519 public key: {exc}",
                error_code="signing.bad_pubkey",
            ) from exc
        return cls(pk)

    @classmethod
    def from_b64(cls, encoded: str) -> "VerifyKey":
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise SignatureError(
                f"public key is not valid base64: {exc}",
                error_code="signing.bad_pubkey_b64",
            ) from exc
        return cls.from_bytes(raw)

    def to_bytes(self) -> bytes:
        from cryptography.hazmat.primitives import serialization

        return self._pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def to_b64(self) -> str:
        return base64.b64encode(self.to_bytes()).decode("ascii")

    def verify(self, message: bytes, signature: bytes) -> bool:
        """Return True iff ``signature`` is a valid Ed25519 signature
        of ``message`` under this public key.

        Returns ``False`` on signature mismatch (does NOT raise);
        raises :class:`SignatureError` only on input-validation failure
        (e.g. wrong-length signature).
        """
        if len(signature) != ED25519_SIGNATURE_LEN:
            raise SignatureError(
                f"signature must be {ED25519_SIGNATURE_LEN} bytes, got {len(signature)}",
                error_code="signing.bad_sig_length",
            )
        try:
            self._pk.verify(signature, message)
            return True
        except InvalidSignature:
            return False


class SigningKey:
    """Ed25519 private key wrapper."""

    __slots__ = ("_sk", "verify_key")

    def __init__(self, sk: Ed25519PrivateKey) -> None:
        self._sk = sk
        self.verify_key = VerifyKey(sk.public_key())

    @classmethod
    def generate(cls) -> "SigningKey":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_bytes(cls, raw: bytes) -> "SigningKey":
        if len(raw) != 32:
            raise SignatureError(
                f"Ed25519 private key must be 32 bytes, got {len(raw)}",
                error_code="signing.bad_privkey_length",
            )
        try:
            sk = Ed25519PrivateKey.from_private_bytes(raw)
        except Exception as exc:
            raise SignatureError(
                f"failed to parse Ed25519 private key: {exc}",
                error_code="signing.bad_privkey",
            ) from exc
        return cls(sk)

    def to_bytes(self) -> bytes:
        from cryptography.hazmat.primitives import serialization

        return self._sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def sign(self, message: bytes) -> bytes:
        return self._sk.sign(message)


def sign_payload(payload: dict, signing_key: SigningKey) -> tuple[str, str]:
    """Canonicalize ``payload``, sign it, return (signature_b64, pubkey_b64).

    The signature is over the RFC-8785 canonical form of ``payload``.
    Callers typically embed both values into the same JSON object
    under reserved keys (e.g. ``signature``, ``signing_pubkey``).
    """
    canonical = canonicalize(payload)
    signature = signing_key.sign(canonical)
    return (
        base64.b64encode(signature).decode("ascii"),
        signing_key.verify_key.to_b64(),
    )


def verify_payload(payload: dict, signature_b64: str, pubkey_b64: str) -> bool:
    """Verify ``payload`` against ``signature_b64`` under ``pubkey_b64``."""
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception as exc:
        raise SignatureError(
            f"signature is not valid base64: {exc}",
            error_code="signing.bad_sig_b64",
        ) from exc
    vk = VerifyKey.from_b64(pubkey_b64)
    canonical = canonicalize(payload)
    return vk.verify(canonical, signature)

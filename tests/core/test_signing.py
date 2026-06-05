"""Ed25519 sign/verify unit tests.

Round-trip + tamper-detection. No production key material involved.
"""

from __future__ import annotations

from qday_clock.core.signing import SigningKey, sign_payload, verify_payload


def test_sign_then_verify_round_trip() -> None:
    key = SigningKey.generate()
    payload = {"axis": "logical_qubits", "reading": 0.42}
    sig_b64, pubkey_b64 = sign_payload(payload, key)
    assert verify_payload(payload, sig_b64, pubkey_b64) is True


def test_tampered_payload_fails_verification() -> None:
    key = SigningKey.generate()
    payload = {"axis": "logical_qubits", "reading": 0.42}
    sig_b64, pubkey_b64 = sign_payload(payload, key)
    tampered = {"axis": "logical_qubits", "reading": 0.43}
    assert verify_payload(tampered, sig_b64, pubkey_b64) is False


def test_tampered_signature_fails_verification() -> None:
    import base64

    key = SigningKey.generate()
    payload = {"x": 1}
    sig_b64, pubkey_b64 = sign_payload(payload, key)
    raw = bytearray(base64.b64decode(sig_b64))
    raw[0] ^= 0x01  # flip one bit
    bad_sig = base64.b64encode(bytes(raw)).decode("ascii")
    assert verify_payload(payload, bad_sig, pubkey_b64) is False


def test_different_keys_produce_different_pubkeys() -> None:
    k1 = SigningKey.generate()
    k2 = SigningKey.generate()
    _, p1 = sign_payload({"x": 1}, k1)
    _, p2 = sign_payload({"x": 1}, k2)
    assert p1 != p2

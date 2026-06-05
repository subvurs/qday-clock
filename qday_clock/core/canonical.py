"""RFC 8785 (JCS) canonical JSON serialization for Q-day Clock.

Every signed artifact (``clock_state.json``, manifest entries) is signed
over the canonical byte sequence of its JSON payload. Without
canonicalization, two semantically identical JSON objects can serialize
to different byte strings and produce different signatures.

This is a self-contained re-implementation aligned with the qwashed
canonical module. It is intentionally not a transitive dependency on
qwashed so Q-day Clock can be packaged stand-alone.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Final, Literal

from qday_clock.core.errors import CanonicalizationError

__all__ = ["canonical_hash", "canonicalize"]

_HashAlgo = Literal["sha256", "sha3-256"]

#: JSON-mandatory short escapes, per RFC 8259 sec. 7.
_SHORT_ESCAPES: Final[dict[int, str]] = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def canonicalize(obj: Any) -> bytes:
    """Serialize ``obj`` to canonical JSON bytes per RFC 8785."""
    seen: set[int] = set()
    parts: list[str] = []
    _emit(obj, parts, seen)
    return "".join(parts).encode("utf-8")


def canonical_hash(obj: Any, algo: _HashAlgo = "sha256") -> str:
    """Canonicalize ``obj`` and return the lowercase hex digest."""
    payload = canonicalize(obj)
    if algo == "sha256":
        return hashlib.sha256(payload).hexdigest()
    if algo == "sha3-256":
        return hashlib.sha3_256(payload).hexdigest()
    raise CanonicalizationError(
        f"unsupported hash algorithm: {algo!r}",
        error_code="canonical.bad_hash_algo",
    )


def _emit(obj: Any, out: list[str], seen: set[int]) -> None:
    if obj is None:
        out.append("null")
        return
    if obj is True:
        out.append("true")
        return
    if obj is False:
        out.append("false")
        return
    if isinstance(obj, str):
        out.append(_emit_string(obj))
        return
    if isinstance(obj, bool):  # pragma: no cover - covered above
        out.append("true" if obj else "false")
        return
    if isinstance(obj, int):
        out.append(_emit_integer(obj))
        return
    if isinstance(obj, float):
        out.append(_emit_float(obj))
        return

    container_id = id(obj)
    if container_id in seen:
        raise CanonicalizationError(
            "cycle detected in input object graph",
            error_code="canonical.cycle",
        )

    if isinstance(obj, dict):
        seen.add(container_id)
        try:
            _emit_object(obj, out, seen)
        finally:
            seen.discard(container_id)
        return

    if isinstance(obj, (list, tuple)):
        seen.add(container_id)
        try:
            _emit_array(obj, out, seen)
        finally:
            seen.discard(container_id)
        return

    raise CanonicalizationError(
        f"type {type(obj).__name__!r} has no canonical JSON representation",
        error_code="canonical.unsupported_type",
    )


def _emit_object(obj: dict[Any, Any], out: list[str], seen: set[int]) -> None:
    items: list[tuple[str, Any]] = []
    for key, value in obj.items():
        if not isinstance(key, str):
            raise CanonicalizationError(
                f"object key must be str, got {type(key).__name__}",
                error_code="canonical.non_string_key",
            )
        items.append((key, value))
    items.sort(key=lambda kv: _utf16_codeunits(kv[0]))

    out.append("{")
    first = True
    for key, value in items:
        if not first:
            out.append(",")
        first = False
        out.append(_emit_string(key))
        out.append(":")
        _emit(value, out, seen)
    out.append("}")


def _emit_array(arr: list[Any] | tuple[Any, ...], out: list[str], seen: set[int]) -> None:
    out.append("[")
    first = True
    for item in arr:
        if not first:
            out.append(",")
        first = False
        _emit(item, out, seen)
    out.append("]")


def _emit_string(value: str) -> str:
    parts: list[str] = ['"']
    for ch in value:
        cp = ord(ch)
        short = _SHORT_ESCAPES.get(cp)
        if short is not None:
            parts.append(short)
        elif cp < 0x20:
            parts.append(f"\\u{cp:04x}")
        else:
            parts.append(ch)
    parts.append('"')
    return "".join(parts)


def _emit_integer(value: int) -> str:
    return str(value)


def _emit_float(value: float) -> str:
    if math.isnan(value):
        raise CanonicalizationError(
            "NaN has no canonical JSON representation",
            error_code="canonical.nan",
        )
    if math.isinf(value):
        raise CanonicalizationError(
            "Infinity has no canonical JSON representation",
            error_code="canonical.infinity",
        )
    if value == 0.0:
        return "0"
    if value.is_integer() and abs(value) < 1e16:
        return str(int(value))
    text = repr(value)
    if "e" in text:
        mantissa, _, exponent = text.partition("e")
        if exponent.startswith("+"):
            exponent = exponent[1:]
        if exponent.startswith("-0") and len(exponent) > 2:
            exponent = "-" + exponent[2:].lstrip("0")
            if exponent == "-":
                exponent = "0"
        elif exponent.startswith("0") and len(exponent) > 1:
            exponent = exponent.lstrip("0") or "0"
        text = f"{mantissa}e{exponent}"
    return text


def _utf16_codeunits(s: str) -> tuple[int, ...]:
    units: list[int] = []
    for ch in s:
        cp = ord(ch)
        if cp < 0x10000:
            units.append(cp)
        else:
            cp -= 0x10000
            units.append(0xD800 + (cp >> 10))
            units.append(0xDC00 + (cp & 0x3FF))
    return tuple(units)

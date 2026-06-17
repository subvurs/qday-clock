"""RFC 8785 canonicalization unit tests.

Covers byte stability, key ordering, number formatting, NaN/Inf
rejection, cycle detection, and non-string-key rejection.
"""

from __future__ import annotations

import math

import pytest

from qday_clock.core.canonical import canonical_hash, canonicalize
from qday_clock.core.errors import CanonicalizationError


def test_simple_object_round_trip() -> None:
    payload = {"b": 2, "a": 1}
    out = canonicalize(payload)
    # Keys sorted lexically: a then b.
    assert out == b'{"a":1,"b":2}'


def test_nested_arrays_and_objects() -> None:
    payload = {"x": [3, 1, 2], "y": {"q": None, "p": True}}
    out = canonicalize(payload).decode("utf-8")
    assert out == '{"x":[3,1,2],"y":{"p":true,"q":null}}'


def test_integer_floats_emit_as_integers() -> None:
    assert canonicalize(1.0) == b"1"
    assert canonicalize(-7.0) == b"-7"


def test_nan_and_inf_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonicalize(float("nan"))
    with pytest.raises(CanonicalizationError):
        canonicalize(math.inf)


def test_non_string_key_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonicalize({1: "a"})


def test_cycle_rejected() -> None:
    a: dict = {}
    a["self"] = a
    with pytest.raises(CanonicalizationError):
        canonicalize(a)


def test_canonical_hash_is_deterministic() -> None:
    h1 = canonical_hash({"a": 1, "b": [2, 3]})
    h2 = canonical_hash({"b": [2, 3], "a": 1})
    assert h1 == h2


def test_string_escapes_for_control_chars() -> None:
    out = canonicalize('\t\n"\\').decode("utf-8")
    assert out == '"\\t\\n\\"\\\\"'

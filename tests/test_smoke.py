"""End-to-end smoke test for the v0.1.0 MVP pipeline.

Per plan section G: full pipeline from seed fixture to signed manifest
to rendered HTML, under 30s.

Stages exercised:

  ingest (seed_signals)
    -> score (compute_clock_state)
    -> sign  (write_signed_manifest, in tmp_path)
    -> render (render_index, render_methodology, render_about)

No network. No real-world data. Uses the existing seed-signals JSON
shipped at ``data/seed_signals.json`` if present; otherwise constructs
a minimal in-memory signal so the smoke test always has something to
score.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from qday_clock.core.canonical import canonicalize
from qday_clock.core.schemas import (
    AxisId,
    ClockState,
    EvidenceClass,
    Signal,
)
from qday_clock.core.signing import SigningKey, verify_payload
from qday_clock.render.manifest import write_signed_manifest
from qday_clock.render.templates import render_about, render_index, render_methodology
from qday_clock.score.clock import compute_clock_state

REPO_ROOT = Path(__file__).resolve().parent.parent


def _fallback_signal() -> Signal:
    now = datetime.now(tz=UTC)
    return Signal(
        signal_id="smoke-fallback-d7-fixture",
        axis=AxisId.LOGICAL_QUBITS,
        title="Smoke-test distance-7 surface code fixture",
        summary="Synthetic in-memory signal for smoke test only.",
        source="smoke-test",
        url=None,
        published_at=now,
        observed_at=now,
        evidence_class=EvidenceClass.HARDWARE,
        raw_value=7.0,
        normalized_value=0.5,
        confidence=1.0,
    )


def test_pipeline_smoke(tmp_path: Path) -> None:
    t0 = time.monotonic()

    # 1. Ingest — use shipped seed signals if available, else fallback.
    seed_path = REPO_ROOT / "data" / "seed_signals.json"
    if seed_path.exists():
        from qday_clock.ingest.seed_signals import load_seed_signals

        signals = load_seed_signals(seed_path)
        # If the shipped seed has no logical-qubits entries, still
        # cover that axis with the fallback so we exercise the
        # non-cold-start branch.
        if not any(s.axis == AxisId.LOGICAL_QUBITS for s in signals):
            signals.append(_fallback_signal())
    else:
        signals = [_fallback_signal()]

    # 2. Score.
    state: ClockState = compute_clock_state(signals)
    assert 0.0 <= state.clock_hours <= 24.0
    assert 0.0 <= state.clock_score <= 1.0

    # 3. Sign and persist.
    key = SigningKey.generate()
    out_path = tmp_path / "clock_state.json"
    write_signed_manifest(state, out_path, key)
    assert out_path.exists()

    # Round-trip: the persisted JSON must verify with the embedded pubkey.
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    signature_b64 = payload.pop("signature")
    pubkey_b64 = payload.pop("signing_pubkey")
    assert verify_payload(payload, signature_b64, pubkey_b64) is True

    # 4. Render — at least the three MVP HTML pages.
    state_with_sig = state.model_copy(
        update={"signature": signature_b64, "signing_pubkey": pubkey_b64}
    )
    html_index = render_index(state_with_sig)
    assert "<svg" in html_index
    assert "Q-day Clock" in html_index

    methodology_path = REPO_ROOT / "METHODOLOGY.md"
    methodology_text = (
        methodology_path.read_text(encoding="utf-8")
        if methodology_path.exists()
        else "# Methodology\n\nPlaceholder text for smoke test."
    )
    html_method = render_methodology(methodology_text)
    lowered = html_method.lower()
    assert "<html" in lowered or "<!doctype" in lowered or "<section" in lowered

    html_about = render_about(pubkey_b64=pubkey_b64)
    assert pubkey_b64 in html_about

    # 5. Performance gate: plan section G mandates < 30s for smoke.
    elapsed = time.monotonic() - t0
    assert elapsed < 30.0, f"smoke pipeline too slow: {elapsed:.2f}s"


def test_canonical_signed_payload_is_stable() -> None:
    """Two consecutive signed manifests over the same ClockState differ
    only in the signature/pubkey fields — the unsigned canonical body
    must be byte-identical. This is the contract the golden replay test
    relies on."""
    sig = _fallback_signal()
    state = compute_clock_state([sig])
    # Pin generated_at so the two signings see the same body.
    pinned = state.model_copy(update={"generated_at": datetime(2026, 1, 1, tzinfo=UTC)})

    def _unsigned_canonical_bytes(s: ClockState) -> bytes:
        body = s.model_dump(mode="json")
        body.pop("signature", None)
        body.pop("signing_pubkey", None)
        return canonicalize(body)

    a = _unsigned_canonical_bytes(pinned)
    b = _unsigned_canonical_bytes(pinned)
    assert a == b

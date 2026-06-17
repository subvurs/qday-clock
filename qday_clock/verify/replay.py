"""Replay a signed ``clock_state.json`` and verify its signature.

Two modes:

  python -m qday_clock.verify.replay --check <path-to-clock_state.json>
      Loads the file, re-canonicalizes the unsigned body, verifies
      the embedded Ed25519 signature, and checks the body matches the
      schema. Returns exit code 0 on success, 1 on any failure.

  python -m qday_clock.verify.replay --replay <golden-manifest.json>
      Re-runs the scoring pipeline against a golden input fixture and
      prints the canonical-body SHA-256. Used by the CI step that locks
      the golden replay hash.

Per CLAUDE.md section 8: errors propagate. Per section 7: this script
never silently weakens its own assertions; failures cause a non-zero
exit and the failing reason is printed to stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from qday_clock.core.canonical import canonicalize
from qday_clock.core.schemas import ClockState
from qday_clock.core.signing import verify_payload


def _err(msg: str) -> None:
    print(f"verify.replay: ERROR: {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"verify.replay: ok: {msg}")


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"file does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"not valid JSON: {path}: {exc}") from exc


def check_signed_manifest(path: Path) -> int:
    """Validate a signed clock_state.json. Return process exit code."""
    payload = _load_json(path)

    signature_b64 = payload.get("signature")
    pubkey_b64 = payload.get("signing_pubkey")
    if not signature_b64 or not pubkey_b64:
        _err(f"{path}: missing signature or signing_pubkey field")
        return 1

    body = {k: v for k, v in payload.items() if k not in ("signature", "signing_pubkey")}

    # Schema validation: round-trip through ClockState model
    try:
        # Re-attach so the full payload validates including signature fields.
        ClockState.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 — explicit reporting required
        _err(f"{path}: schema validation failed: {exc}")
        return 1

    # Signature validation
    if not verify_payload(body, signature_b64, pubkey_b64):
        _err(f"{path}: Ed25519 signature does not verify against embedded pubkey")
        return 1

    # Canonical-body hash for the operator's records.
    canonical_hash = hashlib.sha256(canonicalize(body)).hexdigest()
    _ok(f"{path}: signature valid; canonical-body sha256 = {canonical_hash}")
    return 0


def replay_golden(fixture_path: Path) -> int:
    """Re-run scoring over a golden input fixture and print the hash.

    Used to (a) bootstrap a locked hash for a new fixture, and (b) catch
    silent regressions where the same fixture produces a different
    canonical body.
    """
    # Local import to avoid a hard dependency for the --check path.
    from qday_clock.core.schemas import AxisId, EvidenceClass, Signal
    from qday_clock.ingest.seed_signals import _stable_signal_id
    from qday_clock.score.clock import compute_clock_state
    from qday_clock.score.gri_baseline import GRIBaseline

    fixture = _load_json(fixture_path)

    required = ("observed_at", "generated_at", "signals", "gri_baseline")
    for k in required:
        if k not in fixture:
            _err(f"fixture {fixture_path}: missing top-level key {k!r}")
            return 1

    def _parse_dt(raw: str) -> datetime:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)

    observed_at = _parse_dt(fixture["observed_at"])
    generated_at = _parse_dt(fixture["generated_at"])

    signals = []
    for entry in fixture["signals"]:
        published_at = _parse_dt(entry["published_at"])
        # Optional per-signal ``observed_at`` override. Lets a fixture age
        # individual signals (e.g. to deterministically fire StaleSignalGate)
        # without shifting the fixture-wide ``now`` reference. Omitted
        # signals fall back to the fixture's top-level ``observed_at``.
        entry_observed_at = (
            _parse_dt(entry["observed_at"]) if "observed_at" in entry else observed_at
        )
        signals.append(
            Signal(
                signal_id=_stable_signal_id(entry["source"], entry["title"], published_at),
                axis=AxisId(entry["axis"]),
                title=entry["title"],
                summary=entry["summary"],
                source=entry["source"],
                url=entry.get("url"),
                published_at=published_at,
                observed_at=entry_observed_at,
                evidence_class=EvidenceClass(entry["evidence_class"]),
                raw_value=float(entry["raw_value"]),
                normalized_value=float(entry["normalized_value"]),
                confidence=float(entry.get("confidence", 1.0)),
            )
        )

    g = fixture["gri_baseline"]
    gri = GRIBaseline(
        survey_year=int(g["survey_year"]),
        median_crqc_year=int(g["median_crqc_year"]),
        label=g["label"],
        source=g["source"],
    )

    # Pin ``now`` to the fixture's observed_at so time-dependent gates
    # (StaleSignalGate) stay deterministic across replays — see
    # tests/golden/test_golden_replay.py for the rationale.
    state = compute_clock_state(signals, gri=gri, now=observed_at)
    state = state.model_copy(update={"generated_at": generated_at})
    body = state.model_dump(mode="json")
    body.pop("signature", None)
    body.pop("signing_pubkey", None)

    canon = canonicalize(body)
    digest = hashlib.sha256(canon).hexdigest()
    _ok(f"replay sha256 = {digest}")
    print(digest)  # plain stdout for easy CI capture
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qday_clock.verify.replay")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check",
        metavar="CLOCK_STATE_JSON",
        type=Path,
        help="validate a signed clock_state.json artifact",
    )
    group.add_argument(
        "--replay",
        metavar="FIXTURE_JSON",
        type=Path,
        help="re-run scoring over a golden input fixture",
    )
    args = parser.parse_args(argv)

    if args.check is not None:
        return check_signed_manifest(args.check)
    return replay_golden(args.replay)


if __name__ == "__main__":
    raise SystemExit(main())

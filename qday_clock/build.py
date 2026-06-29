"""Build-step entry point for the Q-day Clock static site.

Closes the v0.2 loop opened by v0.2.1 (UI layer): the dashboard +
sources templates landed in v0.2.1 ship as Jinja sources but were not
yet wired into a production build step. This module is that step.

Pipeline:

  1. Ingest:    load seed signals (and optionally a Curator manifest)
  2. Score:     compute_clock_state(signals, ...) — same call the
                v0.2 golden replay uses
  3. Sign:      write_signed_manifest -> site/data/clock_state.json
  4. History:   append_history -> site/data/history.jsonl
  5. Render:    Jinja2 -> site/{index,methodology,about,dashboard,sources}.html

Run as a module::

    python -m qday_clock.build \\
        --signing-key-file /path/to/ed25519.raw \\
        --now 2026-06-01T00:00:00Z

Or programmatically::

    from qday_clock.build import build_site, BuildConfig
    report = build_site(BuildConfig(site_dir=Path("site"), ...))

CLAUDE.md hooks:
- §1 (failure parity):  history.jsonl is append-only; failed / reversed
  readings stay in the log.
- §5 (foundational doc):  every build entry is one new history.jsonl
  line; CHANGELOG.md is updated by humans per release.
- §7 (no test weakening):  this module never overrides the gate
  defaults wired into compute_clock_state.
- §8 (no silent error swallowing):  ingest / signing / render errors
  propagate as QDayClockError subclasses; the CLI exits non-zero.
- §10 (calibrated uncertainty):  the build does not edit per-axis
  readings; it consumes the scored ClockState as-is.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from qday_clock.core.errors import IngestError, QDayClockError, SignatureError
from qday_clock.core.schemas import ClockState, Signal
from qday_clock.core.signing import SigningKey
from qday_clock.core.time import to_utc
from qday_clock.ingest.seed_signals import load_seed_signals
from qday_clock.render.manifest import append_history, write_signed_manifest
from qday_clock.render.templates import (
    render_about,
    render_dashboard,
    render_index,
    render_methodology,
    render_sources,
)
from qday_clock.score.clock import compute_clock_state

#: Default repo-relative paths. The build entry point can be invoked
#: from anywhere; these defaults assume the standard layout under
#: ``public_interest/qday_clock/``.
_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent
_DEFAULT_SITE_DIR = _REPO_ROOT / "site"
_DEFAULT_SEED_SIGNALS = _REPO_ROOT / "data" / "seed_signals.json"
_DEFAULT_METHODOLOGY = _REPO_ROOT / "METHODOLOGY.md"

#: All HTML pages emitted by a build, in dependency order.
_PAGES: tuple[str, ...] = (
    "index.html",
    "methodology.html",
    "about.html",
    "dashboard.html",
    "sources.html",
)

#: Env-var name for the base64-encoded raw Ed25519 private key. The
#: name mirrors the qwashed convention (uppercase, project-prefixed)
#: so a single secret can be configured across CI workflows.
SIGNING_KEY_B64_ENV: str = "QDAY_SIGNING_KEY_B64"


@dataclass
class BuildConfig:
    """All inputs needed to produce a full build.

    Defaults match the standard layout under
    ``public_interest/qday_clock/``. Tests pass a ``tmp_path`` for
    ``site_dir`` to keep builds hermetic.
    """

    site_dir: Path = field(default_factory=lambda: _DEFAULT_SITE_DIR)
    seed_signals_path: Path = field(default_factory=lambda: _DEFAULT_SEED_SIGNALS)
    methodology_path: Path = field(default_factory=lambda: _DEFAULT_METHODOLOGY)
    signing_key_file: Path | None = None
    signing_key_b64_env: str = SIGNING_KEY_B64_ENV
    allow_ephemeral_key: bool = False
    now: datetime | None = None
    extra_signals: tuple[Signal, ...] = ()
    #: If True, skip the ingest + score steps and treat the committed
    #: ``site/data/clock_state.json`` as the source of truth: re-sign it
    #: with the production signing key and render the HTML from it. This
    #: is the Option α step 2 path — it lets the refresh workflow (which
    #: ingests the Curator manifest) own scoring, and lets the pages
    #: deploy own only signing + rendering. Without this flag, every
    #: deploy from ``main`` regenerates state from seeds and silently
    #: overwrites whatever the refresh workflow committed.
    use_committed_state: bool = False


@dataclass
class BuildReport:
    """Returned from :func:`build_site` so callers / tests can assert
    on what was written without re-parsing the site tree."""

    state: ClockState
    canonical_sha256: str
    manifest_path: Path
    history_path: Path
    rendered_pages: tuple[Path, ...]
    used_ephemeral_key: bool


# ---------------------------------------------------------------------------
# Signing key resolution
# ---------------------------------------------------------------------------


def _load_signing_key(config: BuildConfig) -> tuple[SigningKey, bool]:
    """Resolve a signing key per the documented priority order.

    Returns ``(key, used_ephemeral)`` so the caller can flag a dev-only
    build in the report. Fails closed (raises :class:`SignatureError`)
    when no key source is available and ephemeral keys are not allowed.
    """
    # 1. Explicit file path
    if config.signing_key_file is not None:
        path = config.signing_key_file
        if not path.exists():
            raise SignatureError(
                f"signing key file does not exist: {path}",
                error_code="build.signing_key_file_missing",
            )
        raw = path.read_bytes()
        # Accept either raw 32 bytes or a base64 line; reject anything
        # else so we never sign with a corrupted or wrong-format key.
        if len(raw) == 32:
            return SigningKey.from_bytes(raw), False
        try:
            decoded = base64.b64decode(raw.strip(), validate=True)
        except Exception as exc:
            raise SignatureError(
                f"signing key file is neither 32 raw bytes nor valid base64: {path}",
                error_code="build.signing_key_file_bad_format",
            ) from exc
        return SigningKey.from_bytes(decoded), False

    # 2. Environment variable (base64)
    env_value = os.environ.get(config.signing_key_b64_env)
    if env_value:
        try:
            decoded = base64.b64decode(env_value.strip(), validate=True)
        except Exception as exc:
            raise SignatureError(
                f"${config.signing_key_b64_env} is not valid base64",
                error_code="build.signing_key_env_bad_b64",
            ) from exc
        return SigningKey.from_bytes(decoded), False

    # 3. Ephemeral fallback — only with explicit opt-in. Dev / smoke use.
    if config.allow_ephemeral_key:
        return SigningKey.generate(), True

    raise SignatureError(
        (
            "no signing key available: pass --signing-key-file, set "
            f"${config.signing_key_b64_env}, or pass --allow-ephemeral-key "
            "(dev / smoke only)."
        ),
        error_code="build.no_signing_key",
    )


# ---------------------------------------------------------------------------
# Previous-state lookup (for step-change gate observers)
# ---------------------------------------------------------------------------


def _load_previous_axes_readings(manifest_path: Path) -> dict[str, float] | None:
    """If a prior ``clock_state.json`` exists, return its per-axis
    readings as ``{axis_value: reading}`` so step-change gates
    (MultiSourceConfirmationGate, AntiStiffnessGate) have a baseline
    to compare against.

    Returns ``None`` on a cold-start build (no prior file). A file that
    exists but cannot be parsed is a hard error per CLAUDE.md §8 — a
    silently-skipped previous state would mean step-change gates
    silently went dark.
    """
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestError(
            f"existing clock_state.json is not valid JSON: {manifest_path}: {exc}",
            error_code="build.previous_state_bad_json",
        ) from exc

    axes = payload.get("axes")
    if not isinstance(axes, dict):
        raise IngestError(
            (f"existing clock_state.json missing or malformed 'axes' field: {manifest_path}"),
            error_code="build.previous_state_no_axes",
        )

    out: dict[str, float] = {}
    for axis_key, axis_payload in axes.items():
        if not isinstance(axis_payload, dict) or "reading" not in axis_payload:
            raise IngestError(
                (
                    f"existing clock_state.json axis {axis_key!r} missing "
                    f"'reading' field: {manifest_path}"
                ),
                error_code="build.previous_state_axis_no_reading",
            )
        out[axis_key] = float(axis_payload["reading"])
    return out


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_site(config: BuildConfig) -> BuildReport:
    """Run the full ingest → score → sign → render pipeline.

    All artifacts land under ``config.site_dir``:

      - ``data/clock_state.json``  (signed, canonical)
      - ``data/history.jsonl``     (append-only)
      - ``{index,methodology,about,dashboard,sources}.html``

    The function does NOT copy ``site/assets/`` — that directory is
    static and lives in the repo; CI / deploy is responsible for
    publishing it alongside the rendered HTML.
    """
    manifest_path = config.site_dir / "data" / "clock_state.json"

    # The sources page lists seed signals (manifest-classified signals
    # are summarised in the state's per-axis ``contributing_signal_ids``
    # but their full Signal objects don't round-trip through the
    # manifest). Loading seeds is therefore needed for the sources page
    # in BOTH the compute path and the use-committed-state path. This
    # matches the pre-Option-α deploy behaviour, where the sources page
    # has always been seed-driven.
    signals = list(load_seed_signals(config.seed_signals_path))
    if config.extra_signals:
        signals.extend(config.extra_signals)

    if config.use_committed_state:
        # ---- 1+2. Use committed state ------------------------------
        # Skip ingest + score: the refresh workflow already produced
        # the scored, manifest-fed state in site/data/clock_state.json,
        # and that file is what we want the deploy to publish. Fail
        # closed if the file is missing — silently falling back to a
        # fresh seeds-only score would defeat the whole point of the
        # Option α pages-deploy fix.
        if not manifest_path.exists():
            raise IngestError(
                (
                    "use_committed_state=True but committed manifest is "
                    f"missing: {manifest_path}. The refresh workflow is "
                    "the producer of this file; check that the previous "
                    "refresh PR was merged and that site/data/ is "
                    "tracked in the repo."
                ),
                error_code="build.committed_state_missing",
            )
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IngestError(
                (f"committed manifest is not valid JSON: {manifest_path}: {exc}"),
                error_code="build.committed_state_bad_json",
            ) from exc
        state = ClockState.model_validate(payload)
    else:
        # ---- 1. Ingest (already loaded above) ----------------------
        # ---- 2. Score ----------------------------------------------
        previous_axes = _load_previous_axes_readings(manifest_path)
        state = compute_clock_state(
            signals,
            now=config.now,
            previous_axes_readings=previous_axes,
        )

    # ---- 3. Sign + persist manifest ---------------------------------
    # In use_committed_state mode this re-signs the committed state with
    # the deploy-time production signing key. The deployed pubkey is
    # the one embedded in about.html for public verification; the
    # refresh-time signature is internal bookkeeping and is intentionally
    # overwritten here.
    signing_key, used_ephemeral = _load_signing_key(config)
    canonical_sha = write_signed_manifest(state, manifest_path, signing_key)

    # ---- 4. Append history -------------------------------------------
    history_path = config.site_dir / "data" / "history.jsonl"
    append_history(state, history_path)

    # ---- 5. Render pages --------------------------------------------
    pubkey_b64 = signing_key.verify_key.to_b64()

    # The index, about, and dashboard pages reference the manifest /
    # pubkey in their footers. The Jinja templates read ``state.*``
    # directly, so we re-load the signed payload to ensure what the
    # page shows matches what was actually signed (no risk of skew
    # between the signed manifest and the rendered footer).
    signed_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    state_for_render = ClockState.model_validate(signed_payload)

    methodology_text = _read_methodology(config.methodology_path)

    rendered: list[Path] = []
    rendered.append(_write(config.site_dir / "index.html", render_index(state_for_render)))
    rendered.append(
        _write(
            config.site_dir / "methodology.html",
            render_methodology(methodology_text),
        )
    )
    rendered.append(_write(config.site_dir / "about.html", render_about(pubkey_b64=pubkey_b64)))
    rendered.append(
        _write(
            config.site_dir / "dashboard.html",
            render_dashboard(state_for_render),
        )
    )
    rendered.append(
        _write(
            config.site_dir / "sources.html",
            render_sources(state_for_render, signals),
        )
    )

    return BuildReport(
        state=state_for_render,
        canonical_sha256=canonical_sha,
        manifest_path=manifest_path,
        history_path=history_path,
        rendered_pages=tuple(rendered),
        used_ephemeral_key=used_ephemeral,
    )


def _read_methodology(path: Path) -> str:
    """Read the methodology markdown. Missing file is a hard error
    (the page is part of the credibility moat — silent fallback to a
    placeholder would be a §8 violation)."""
    if not path.exists():
        raise IngestError(
            f"methodology file does not exist: {path}",
            error_code="build.methodology_missing",
        )
    return path.read_text(encoding="utf-8")


def _write(path: Path, html: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_dt(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise SystemExit(f"--now is not a valid ISO-8601 datetime: {raw!r}: {exc}") from exc
    return to_utc(dt)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="qday_clock.build",
        description="Build the Q-day Clock static site (signed manifest + HTML).",
    )
    p.add_argument(
        "--site-dir",
        type=Path,
        default=_DEFAULT_SITE_DIR,
        help=f"Output site directory (default: {_DEFAULT_SITE_DIR}).",
    )
    p.add_argument(
        "--seed-signals",
        type=Path,
        default=_DEFAULT_SEED_SIGNALS,
        help=f"Path to seed-signals JSON (default: {_DEFAULT_SEED_SIGNALS}).",
    )
    p.add_argument(
        "--methodology",
        type=Path,
        default=_DEFAULT_METHODOLOGY,
        help=f"Path to METHODOLOGY.md (default: {_DEFAULT_METHODOLOGY}).",
    )
    p.add_argument(
        "--signing-key-file",
        type=Path,
        default=None,
        help=(
            "Path to an Ed25519 private key (32 raw bytes or base64). "
            f"Falls back to ${SIGNING_KEY_B64_ENV}, then to "
            "--allow-ephemeral-key."
        ),
    )
    p.add_argument(
        "--signing-key-b64-env",
        type=str,
        default=SIGNING_KEY_B64_ENV,
        help=f"Env var holding a base64-encoded Ed25519 key (default: {SIGNING_KEY_B64_ENV}).",
    )
    p.add_argument(
        "--allow-ephemeral-key",
        action="store_true",
        help=(
            "Generate a one-shot Ed25519 keypair for this build. "
            "Use only for development / smoke runs — verifiers will "
            "see a different public key on every build."
        ),
    )
    p.add_argument(
        "--now",
        type=str,
        default=None,
        help=(
            "ISO-8601 reference time for deterministic builds (sets the "
            "`now` argument that time-dependent gates see). Defaults to "
            "wall-clock UTC."
        ),
    )
    p.add_argument(
        "--use-committed-state",
        action="store_true",
        help=(
            "Skip ingest + score and consume the committed "
            "site/data/clock_state.json as the source of truth, then "
            "re-sign + render. Use this in the pages-deploy workflow so "
            "the manifest-fed score produced by the refresh workflow is "
            "actually published, instead of being silently overwritten "
            "by a fresh seeds-only score at every deploy."
        ),
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    now = _parse_dt(args.now) if args.now else None
    config = BuildConfig(
        site_dir=args.site_dir,
        seed_signals_path=args.seed_signals,
        methodology_path=args.methodology,
        signing_key_file=args.signing_key_file,
        signing_key_b64_env=args.signing_key_b64_env,
        allow_ephemeral_key=args.allow_ephemeral_key,
        now=now,
        use_committed_state=args.use_committed_state,
    )
    try:
        report = build_site(config)
    except QDayClockError as exc:
        print(
            f"build: ERROR [{exc.error_code}]: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"build: ok: canonical sha256 = {report.canonical_sha256}")
    print(f"build: ok: manifest = {report.manifest_path}")
    print(f"build: ok: history  = {report.history_path}")
    for page in report.rendered_pages:
        print(f"build: ok: rendered = {page}")
    if report.used_ephemeral_key:
        print(
            "build: WARNING: ephemeral signing key — public key will not match "
            "previous or future builds. Do not deploy.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

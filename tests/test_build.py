"""End-to-end smoke for the build entry point.

The build module wires the ingest -> score -> sign -> render pipeline
into a single CLI / function call. These tests assert that:

  - All 5 HTML pages land in ``site/`` with non-trivial content
  - ``site/data/clock_state.json`` is signed and the embedded
    signature verifies under the embedded public key
  - ``site/data/history.jsonl`` is append-only across two builds
  - The signing-key resolution order is fail-closed: missing key +
    no ephemeral flag must raise SignatureError
  - A second build sees the first build's clock_state.json as
    ``previous_axes_readings`` (no exception, file parse path lives)
  - The CLI ``main()`` returns 0 on success, 1 on a missing signing key

These do NOT lock the canonical hash — that's the golden replay's job.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from qday_clock.build import (
    SIGNING_KEY_B64_ENV,
    BuildConfig,
    build_site,
)
from qday_clock.build import (
    main as build_main,
)
from qday_clock.core.errors import IngestError, SignatureError
from qday_clock.core.signing import SigningKey, verify_payload

REPO_ROOT = Path(__file__).resolve().parent.parent

# All five MVP pages must land. Index/methodology/about were the
# v0.1 ship; dashboard/sources joined the public-facing set in v0.2.1
# but did not have a build wired through them until v0.2.2.
_EXPECTED_PAGES = (
    "index.html",
    "methodology.html",
    "about.html",
    "dashboard.html",
    "sources.html",
)


def _config(tmp_path: Path, **overrides) -> BuildConfig:
    """Build a BuildConfig pointing at a fresh tmp site dir but using
    the repo's real seed-signals + methodology, so the smoke covers
    the actual shipped inputs."""
    defaults = dict(
        site_dir=tmp_path / "site",
        seed_signals_path=REPO_ROOT / "data" / "seed_signals.json",
        methodology_path=REPO_ROOT / "METHODOLOGY.md",
        allow_ephemeral_key=True,
        now=datetime(2026, 6, 1, tzinfo=UTC),
    )
    defaults.update(overrides)
    return BuildConfig(**defaults)


def test_build_emits_all_pages_and_signed_manifest(tmp_path: Path) -> None:
    config = _config(tmp_path)
    report = build_site(config)

    # ---- Pages ----
    for name in _EXPECTED_PAGES:
        path = config.site_dir / name
        assert path.exists(), f"build did not emit {name}"
        body = path.read_text(encoding="utf-8")
        assert len(body) > 200, f"{name} suspiciously small"
    assert {p.name for p in report.rendered_pages} == set(_EXPECTED_PAGES)

    # ---- Manifest signature round-trip ----
    payload = json.loads(report.manifest_path.read_text(encoding="utf-8"))
    sig = payload.pop("signature")
    pub = payload.pop("signing_pubkey")
    assert verify_payload(payload, sig, pub) is True

    # ---- History line ----
    lines = report.history_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    first = json.loads(lines[0])
    assert first["version"] == report.state.version

    # ---- Ephemeral flag surfaced ----
    assert report.used_ephemeral_key is True


def test_rendered_pages_reference_assets_css(tmp_path: Path) -> None:
    """Every rendered page must reference ``assets/clock.css``.

    qday_clock.build does NOT copy site/assets/ — the deploy workflow
    copies the assets tree alongside the rendered HTML. If a future
    template change silently drops the stylesheet ``<link>``, the
    deploy workflow would still ship assets but the pages would render
    unstyled and no test would catch it. This guards the asset path
    contract between the renderer and the deploy workflow.
    """
    config = _config(tmp_path)
    build_site(config)
    for name in _EXPECTED_PAGES:
        body = (config.site_dir / name).read_text(encoding="utf-8")
        assert "assets/clock.css" in body, (
            f"{name} does not reference assets/clock.css — the deploy "
            f"workflow stages assets/ for a reason; do not orphan it."
        )


def test_dashboard_and_sources_reference_each_other(tmp_path: Path) -> None:
    """The drill-down links in dashboard.html must point at anchors that
    actually exist in sources.html. v0.2.1 added the templates; this
    asserts the build produces a consistent pair."""
    config = _config(tmp_path)
    report = build_site(config)
    dashboard = (config.site_dir / "dashboard.html").read_text(encoding="utf-8")
    sources = (config.site_dir / "sources.html").read_text(encoding="utf-8")
    # Pull any sources.html#... anchor from the dashboard and check it
    # resolves to an id="..." in sources.html.
    import re

    anchors = re.findall(r"sources\.html#([A-Za-z0-9_-]+)", dashboard)
    assert anchors, "dashboard.html has no sources.html# drill-down links"
    for anchor in anchors:
        assert f'id="{anchor}"' in sources, (
            f"dashboard links to sources.html#{anchor} but no matching id in sources.html"
        )
    # Sanity: the methodology footer URL appears on dashboard.
    assert report.state.methodology_url in dashboard


def test_second_build_appends_history_and_reads_previous_state(
    tmp_path: Path,
) -> None:
    """Second build should append (not overwrite) history and parse the
    first build's clock_state.json without error."""
    config_a = _config(tmp_path, now=datetime(2026, 6, 1, tzinfo=UTC))
    build_site(config_a)

    config_b = _config(tmp_path, now=datetime(2026, 6, 2, tzinfo=UTC))
    build_site(config_b)

    history = (config_b.site_dir / "data" / "history.jsonl").read_text("utf-8")
    lines = [ln for ln in history.splitlines() if ln.strip()]
    assert len(lines) == 2, "history.jsonl must be append-only across builds"


def test_corrupt_previous_state_raises(tmp_path: Path) -> None:
    """A previous clock_state.json that is unreadable must NOT be
    silently treated as a cold start — that would mask a corrupted
    artifact and silently disable step-change gates. CLAUDE.md §8."""
    config = _config(tmp_path)
    (config.site_dir / "data").mkdir(parents=True)
    (config.site_dir / "data" / "clock_state.json").write_text("not json", encoding="utf-8")
    with pytest.raises(IngestError) as excinfo:
        build_site(config)
    assert excinfo.value.error_code == "build.previous_state_bad_json"


def test_signing_key_missing_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No file, no env var, no ephemeral opt-in => SignatureError."""
    monkeypatch.delenv(SIGNING_KEY_B64_ENV, raising=False)
    config = _config(tmp_path, allow_ephemeral_key=False)
    with pytest.raises(SignatureError) as excinfo:
        build_site(config)
    assert excinfo.value.error_code == "build.no_signing_key"


def test_signing_key_from_env_b64(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = SigningKey.generate()
    monkeypatch.setenv(SIGNING_KEY_B64_ENV, base64.b64encode(key.to_bytes()).decode("ascii"))
    config = _config(tmp_path, allow_ephemeral_key=False)
    report = build_site(config)
    assert report.used_ephemeral_key is False
    payload = json.loads(report.manifest_path.read_text(encoding="utf-8"))
    assert payload["signing_pubkey"] == key.verify_key.to_b64()


def test_signing_key_from_file_raw_bytes(tmp_path: Path) -> None:
    key = SigningKey.generate()
    key_path = tmp_path / "ed25519.raw"
    key_path.write_bytes(key.to_bytes())
    config = _config(tmp_path, signing_key_file=key_path, allow_ephemeral_key=False)
    report = build_site(config)
    payload = json.loads(report.manifest_path.read_text(encoding="utf-8"))
    assert payload["signing_pubkey"] == key.verify_key.to_b64()


def test_signing_key_file_bad_format_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.key"
    bad.write_bytes(b"this is neither 32 raw bytes nor base64\x00\x01\x02")
    config = _config(tmp_path, signing_key_file=bad, allow_ephemeral_key=False)
    with pytest.raises(SignatureError) as excinfo:
        build_site(config)
    assert excinfo.value.error_code == "build.signing_key_file_bad_format"


def test_missing_methodology_raises(tmp_path: Path) -> None:
    config = _config(tmp_path, methodology_path=tmp_path / "nope.md")
    with pytest.raises(IngestError) as excinfo:
        build_site(config)
    assert excinfo.value.error_code == "build.methodology_missing"


def test_cli_main_returns_zero_on_success(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(SIGNING_KEY_B64_ENV, raising=False)
    site_dir = tmp_path / "site"
    rc = build_main(
        [
            "--site-dir",
            str(site_dir),
            "--seed-signals",
            str(REPO_ROOT / "data" / "seed_signals.json"),
            "--methodology",
            str(REPO_ROOT / "METHODOLOGY.md"),
            "--allow-ephemeral-key",
            "--now",
            "2026-06-01T00:00:00Z",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "canonical sha256" in captured.out
    for page in _EXPECTED_PAGES:
        assert page in captured.out


def test_cli_main_returns_one_on_missing_key(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(SIGNING_KEY_B64_ENV, raising=False)
    site_dir = tmp_path / "site"
    rc = build_main(
        [
            "--site-dir",
            str(site_dir),
            "--seed-signals",
            str(REPO_ROOT / "data" / "seed_signals.json"),
            "--methodology",
            str(REPO_ROOT / "METHODOLOGY.md"),
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "build.no_signing_key" in captured.err

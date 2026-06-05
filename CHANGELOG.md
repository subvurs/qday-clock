# Changelog — Q-day Clock

All notable changes, gate fires, and reversals are recorded here.
Per CLAUDE.md §1 (failure-reporting parity), reversals get the same
prominence as advances.

The format is loosely [Keep a Changelog](https://keepachangelog.com/),
with project-specific sections for `Gate fires` and `Reversals`.

## [Unreleased]

### Added
- `site/CNAME` set to `icqubit.com` (Mark-owned domain for the deploy
  target).
- Ed25519 signing keypair generated at
  `~/.config/qday_clock/signing_ed25519.{key,pub}` (mode 0600 on the
  private file). Public key fingerprint:
  `gpg724ZUbG1PHzEI9L/dhcJGkbz5S/251STdeN3P0YU=`. Round-trip
  sign / verify / tamper-detect smoke passed before the key was
  persisted. Private key is **not** in the repo; the public key is
  rendered into `site/about.html` via `{{ pubkey_b64 }}` at deploy
  time (template already wired).
- `data/seed_signals.json` expanded from 3 → **17** axis-1 signals
  (6 hardware / 7 theory / 4 roadmap), date range 2024-09-06 →
  2026-05-22, drawn from the Subvurs Quantum Curator corpus
  (manually classified per CLAUDE.md §3 evidence-class rules — no
  press release labelled as hardware demo).
- Cold-start reading with expanded seeds:
  `clock_score = 0.2607`, `clock_hours = 17.74`, band
  `[11.82, 23.22] h`, 0 gates fired. Axis 1 reading
  `0.463` from 15 independent sources, confidence band
  `[0.30, 0.70]`. Axes 2–5 still floored to the GRI 2024 baseline
  (`0.580`) since their extractors are deferred to v0.2.

### Added — Path B: Curator manifest pipeline wired
- **Curator side**: `quantum_curator/qday_export.py` + `qday-export`
  CLI subcommand (registered in the curator's `[project.scripts]`).
  Filters `raw_articles` to the four Q-day-relevant `ContentTopic`
  values (HARDWARE, ALGORITHMS, ERROR_CORRECTION, CRYPTOGRAPHY),
  builds a `CuratorManifest` (Q-day Clock pydantic schema imported
  directly so the signed shape can never silently drift), signs with
  Ed25519 via `qday_clock.core.signing`. Tight canonicalization
  coupling, loose data coupling — Curator owns the DB, Q-day Clock
  owns the contract. First live export: **204 articles signed,
  pubkey `gpg724ZUbG1PHzEI9L/dhcJGkbz5S/251STdeN3P0YU=`,
  db_row_counts={raw_articles: 448, curated_posts: 28, sources: 18}**.
- **Q-day Clock side**: `qday_clock/ingest/curator_client.fetch_manifest()`
  replaced the v0.2-deferred stub. Loader returns a validated
  `CuratorManifest` with the signature **already verified** (no
  caller forgets to call verify). Six distinct fail-closed
  `error_code`s — one per failure mode, per CLAUDE.md §8:
  - `ingest.manifest_not_found`
  - `ingest.manifest_bad_json`
  - `ingest.manifest_bad_shape` (covers both "not a JSON object" and
    schema-validation failures)
  - `ingest.manifest_unsigned` (default; `require_signature=False`
    is the documented debug-only escape)
  - `ingest.manifest_pubkey_mismatch` (optional pinning via
    `expected_pubkey=`)
  - `ingest.manifest_bad_signature` (covers both tampered body and
    swapped-pubkey-with-original-sig attack)
- **Classifier**: `qday_clock/extract/classifier.py`. Conservative
  manifest→`Signal` router: each article is fed to
  `axis_logical_qubits.extract`; if extraction fails (no numeric
  found, even with keyword hits), no signal is emitted — fail-closed
  per CLAUDE.md §10 (calibrated uncertainty). Evidence class is
  derived from the curator's topic tags via a fixed priority order:
  hardware → policy → cryptography → error_correction → algorithms
  → simulation → research, defaulting to `THEORY`. Signal IDs are
  deterministic (`sig_<sha256(post_id|axis)[:16]>`) so re-running
  the pipeline on the same manifest produces byte-identical signals.
- **Refresh workflow**: `.github/workflows/refresh.yml`. Currently
  `workflow_dispatch`-only — the daily cron line is intentionally
  commented out and v0.2 enables it once Curator publishes a signed
  artifact reliably. Optional `curator_manifest_url` input lets a
  human trigger a seeded refresh against a specific manifest URL.
  Uses the `QDAY_CURATOR_PUBKEY_B64` repo secret for pubkey pinning
  in CI. Opens a PR via `peter-evans/create-pull-request@v6` if
  `site/data/` changed — **never auto-publishes** per plan §F.

### Path B smoke (run 2026-06-04)
- End-to-end: 204-article manifest → classifier → clock pipeline
  produced 4 axis-1 signals (3 hardware, 1 theory).
- Combined reading with 17 seeds + 4 manifest signals:
  `clock_score = 0.2760`, `clock_hours = 17.38`, band
  `[11.82, 23.22] h`, **0 gates fired**. Axis-1 reading
  `0.5238` from 16 independent sources (up from 15 / 0.463 at the
  seeds-only baseline); axes 2–5 still at GRI 2024 floor.
- The +0.06 axis-1 movement is sub-gate-threshold (the
  `MultiSourceConfirmationGate` lands in v0.2 with a 0.15 step
  trigger). Movement is therefore noted but not flagged.

### Tests — Path B
- `tests/ingest/test_curator_client.py` — **11 tests** (3 happy,
  8 negative; one test per distinct `error_code` per CLAUDE.md §8).
  Includes both `tampered_body_fails_verification` and
  `swapped_key_fails_verification` so a refactor can't accept a
  sig under the wrong pubkey.
- `tests/extract/test_classifier.py` — **16 tests** covering
  single-article routing (positive + two fail-conservative
  negatives), all 7 evidence-class priority slots, `signal_id`
  determinism + cross-axis separation, manifest-level routing,
  and a full manifest → classifier → `ClockState` end-to-end.

### Verification — Unreleased (post Path B)
- `pytest tests/ -q` → **92 passed** (was 65; +11 ingest, +16
  classifier).
- `python -m qday_clock.verify.replay --replay tests/golden/manifest_2026_q1.json`
  → `aa5a8c11dd0981ce19a191aa74eadeb7ec51211f7efe7793aff0b5bbee242fe9`
  (byte-identical to v0.1.0 lock — Path B introduced no scoring
  changes).
- The golden fixture uses its own inline signals, so neither the
  seed expansion nor the manifest pipeline perturbs the locked
  replay hash; the larger seed set + classifier path are exercised
  by `tests/test_smoke.py` and the new ingest/extract suites.

### Path B — what's still deferred (still v0.2)
- Curator-side workflow that publishes the signed manifest as a
  release artifact (until that lands, `refresh.yml` is the
  human-triggered fallback).
- Daily cron in `refresh.yml` (uncomment once artifact is reliable).

### Added — Path C: axes 2–5 + remaining 5 gates
- **Axis 2 — physical qubit scaling**: `extract/axis_physical_scaling.py`.
  Log-scale anchor `100 → 10k → 1M → 20M` physical qubits; vendor name
  list (IBM Condor/Flamingo/Kookaburra, Google Sycamore/Willow, IonQ
  Tempo, Quantinuum H/Helios, Atom Computing, PsiQuantum) treated as
  keyword hits even without explicit "qubit" tokens; comma-thousands
  numerics parsed.
- **Axis 3 — resource estimate (Shor + AES/Grover)**: `extract/axis_resource_estimate.py`.
  Gidney-Ekera anchor (20M qubits / 8 h = 0.0); peer-reviewed ≤1M
  qubits or ≤1 h = 0.5; ≤100k qubits or ≤1 min = 1.0. AES-128/Grover
  is a sub-channel folded in at `AES_SUB_WEIGHT = 0.3` so AES alone
  cannot drive the axis past `0.3` ("weakens, not breaks" framing
  from `THREAT_MODEL.md`).
- **Axis 4 — error rate floor**: `extract/axis_error_rate.py`. Anchor
  `1e-2 → 0` (NISQ floor) and `1e-5 → 1.0` (well below the surface
  code threshold), log-linearly interpolated. Tie-break on identical
  numerics is fp-tolerant via `round(pair[0], 9)`; `_ERROR_MAX = 0.05`
  prevents non-error-rate percents (e.g. "5% improvement") from
  registering.
- **Axis 5 — PQC migration (inverse)**: `extract/axis_pqc_migration.py`.
  Severity tiers — mandate (1.0), broad deployment (0.7), pilot (0.5),
  standardization (0.3), bare mention (0.1). Unlike axes 1–4, axis 5
  returns a non-`None` reading on every keyword-gate match (bare
  mentions floor at 0.1 rather than failing out). Combined into the
  clock via subtraction (axis 5 ↑ ⇒ clock score ↓).
- **Classifier wiring**: `extract/classifier.py` now routes every
  article through all five axes (`_PER_ARTICLE_ROUTERS` tuple). A
  single article may produce signals on multiple axes — a hardware
  release citing both a qubit count and a gate error is a normal
  multi-axis case.
- **`MultiSourceConfirmationGate`** (`score/gates.py`): proposed
  axis-step > `min_step` (0.15) requires ≥ `min_sources` (2) distinct
  `source` strings within a `window_days` (30 d) rolling window,
  otherwise the gate fires with `multiplier = 0.5`. Step comparison
  uses `+ 1e-9` tolerance so `0.45 − 0.30 = 0.15…02` lands on the
  "no confirmation required" side at the threshold (boundary test
  pinned in `tests/adversarial/test_multi_source_confirmation_gate.py`).
- **`RoadmapWeightCapGate`** (`score/gates.py`): caps signals with
  `evidence_class == ROADMAP` to a normalized contribution of at most
  `cap` (0.3). Hardware / theory / simulation / policy / survey
  signals pass through unchanged — preserves the CLAUDE.md §3
  evidence-class asymmetry.
- **`StaleSignalGate`** (`score/gates.py`): full weight up to
  `fresh_days` (18·30 ≈ 18 months), linear decay to zero across the
  window `[fresh_days, stale_days]` (36·30 ≈ 36 months), zero
  contribution beyond. Evidence-class agnostic — pure freshness policy
  (the asymmetry is RoadmapWeightCapGate's job).
- **`AntiStiffnessGate`** (`score/gates.py`): any single-refresh axis
  step > `max_step` (0.4) triggers `multiplier = 0.5`. Fires on
  magnitude alone, independent of source count — distinguishes it
  from MultiSourceConfirmationGate. Both gates can fire on the same
  step. Symmetric: positive and negative jumps treated equally (§1
  parity).
- **`ContrastSaturationGate`** (`score/gates.py`): caps any single
  signal's share of an axis to `cap` (0.5). Distinct from
  SingleSourceCapGate (which caps per source name): this caps
  per-signal so one outlier observation from a unique source cannot
  dominate.
- **`GateBundle`**: now wires `multi_source`, `roadmap_cap`,
  `stale_signal`, `anti_stiffness`, `contrast_saturation` alongside
  the v0.1 set. `all_verdicts(...)` gained optional
  `axis_step_proposals` (per-axis step-changes for the two step gates)
  and `per_signal_share` (per-signal share for ContrastSaturation),
  and runs StaleSignalGate per signal when a `now=` clock-time is
  supplied. Backwards-compatible: callers using only v0.1 gates
  produce identical verdict lists.
- **Adversarial fixtures**: 5 new test files under
  `tests/adversarial/`, one per gate — 7 / 5 / 9 / 6 / 7 tests
  respectively (`MultiSourceConfirmation` / `RoadmapWeightCap` /
  `StaleSignal` / `AntiStiffness` / `ContrastSaturation`). All include
  boundary cases and §1 parity (negative-step + reversal) checks
  where applicable.

### Path C — gate-design notes
- The two step gates (`MultiSourceConfirmation`, `AntiStiffness`) are
  semantically complementary, not redundant. MultiSourceConfirmation
  fires on source-count, AntiStiffness fires on magnitude. A jump of
  0.55 from two independent sources still trips AntiStiffness; a jump
  of 0.20 from one source still trips MultiSourceConfirmation. The
  current production stack runs both.
- `ContrastSaturationGate` and `SingleSourceCapGate` similarly split
  responsibility: source-cap protects against one vendor producing
  many signals; contrast-saturation protects against one signal of
  extreme magnitude (potentially from a different source than the
  others). Either can fire without the other.
- The AntiStiffness / ContrastSaturation gates are *Q-day-shaped*
  analogs of the gh_eval gates of the same name. The gh_eval versions
  consume `MetricInputs` (`std_d`, `extras["saturation_rate"]`) shaped
  for OpenEvolve trajectories. Q-day has no trajectory, so I re-shaped
  the inputs onto Q-day's natural data model (axis-reading step;
  per-signal axis share) while preserving the semantic intent. This
  matches the pattern in `gh_eval/adapters/{nyx,impax}.py` where
  adapters re-skin the abstract gate I/O for their domain.

### Verification — Path C
- `pytest tests/ -q` → **201 passed** (was 92 after Path B; +22
  adversarial across the 5 new gates, +classifier and extractor
  coverage for axes 2–5).
- `pytest tests/golden/ -v` → **2 passed** (golden replay
  byte-for-byte + clock-hours range).
- Golden canonical hash unchanged:
  `aa5a8c11dd0981ce19a191aa74eadeb7ec51211f7efe7793aff0b5bbee242fe9`.
  The golden fixture uses inline signals on axis 1 only, so it is
  insensitive to axes-2–5 wiring and to gates that have not yet fired
  on a real signal. This is the intended behavior: a hash drift here
  would indicate a v0.1 scoring regression, not v0.2 scope expansion.

### Added — Path C: gate integration (production scoring path)
- **Gate wiring**: `score/clock.compute_clock_state` now instantiates
  the full v0.2 gate suite (`StaleSignalGate`, `RoadmapWeightCapGate`,
  `ContrastSaturationGate`, `MultiSourceConfirmationGate`,
  `AntiStiffnessGate`) alongside the v0.1 `SingleSourceCapGate`. Before
  this entry, the v0.2 gates were unit-tested at the gate boundary but
  never reachable from the production scoring path — Goodhart
  resistance was theoretical only. Unit-test ∧ integration-test now
  jointly demonstrate each gate is both correct in isolation and
  wired into the live pipeline.
- **`compute_clock_state` signature**: gained two kwargs.
  - `now: datetime | None = None` — reference clock-time for
    time-dependent gates (`StaleSignalGate`,
    `MultiSourceConfirmationGate`). When `None`, the stale gate is
    skipped entirely (forever-deterministic replay path);
    multi-source uses `utcnow()` only if step-change observers run at
    all.
  - `previous_axes_readings: dict[str, float] | None = None` — when
    supplied, step-change gates (`MultiSourceConfirmationGate`,
    `AntiStiffnessGate`) run as observers and record verdicts without
    retroactively editing axis values. Matches the gh_eval pattern of
    record-not-mutate for review-class gates.
- **`aggregate_axis` pipeline**: extended from a single source-cap
  step into a 5-stage pipeline, each stage preserving the symmetric
  numerator/denominator invariant (a `multiplier == 1.0` step is a
  true no-op):
  1. per-signal pre-multipliers (`stale_gate × roadmap_cap_gate`);
     stale-gate skipped when `now is None`
  2. per-source share computed against the pre-multipliers
  3. per-source `SingleSourceCapGate` (v0.1 behavior, unchanged)
  4. per-signal share fed to `ContrastSaturationGate`
  5. final aggregation stacks all three multiplier categories
     symmetrically
- **Forever-determinism**: `tests/golden/test_golden_replay.py` and
  `qday_clock/verify/replay.py` both now pin `now=observed_at` from
  the fixture. Without this, `StaleSignalGate` would silently begin
  decaying signals roughly 18 months after the fixture's observed_at
  date (~2027-09-29 for `manifest_2026_q1.json`) and drift the
  canonical hash. Per CLAUDE.md §7, the test stays
  forever-deterministic by construction, not by luck.
- **Symmetric multiplier semantic preserved**: the existing
  `SingleSourceCap` convention — multipliers apply to both numerator
  AND denominator — is held for every v0.2 gate. For an axis composed
  of a single signal, the gate's multiplier cancels out exactly: the
  *reading* is unchanged but the verdict is recorded in `gates_fired`.
  This is the explicit contract; an integration test pins it.

### Tests — Path C (gate integration)
- `tests/score/test_clock_gate_integration.py` — **9 tests** locking
  the wiring contract:
  - `test_roadmap_cap_gate_fires_through_pipeline` — roadmap
    `normalized=0.9` triggers the cap with a corroborating non-roadmap
    signal so source-cap doesn't also confuse the assertion
  - `test_roadmap_cap_gate_dampens_axis_reading` — single-signal axis
    proves the symmetric numerator/denominator contract (reading
    unchanged, verdict recorded)
  - `test_stale_signal_gate_fires_through_pipeline` — 2-year-old
    signal flagged when `now` is supplied
  - `test_stale_signal_gate_skipped_when_now_is_none` — the
    forever-deterministic replay path: no `now` means no stale gate
  - `test_contrast_saturation_fires_when_one_signal_dominates` —
    one signal at full `normalized=1.0` with near-silent companions
    trips the per-signal share cap
  - `test_anti_stiffness_fires_on_large_step` — 0.10 → 0.85 (Δ=0.75 >
    0.4) trips the magnitude gate
  - `test_multi_source_confirmation_fires_on_unconfirmed_step` —
    single-source step > 0.15 with < 2 sources trips multi-source
  - `test_step_change_gates_silent_without_previous_readings` —
    neither step gate runs without `previous_axes_readings`
  - `test_apply_gates_false_silences_all_v02_gates` — the only
    legitimate way to obtain a strictly-pre-gate reading is
    `apply_gates=False`; verifies `gates_fired == []` even when every
    gate's triggering pathology is present

### Verification — Path C (gate integration)
- `pytest tests/ -q` → **210 passed** (was 201; +9 integration tests).
- `python -m qday_clock.verify.replay --replay tests/golden/manifest_2026_q1.json`
  → `aa5a8c11dd0981ce19a191aa74eadeb7ec51211f7efe7793aff0b5bbee242fe9`
  (byte-identical to the v0.1.0 lock). The golden fixture has five
  hardware signals at the same `observed_at` with distinct sources,
  max per-signal share ≈ 0.21, and no previous reading; with
  `now=observed_at` no v0.2 gate fires, `gates_fired == []`, and the
  canonical body is preserved. Hash preservation is structural, not
  coincidental — re-derivable from the fixture parameters.

### Added — Path C: v0.2 gate-fire golden fixture
- `tests/golden/manifest_2026_v02.json` — second locked golden input
  fixture. Covers all 5 axes (10 signals total) at
  `observed_at = 2026-06-01` and is built to deterministically trigger
  the v0.2 gates that the v0.1 fixture by design does **not** fire:
  - **RoadmapWeightCapGate**: one roadmap-evidence signal on axis 1
    (`vendor-C-blog`, normalized 0.9) above the 0.3 cap → cap
    multiplier 0.3333 applied; verdict in `gates_fired`.
  - **StaleSignalGate**: one hardware signal on axis 1
    (`vendor-D-paper`, archival d=3 demo) with explicit per-signal
    `observed_at = 2024-06-01` ≈ 730 days before fixture `now`, inside
    the [`fresh_days=540`, `stale_days=1080`] decay window → linear
    decay multiplier ≈ 0.351; verdict in `gates_fired`.
  - **ContrastSaturationGate** (incidental): fires 4× on single-signal
    axes 4 and 5 and on two logical-qubits signals where the per-axis
    share crosses 0.5. Recorded but not the headline contract.
- Loader change — both `qday_clock/verify/replay.py` and
  `tests/golden/test_golden_replay.py` now honor an optional per-signal
  `observed_at` field; signals without it continue to inherit the
  fixture-wide `observed_at` exactly as before. The v0.1 manifest does
  not use the field, so the v0.1 golden hash
  `aa5a8c11dd0981ce19a191aa74eadeb7ec51211f7efe7793aff0b5bbee242fe9`
  is byte-preserved. The override exists so the stale signal can be
  aged without shifting `now`, keeping `compute_clock_state` invocations
  in golden tests forever-deterministic.
- `tests/golden/test_golden_replay_v02.py` — three pinned tests:
  - `test_golden_replay_v02_byte_for_byte` locks the canonical hash
    `9d20017e0e938d4b4a98e6d47ba545f2c73ea5c074d9973288408c2c602d0d7d`
    (RFC 8785 canonical body of the unsigned `ClockState` produced by
    replaying `manifest_2026_v02.json` with `now = observed_at` and
    `generated_at` pinned).
  - `test_golden_replay_v02_required_gates_fire` locks the Goodhart
    contract (CLAUDE.md §9): `RoadmapWeightCapGate` ≥ 1 fire and
    `StaleSignalGate` ≥ 1 fire on this fixture. A future refactor that
    silently disconnects either gate from `compute_clock_state` will
    trip this assertion even if the hash happens to coincide.
  - `test_golden_replay_v02_clock_hours_in_range` — sanity:
    `0 ≤ clock_hours ≤ 24`, `0 ≤ clock_score ≤ 1`, and no axis is
    cold-start (closes a hole the v0.1 fixture cannot cover since it
    only populates axis 1).
- Replay sanity (Path C v0.2 fixture):
  `clock_hours = 20.70`, `clock_score = 0.1375`, 6 gate verdicts in
  `gates_fired` (1 RoadmapWeightCapGate + 1 StaleSignalGate +
  4 ContrastSaturationGate). The relatively low clock_score is
  consistent with the fixture's mostly-modest normalized values across
  axes 2–5 and the stale-gate decay multiplier dragging the only
  high-value axis-1 signal down by ≈ 65%.

### Verification — Path C (v0.2 golden fixture)
- `pytest tests/ -q` → **213 passed** (was 210; +3 for the new v0.2
  golden test). v0.1 golden hash unchanged at
  `aa5a8c11dd0981ce19a191aa74eadeb7ec51211f7efe7793aff0b5bbee242fe9`.
- `python -m qday_clock.verify.replay --replay tests/golden/manifest_2026_v02.json`
  → `9d20017e0e938d4b4a98e6d47ba545f2c73ea5c074d9973288408c2c602d0d7d`
  (byte-stable across runs).
- Both golden hashes are now pinned independently — v0.1 anchors the
  pre-gate path (no triggering pathology, no verdict), v0.2 anchors
  the gate-reachable path (designed pathologies, verdicts recorded).

### Path C — what's still deferred (still v0.2)
- Curator-side workflow that publishes the signed manifest as a
  release artifact (still v0.2 — Path B section above).
- Daily cron in `refresh.yml`.
- `dashboard.html` + `sources.html` (UI layer; v0.2 plan §C).

## [0.1.0] — MVP scaffold

### Added
- Repository structure under `public_interest/qday_clock/`
- `README.md`, `LICENSE` (MIT), `METHODOLOGY.md`, `THREAT_MODEL.md`
- Core package: `schemas`, `canonical` (RFC 8785), `signing` (Ed25519),
  `errors`, `time`
- Ingest: `seed_signals.py` (MVP — manual seed; Curator integration
  stubbed but not wired)
- Extract: `axis_logical_qubits.py` (1 of 5 axes live)
- Score: `weights`, `axes`, `clock`, `gri_baseline`, `mosca` (calculator
  only), `gates` with **StaticPointGate**, **SingleSourceCapGate**,
  **ThresholdGuard**
- Render: `svg_clock`, `manifest`, templates for `index.html`,
  `methodology.html`, `about.html`
- Tests: core unit, 1 golden fixture, 3 adversarial fixtures
  (one per active gate), forbidden-language lint
- CI: `ci.yml`, `pages-deploy.yml`
- Docs: `ARCHITECTURE.md`, `GATE_CATALOG.md`, `SIGNAL_CATALOG.md`
- `qday_clock.verify.replay` CLI with `--check <signed.json>` and
  `--replay <fixture.json>` modes (used by `ci.yml`)

### Verification — v0.1.0 lock
- Test suite: **65 passed** (`pytest tests/ -v`). The golden-bootstrap
  branch in `tests/golden/test_golden_replay.py` (active only when
  `EXPECTED_CANONICAL_HASH is None`) is dormant; re-lock requires
  explicitly clearing the constant per CLAUDE.md §7.
- Golden canonical hash locked at
  `aa5a8c11dd0981ce19a191aa74eadeb7ec51211f7efe7793aff0b5bbee242fe9`
  (RFC 8785 canonical form of the unsigned `ClockState` body produced
  by `tests/golden/manifest_2026_q1.json`, with `generated_at` pinned
  to `2026-04-01T00:00:00+00:00`). Drift in this hash means either
  (a) a scoring change that needs a CHANGELOG entry, or (b) a
  canonicalization / schema regression.
- `python -m qday_clock.verify.replay --replay tests/golden/manifest_2026_q1.json`
  reproduces the locked hash byte-for-byte.

### Deferred to v0.2
- Curator manifest export integration
- Remaining 4 axes (physical scaling, resource estimate, error rate,
  PQC migration)
- `dashboard.html` + `sources.html`
- Remaining 5 gates: `MultiSourceConfirmationGate`,
  `RoadmapWeightCapGate`, `StaleSignalGate`, `AntiStiffnessGate`,
  `ContrastSaturationGate`
- Daily refresh workflow with human-reviewed auto-PR
  (`.github/workflows/refresh.yml`)

### Deferred to v0.3
- Interactive Mosca calculator on dashboard
- History visualization
- RSS / email digest of clock changes
- Public API endpoint serving `clock_state.json` with CORS

## Gate fires

(Each entry: gate name, timestamp, signal id(s) that triggered it,
prior axis reading, post-gate axis reading, link to the manifest hash.)

_None yet — MVP not yet anchored to a live corpus._

## Reversals

(Each entry: what we previously said, what we now believe, why, and
which signals were retracted or reinterpreted.)

_None yet._

## Threat-model revisions

(Per `THREAT_MODEL.md`: a revision to the threat model is a breaking
change. Each revision lives here with full rationale.)

_None yet._

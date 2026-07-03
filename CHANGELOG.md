# Changelog — Q-day Clock

All notable changes, gate fires, and reversals are recorded here.
Per CLAUDE.md §1 (failure-reporting parity), reversals get the same
prominence as advances.

The format is loosely [Keep a Changelog](https://keepachangelog.com/),
with project-specific sections for `Gate fires` and `Reversals`.

## [Unreleased]

### Reversal — axis-5 inverse cold-start floor 0.58 → 0.0 (2026-07-03)

Reverses the "keep GRI floor (status quo)" decision recorded in the
2026-06-29 token-boundary entry (see "Flagged for review" block below,
lines under *Fixed — keyword token-boundary matching*). That entry
flagged the 0.58 cold-start floor as "an aggressive default for an
inverse/defensive axis" and parked the fix as "the next decision to
make." This is that decision.

**The defect.** The cold-start fallback applied a single GRI-anchored
floor (`baseline_axis_floor` = 0.58 for GRI-2024 median CRQC year 2034)
to *every* axis with no live signals. That floor is threat-neutral on
the four **additive** axes (1–4) but threat-**optimistic** on axis 5
(PQC migration), which is *subtracted* at coefficient 0.5. An axis-5
cold-start of 0.58 therefore subtracted `0.5 × 0.58 = 0.29` from every
reading with no PQC-deployment evidence behind it — crediting the clock
for defensive readiness we cannot observe and backing it off ~7 hours.

**The fix.** Cold-start is now **sign-aware** (`score/clock.py`):
additive axes still fall back to the GRI floor (0.58); the inverse
axis 5 falls back to **0.0** ("no evidence of PQC migration → assume
none deployed"), the threat-conservative default. Documented in
METHODOLOGY.md §3 (new "Cold-start fallback" clause under *Combination*).

**Live-manifest impact** (informational; manifest is not committed
data). Live 2026-07-03 manifest (298 articles), `observed_at =
2026-07-03`, axis 5 cold-start (n=0):

| | Before (0.58 floor) | After (0.0 floor) |
|---|---|---|
| pqc_migration reading | 0.5800 | **0.0000** |
| clock_score | 0.0549 | **0.3449** |
| clock_hours | 22.68h | **15.72h** |

The ~7-hour move is the removal of the unevidenced backoff, not new
threat signal. Axes 1–4 are unchanged; only the inverse-axis cold-start
default changed.

**Golden replay re-lock (CLAUDE.md §7).** The `manifest_2026_q1.json`
fixture leaves axis 5 cold-start, so its reading drops 0.58 → 0.0,
removing the 0.29 subtraction and moving the fixture clock 17.94h →
10.98h. Re-locked per the documented bootstrap path:

- `tests/golden/test_golden_replay.py::EXPECTED_CANONICAL_HASH`
  re-locked: `696887e1…` → `7b22b0a2d51e4fc9937b95da9634f9dc9c4c8cc2cd70f3b3ac64660081428493`.
- `tests/golden/test_golden_replay_v02.py` **unchanged** — the v0.2
  fixture carries a live axis-5 signal, so it never hits the cold-start
  path (verified: v02 replay still green).
- `tests/golden/expected_state.json` regenerated (deterministic
  RFC-8785 snapshot of the q1 replay; not read by any test).

**Tests.** `tests/score/test_clock.py::test_cold_start_is_sign_aware`
added (locks additive-axes = GRI floor, inverse-axis = 0.0). Full suite
245 passing (was 244).

### Changed — refresh.yml v0.10: collapse review to a one-step merge gate (2026-06-30)
v0.9's formal GitHub review-request added friction it was never meant to:
GitHub forbids an account approving its own PR, so review had to come from
a second identity (`MarsVMondo`), and a formal "Approve" doesn't publish —
it left a separate manual merge. That is two identities and two clicks to
update a static site. `main` is unprotected, so `subvurs` can merge its own
auto-refresh PR directly. v0.10 therefore:

- **Removes** `reviewers: MarsVMondo` / `assignees: MarsVMondo` from the
  `peter-evans/create-pull-request` step. No formal review is requested.
- **Keeps** the daily SMTP email as the sole notification channel; reworded
  body now says "review, then click Merge to publish" (the merge click is
  the entire human gate) and notes that closing the PR cancels the day's
  update (tomorrow's run reopens a fresh one).
- **Unchanged**: SMTP secrets, optional `REVIEW_NOTIFY_EMAIL` recipient
  override, fail-loud-on-missing-secret behaviour (CLAUDE.md §8), and the
  no-auto-merge stance — the human merge click stays the deliberate gate.

Net flow: daily run opens PR → email lands in the SMTP inbox with the
reading + PR link → human clicks Merge → `pages-deploy.yml` publishes to
icqubit.com. One identity, one click. `MarsVMondo` collaborator access is
now unused by the workflow (left in place; harmless).

### Fixed — keyword token-boundary matching + axis-4 fidelity admission (2026-06-29)

Two extractor-precision fixes. No package version bump; no golden-replay
hash change (the golden fixtures reconstruct `Signal` objects directly
from JSON and never run the keyword classifier, so these changes cannot
shift the locked v0.1/v0.2 hashes — verified, both replay tests still
green).

- **Fix A — token-boundary keyword gates (all 5 axes).** Every axis
  `matches()` now routes its keyword tuple through the new
  `keywords.keyword_hit`, which matches each keyword as a token
  (`(?<![A-Za-z0-9])…(?![A-Za-z0-9])`, case-insensitive) instead of a
  raw `kw in blob` substring test. Punctuation still counts as a
  boundary, so `CRYSTALS-Kyber`, `SPHINCS+`, `FIPS 203`, `RSA-2048`,
  `ecc-256` keep matching; substring accidents (`shor`→"shorten",
  `ecc`→"Rebecca", `crystals`→"quasicrystals") no longer fire.

- **Fix B — admit `fidelity` into `ERROR_RATE_KEYWORDS`.** The axis-4
  extractor already converts a reported fidelity `F` to an implied error
  `1 − F`, but fidelity-only articles never passed the keyword gate.
  Adding `fidelity` makes that conversion path reachable from the live
  manifest.

**Live-manifest clock impact (informational; manifest is not committed
data).** Reproduced with `simfix.py` against the 2026-06-29 curator
manifest (190 articles), `observed_at = 2026-06-29T12:00Z`:

| Axis | Before (substring) | After (token-boundary + fidelity) |
|---|---|---|
| logical_qubits | 0.4603 (n=16) | 0.4603 (n=16) — unchanged |
| physical_scaling | 0.0148 (n=2) | 0.0148 (n=2) — unchanged |
| resource_estimate | 0.5800 GRI floor (n=0) | 0.5800 GRI floor (n=0) — unchanged |
| error_rate | 0.5800 GRI floor (n=0) | **0.1890 (n=3)** — Fix B admits 3 fidelity articles |
| pqc_migration | 0.1000 (n=1) | **0.5800 GRI floor (n=0)** — Fix A drops 1 false positive |
| **clock_score** | **0.4153 / 14.03h** | **0.0580 / 22.61h** |

  The single pre-fix pqc_migration signal was a `crystals`-in-
  "quasicrystals" false positive on a materials-science article ("New
  quantum algorithm solves impossible materials problem"). Removing it
  is correct.

  **Flagged for review (rigor §1/§11):** the large clock drop is
  dominated by the **inverse** pqc_migration axis falling back to the
  GRI cold-start floor of 0.58, which is then subtracted at coefficient
  0.5. The spurious 0.10 reading had been masking a pre-existing
  design question — a 0.58 cold-start floor is an *aggressive default
  for an inverse/defensive axis* (an axis with no PQC-deployment
  evidence arguably warrants 0 defensive credit, not 0.58). Per the
  "keep GRI floor (status quo)" decision this is **not** changed here;
  it is recorded as the next decision to make. Fix B's axis-4 reading
  (0.189) is below the 0.58 floor it replaces, also pulling the clock
  down — that is the honest best-evidence error-rate reading, not a
  regression.

- **Tests**: `tests/extract/test_keyword_boundary.py` (9 new) covering
  substring rejection, punctuation-boundary acceptance, case
  insensitivity, the wired axis gates, and fidelity admission/conversion.
  Full suite 244 passing (was 235).

### Added — refresh.yml v0.9: active daily-review notification (2026-06-29)
The daily refresh now actively notifies a human reviewer instead of
relying on them to remember to check the repo. Workflow-only change (no
Python code, no package version bump). Two channels added on top of the
existing `requires-review`-labelled PR:

- **GitHub native review request** — `reviewers: MarsVMondo` +
  `assignees: MarsVMondo` on the `peter-evans/create-pull-request` step.
  The auto-refresh PR is authored by the DEPLOY_TOKEN owner `subvurs`,
  so `MarsVMondo` (read access — can review/approve, cannot merge) is an
  eligible reviewer. GitHub forbids requesting review from a PR's own
  author, which is why the reviewer is deliberately not `subvurs`.

- **SMTP email** — new `Email daily review request` step
  (`dawidd6/action-send-mail@v3`, Gmail SMTP 465/SSL) sends the day's
  `clock_score` / `clock_hours` + PR link + review checklist. Gated on
  `steps.diff.outputs.changed == 'true'` AND a non-empty
  `steps.cpr.outputs.pull-request-number`, so no email is sent on a
  no-change day or with a dead PR link. The recompute step now carries
  `id: compute` and writes `clock_score` / `clock_hours` to
  `$GITHUB_OUTPUT` so the email can quote them.

  **New repo secrets required** (this repo does not yet have them):
  `SMTP_EMAIL` and `SMTP_APP_PASSWORD` (Gmail app-password, same pattern
  as `subvurs/quantum-curator`). Optional repo variable
  `REVIEW_NOTIFY_EMAIL` overrides the recipient; absent it the mail goes
  to `SMTP_EMAIL` itself. Per CLAUDE.md §8 the email step fails loudly
  if the secrets are unset rather than skipping silently — until they
  are added, the GitHub review-request channel still works on its own.

- **Approval model unchanged**: approval is the gate, not an auto-merge
  trigger. After review the PR is merged manually by the `subvurs`
  account; `pages-deploy.yml` then renders the committed state to
  icqubit.com. Nothing auto-publishes (plan §F).

### Added — Path H: daily cron enabled + first end-to-end smoke (2026-06-27)
Two workflow-only PRs (no package version bump — no Python code shipped):

- **PR #1** ([qday-clock#1](https://github.com/subvurs/qday-clock/pull/1),
  branch `qday-clock/enable-daily-cron-v02`, squash-merged
  2026-06-27T00:05:12Z as commit `d1bd6b6a`): uncommented the
  `schedule: cron: "0 8 * * *"` line in `refresh.yml`. First scheduled
  fire 2026-06-27 08:00 UTC.

  Scope cut, recorded per rigor §1: the cron path still runs SEEDS-ONLY
  because the `Fetch Curator manifest` step is gated on
  `inputs.curator_manifest_url != ''`, which is empty under cron. A
  follow-on PR will default that input to
  `https://raw.githubusercontent.com/subvurs/quantum-curator/manifest/curator_manifest.json`
  so the cron path actually consumes the upstream manifest. Two-PR
  split is intentional — each behavior change reviewable on its own,
  and the URL default waited until after the smoke proved the URL
  serves content.

- **PR #2** ([qday-clock#2](https://github.com/subvurs/qday-clock/pull/2),
  branch `qday-clock/fix-workflow-cwd`, squash-merged
  2026-06-27T00:20:22Z as commit `cc320f8`): removed the stale
  `defaults: run: working-directory: public_interest/qday_clock` block
  from `refresh.yml`. It was a leftover from when `qday_clock` lived
  as a subdirectory of the Subvurs monorepo; the standalone repo has
  `qday_clock/` at the root. Discovered by the K11 smoke (run
  `28272363714` failed at `Install Q-day Clock` with "No such file or
  directory" for that path). PR CI had never caught this because PR
  CI only runs the tests job, not the refresh job.

### End-to-end smoke (run 2026-06-27 — Curator → manifest branch → refresh.yml)
This is the first time the full **K11 → `subvurs/quantum-curator`
manifest branch → `raw.githubusercontent.com` → `refresh.yml`
workflow_dispatch → signature verify → `compute_clock_state`** path
has run live.

| Stage | Evidence |
|---|---|
| K11 `quantum-curator qday-export` | 167 articles, 240801 bytes, local `verify_payload=True`; curator commit `55efcfa5c591` |
| Force-push → manifest branch | commit `33152bb` on `subvurs/quantum-curator` (first push, branch created at that moment) |
| `raw.githubusercontent.com` GET | HTTP 200, byte-identical 240801 bytes |
| `refresh.yml` workflow_dispatch | run [28272654436](https://github.com/subvurs/qday-clock/actions/runs/28272654436) — Install + Fetch + Recompute + Diff all green in 23 s |
| Signature verified vs `QDAY_CURATOR_PUBKEY_B64` | log line: `refresh: ingested manifest with 167 articles, commit=55efcfa5c591` (no `VerificationError`) |
| Clock state | `clock_score = 0.4153`, `clock_hours = 14.03` |
| Refresh PR opened? | No — recomputed `site/data/clock_state.json` is byte-identical to current `main` (deterministic; expected outcome, not a fault) |

Curator-side pubkey: `w2jrKwsAQoSBOq8wgqEVIQd0gzs56/KmMBLFuXUy+d0=`
(distinct from the Q-day Clock state-signing key
`gpg724ZUbG1PHzEI9L/dhcJGkbz5S/251STdeN3P0YU=` documented above — two
separate concerns, two separate secrets).

### What this leg confirms

1. The `qday-export` → `fetch_manifest` → `classify_manifest` pydantic
   contract holds on the wire: 167 articles round-tripped through
   canonical-JSON, Ed25519 signature, force-push, raw fetch,
   `verify_payload`, classification, scoring.
2. The pinned-pubkey defense works end-to-end: the workflow secret
   matches the K11 signing key, so an attacker swapping the manifest
   branch content (or compromising a different curator instance) would
   trip `VerificationError` at `fetch_manifest` line 1 — before any
   axis reading is touched.
3. The orphan-branch + force-push pattern (one-commit, single-file
   `curator_manifest.json` on a dedicated branch) is the right
   distribution shape: `gh-pages` deploy of the Crier remains
   unaffected, history stays at exactly one commit, and
   `raw.githubusercontent.com` serves the JSON immediately on push.

### Open follow-ups (next session)

- Default `curator_manifest_url` so the cron path consumes the
  manifest. Now that the URL is provably serving content, the
  precondition is cleared.
- Watch the first scheduled cron fire (2026-06-27 08:00 UTC) — should
  log `refresh: no manifest URL provided; seeds-only refresh` and
  diff clean (no PR), unless the cron and the smoke disagree on
  the seed-only baseline, in which case there's an axis-drift bug
  worth running down.

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

### Added — Path C: v0.2 UI layer (`dashboard.html` + `sources.html`)
- `site/dashboard.tmpl.html` — 5-axis dashboard with:
  - per-axis reading + weight + confidence band + signal counts table,
  - one `<details>` drill-down per axis listing
    `contributing_signal_ids` and linking to the per-signal anchor on
    `sources.html`,
  - gates-fired table sourced from `state.gates_fired` (the same gate
    records that the golden v0.2 fixture locks),
  - Mosca's-inequality informational panel (no probability or
    calendar-date framing — informational, anchored to the GRI
    baseline as the only stated `z` reference),
  - meta block: clock score, confidence band, GRI baseline,
    generated-at timestamp, schema version.
- `site/sources.tmpl.html` — per-signal provenance page with:
  - rendered table keyed by `signal_id` (each row has
    `id="{{ signal_id }}"` so `dashboard.html` anchor links resolve),
  - explicit evidence-class tag per signal (`hardware`, `roadmap`,
    `policy`, etc.) matching CLAUDE.md §3,
  - URL-bearing signals link to the underlying article;
    URL-less signals render plain titles,
  - empty-signal-list path renders an honesty notice
    rather than a blank page (CLAUDE.md §8).
- `qday_clock/render/templates.py`:
  - new `render_dashboard(state, template_dir=None)` and
    `render_sources(state, signals, template_dir=None)` following the
    existing `render_index` / `render_methodology` / `render_about`
    contract (Jinja2 `StrictUndefined`, file loader rooted at `site/`),
  - per-axis labels centralized in module-level `_AXIS_LABELS` so the
    templates stay declarative,
  - `render_sources` sorts by `(axis, -normalized_value, signal_id)`
    for deterministic output — important for forever-deterministic
    rendering and for diffing future readings.
- `tests/render/test_jinja_smoke.py`:
  - `test_render_dashboard_smoke` — asserts all 5 axes render, PQC
    axis is flagged as inverse, Mosca panel present,
    `sources.html#…` drill-down anchors emitted.
  - `test_render_sources_smoke` — asserts each signal renders with
    its ID anchor, evidence-class tag is visible, URL-bearing signals
    get a link.
  - `test_render_sources_handles_empty_signal_list` — guards the
    honesty-notice path so a future regression doesn't silently
    render a blank sources page.
- `tests/test_forbidden_language.py` extended to lint
  `site/dashboard.tmpl.html` and `site/sources.tmpl.html` against the
  prediction / marketing-language pattern set.

### Verification — Path C (v0.2 UI layer)
- `python3 -m pytest tests/` — **218 passed** (was 213; +3 render
  smokes + 2 forbidden-language lint cases).
- v0.1 and v0.2 golden replays still hash-locked
  (`aa5a8c11…` and `9d20017e…` unchanged).
- Forbidden-language lint passes on both new templates without any
  allow-list additions (the templates use "this is a reading, not a
  prediction" phrasing, which is already in `ALLOW_CONTEXTS`).

### Path C — what's still deferred (still v0.2)
- Curator-side workflow that publishes the signed manifest as a
  release artifact (still v0.2 — Path B section above).
- Daily cron in `refresh.yml`.
- A pipeline wire-up that emits `dashboard.html` + `sources.html` from
  the same `compute_clock_state` run that produces
  `data/clock_state.json` (the templates and renderers are live; only
  the build-step entry point is unwritten).

### Added — Path D: build-step entry point (`qday_clock.build`)
- New module `qday_clock/build.py` wires the full pipeline
  (ingest → score → sign → render) behind one function and one CLI:
  - `BuildConfig` — dataclass: `site_dir`, `seed_signals_path`,
    `methodology_path`, `signing_key_file`, `signing_key_b64_env`
    (default `QDAY_SIGNING_KEY_B64`), `allow_ephemeral_key`, `now`,
    `extra_signals`.
  - `BuildReport` — dataclass: `state`, `canonical_sha256`,
    `manifest_path`, `history_path`, `rendered_pages`,
    `used_ephemeral_key`.
  - `build_site(config)` — runs the full pipeline and emits all five
    pages (`index.html`, `methodology.html`, `about.html`,
    `dashboard.html`, `sources.html`) plus `data/clock_state.json`
    (signed) and an appended line in `data/history.jsonl`.
  - `main(argv)` — argparse CLI returning `0` on success and `1` on
    a missing-signing-key fail-closed event. CLI flags mirror the
    config fields; `--allow-ephemeral-key` is the documented escape
    hatch for local dev / smoke runs.
- **Fail-closed signing-key resolution order**, in priority:
  1. `--signing-key-file` (accepts either raw 32 bytes OR base64-text
     contents — `build.signing_key_file_bad_format` if neither).
  2. `QDAY_SIGNING_KEY_B64` env var (base64).
  3. Ephemeral key, **only** if `--allow-ephemeral-key` is set;
     `BuildReport.used_ephemeral_key=True` surfaces this so a CI run
     can refuse to publish ephemeral-signed artifacts.
  4. Otherwise: `SignatureError(error_code="build.no_signing_key")`.
- **Step-change gate path wired**: when a previous
  `site/data/clock_state.json` already exists, `build_site` parses
  its `axes` block into `previous_axes_readings` and passes it to
  `compute_clock_state` so the MultiSourceConfirmationGate +
  AntiStiffnessGate observers fire on day-over-day diffs. A
  malformed previous state raises
  `IngestError(error_code="build.previous_state_bad_json")` —
  per CLAUDE.md §8, a corrupted artifact is not silently demoted to
  a cold start (that would mask a real corruption event and disable
  step-change gates without telling anyone).
- **Render reads the signed payload back**, not the in-memory
  `ClockState`. The renderer is fed `ClockState.model_validate(
  signed_payload_without_sig_fields)` so the rendered footer can
  never drift from the signed body's canonical-sha attestation in
  about/dashboard pages.
- New error codes (all carry `error_code` per existing pattern):
  - `build.no_signing_key`
  - `build.signing_key_file_missing`
  - `build.signing_key_file_bad_format`
  - `build.signing_key_env_bad_base64`
  - `build.previous_state_bad_json`
  - `build.previous_state_bad_shape`
  - `build.methodology_missing`

### Tests — Path D (build entry point)
- New `tests/test_build.py` — **11 tests**, all green:
  - `test_build_emits_all_pages_and_signed_manifest` — all five
    pages land with >200 bytes; signature round-trips under embedded
    pubkey; one history line; `used_ephemeral_key=True` surfaced.
  - `test_dashboard_and_sources_reference_each_other` — regex pulls
    every `sources.html#<id>` anchor from the rendered dashboard and
    asserts a matching `id="<id>"` lives in the rendered sources
    page (drill-down link consistency).
  - `test_second_build_appends_history_and_reads_previous_state` —
    two consecutive builds produce **two** history lines, not one
    overwritten line; second build parses first build's
    `clock_state.json` without error.
  - `test_corrupt_previous_state_raises` — bad previous JSON →
    `IngestError("build.previous_state_bad_json")`.
  - `test_signing_key_missing_is_fail_closed` — no file, no env, no
    ephemeral → `SignatureError("build.no_signing_key")`.
  - `test_signing_key_from_env_b64` — env-var path; signed manifest
    `signing_pubkey` matches the supplied key.
  - `test_signing_key_from_file_raw_bytes` — file-path with raw 32
    bytes; signed manifest `signing_pubkey` matches.
  - `test_signing_key_file_bad_format_raises` →
    `SignatureError("build.signing_key_file_bad_format")`.
  - `test_missing_methodology_raises` →
    `IngestError("build.methodology_missing")`.
  - `test_cli_main_returns_zero_on_success` — CLI `main(argv)` with
    `--allow-ephemeral-key` returns 0 and prints canonical sha + each
    page name.
  - `test_cli_main_returns_one_on_missing_key` — CLI without
    ephemeral opt-in returns 1 and surfaces `build.no_signing_key`
    on stderr.

### Verification — Path D (build entry point)
- `python3 -m pytest tests/test_build.py -x -q` — **11 passed**.
- `python3 -m pytest tests/ -q` — **229 passed** (was 218; +11
  build-entry-point tests).
- v0.1 and v0.2 golden replays still hash-locked (`aa5a8c11…` and
  `9d20017e…` unchanged — the new module is purely additive and the
  golden replays go through `replay.py`, not the new build path).
- Forbidden-language lint untouched.

### Added — Path E: deploy-workflow fix (`pages-deploy.yml`)
Pre-v0.2.3 the deploy workflow was, in practice, broken:
`Render static site` invoked `qday_clock.render.cli build` (which has
never existed) with `continue-on-error: true`, then the fallback step
ran `cp -R site _site` and uploaded the **raw Jinja templates** with
`{{ }}` placeholders. Any push to `main` would have shipped an
unrendered, unsigned site. This is a §8 silent-fallthrough hazard
caught only because we sat down to actually deploy.

Rewrite scope:
- **Fail loud on missing signing-key secret** (new step
  `Assert signing-key secret is present`). If
  `secrets.QDAY_SIGNING_KEY_B64` is empty, the workflow exits 1 with a
  human-readable error rather than silently degrading to an ephemeral
  key (which would publish a different pubkey on every deploy and
  break the "embed pubkey in about.html for re-verification" story).
- **Real renderer invocation**: `python -m qday_clock.build
  --site-dir _site --seed-signals data/seed_signals.json
  --methodology METHODOLOGY.md` (the v0.2.2 entry point). The
  signing key is passed through the environment via
  `QDAY_SIGNING_KEY_B64`.
- **Asset + CNAME staging**: explicit step copies `site/assets/`
  and `site/CNAME` into `_site/`. The renderer deliberately doesn't
  touch the asset tree (its job is HTML + signed manifest); the
  workflow owns asset placement.
- **Post-build verification step**: asserts that all 5 rendered
  HTML files exist and are non-empty, and that
  `_site/data/clock_state.json` exists, before the artifact is handed
  to `actions/upload-pages-artifact`. Defence-in-depth against any
  earlier step silently no-op'ing.
- **Removed the `cp -R site _site` fallback** entirely. If the
  build fails, the deploy fails. No silent success path.

### Tests — Path E
- New `tests/test_build.py::test_rendered_pages_reference_assets_css`
  asserts every rendered page references `assets/clock.css`. This
  guards the deploy contract: the workflow stages `site/assets/`
  alongside the rendered HTML; if a future template change drops the
  stylesheet link, the workflow would still ship the asset tree but
  the pages would render unstyled and nothing else would catch it.

### Verification — Path E
- Local smoke of the exact CLI the workflow invokes:
  ```
  python3 -m qday_clock.build \
    --site-dir /tmp/qday_test_site \
    --seed-signals data/seed_signals.json \
    --methodology METHODOLOGY.md \
    --allow-ephemeral-key
  ```
  emits all 5 pages plus `data/{clock_state.json,history.jsonl}`;
  followed by `cp -R site/assets _site/assets` + `cp site/CNAME
  _site/CNAME`, the final tree contains every artifact GH Pages needs.
  Canonical sha256 of the smoke run:
  `7522f0bdc85e083ae517355a06c67e84b152d0a597405305c11f83398cc813c4`
  (ephemeral-key — not a deploy attestation, just a smoke
  reproducibility anchor).
- `python3 -m pytest tests/ -q` — **230 passed** (was 229; +1
  asset-ref guard).
- v0.1 and v0.2 golden replays still hash-locked.

### Path E — what's required from Mark before the first real deploy
- **Repo secret `QDAY_SIGNING_KEY_B64`**: base64 of the 32 raw bytes
  in `~/.config/qday_clock/signing_ed25519.key`. Generate locally
  with `base64 -i ~/.config/qday_clock/signing_ed25519.key | tr -d
  '\n'` and paste into the GH repo secret. Without this, the
  workflow refuses to deploy.
- **DNS for `icqubit.com`**: an A/AAAA or CNAME record pointing at
  GitHub Pages (`<user>.github.io.`). The `site/CNAME` file is
  staged by the workflow; DNS is the Mark-side half.
- **Pages source = GitHub Actions** in repo Settings → Pages
  (not "Deploy from a branch").

### Path E — what's still deferred (still v0.2)
- Curator-side workflow that publishes the signed manifest as a
  release artifact (Path B section above).
- Daily cron in `refresh.yml` (currently `workflow_dispatch`-only).

### Added — Path F: v0.2.4 — methodology URL rename + authorship cleanup
Caught during the first live deploy of `https://icqubit.com/`: the
signed `clock_state.json` `methodology_url` field pointed at
`https://github.com/MarkEatherly/subvurs/blob/main/public_interest/qday_clock/METHODOLOGY.md`,
a repo path that does not exist (the SBVRS repo is under MarsVMondo,
the standalone repo is `subvurs/qday-clock`). The link rendered into
the dashboard footer was therefore dead. v0.2.4 swaps the URL to the
live `https://icqubit.com/methodology.html` (which the v0.2.2 build
step already renders) and removes the `Mark Eatherly` authorship
string from `pyproject.toml` and `LICENSE` in favor of `Subvurs`
project-level authorship — per Mark's request to keep the public-facing
artifacts cleanly under the Subvurs identity.

Files changed:
- `qday_clock/score/clock.py`: `METHODOLOGY_URL` set to
  `https://icqubit.com/methodology.html`.
- `pyproject.toml`: `authors = [{ name = "Subvurs" }]` (was
  `Mark Eatherly`). Version bumped `0.1.0` → `0.2.4` to match git
  tag cadence (the v0.2.0/.1/.2/.3 tags were git-only; v0.2.4 is the
  first release where the pyproject string is brought in line).
- `qday_clock/__init__.py`: `__version__ = "0.2.4"` (was `0.1.0`).
- `LICENSE`: `Copyright (c) 2026 Subvurs` (was `Mark Eatherly`).

### Tests — Path F (golden replay re-lock)
The `methodology_url` rename changes the byte image of every signed
`clock_state.json`, so both golden replay hashes had to be re-locked.
Per CLAUDE.md §7 this is the documented re-lock path — the test files
explicitly support `EXPECTED_CANONICAL_HASH = None` bootstrap mode for
exactly this case, and re-locking is conditional on a CHANGELOG entry
documenting the change (this entry).

- `tests/golden/test_golden_replay.py::EXPECTED_CANONICAL_HASH`
  re-locked: `aa5a8c11…` → `696887e1a72fbaada43940c0968a7b6a041f99b35b84d4b452bed7eb955a9caa`.
- `tests/golden/test_golden_replay_v02.py::EXPECTED_CANONICAL_HASH`
  re-locked: `9d20017e…` → `96eb797b8a006bf93eae7026b4d49837867c329cd0d767f30e058f6a01ce14b1`.
- `tests/golden/expected_state.json` regenerated as a deterministic
  byte-identical canonical (RFC-8785) replay snapshot of
  `manifest_2026_q1.json`. This file isn't read by any test (a
  stale snapshot artifact); regenerated only so a future reader
  doesn't mistake it for current data.
- v0.2 gate-fire contract unchanged: both `RoadmapWeightCapGate`
  and `StaleSignalGate` still fire on `manifest_2026_v02.json` per
  the Goodhart-contract assertion in
  `test_golden_replay_v02_required_gates_fire`.

### Verification — Path F
- `python3 -m pytest tests/ -q` — 230 passed (unchanged from Path E).
- `methodology_url` in the regenerated `expected_state.json` reads
  `https://icqubit.com/methodology.html` (verified via
  `python3 -c "import json; print(json.load(open('tests/golden/expected_state.json'))['methodology_url'])"`).
- Forbidden-language lint untouched.
- Live verification deferred to the post-deploy step (re-deploy
  must regenerate the live `clock_state.json` with the new URL,
  then `curl -s https://icqubit.com/data/clock_state.json | jq .methodology_url`
  must read `https://icqubit.com/methodology.html`).

### Added — Path G: v0.2.5 — ruff lint cleanup
The v0.2.4 deploy fixed the standalone-repo CI workflow (the
`working-directory` mis-pointer left over from the SBVRS-source-tree
layout). Once the CI step actually ran, it surfaced **119 pre-existing
ruff lint errors** that had been invisible behind the broken bash step.
v0.2.5 cleans them up to zero.

Auto-fixed (142 in total across `--fix` cascade):
- `UP017` × 33: `datetime.timezone.utc` → `datetime.UTC`
- `UP045` × 33: `Optional[X]` → `X | None` (PEP 604)
- `I001` × 17: import ordering
- `UP037` × 7: quoted runtime annotations stripped
- `F401` × 5: unused imports removed
- `UP035` × 3: `typing` deprecated imports → `collections.abc`
- `UP012` × 1: `"x".encode("utf-8")` → `"x".encode()`

Manual fixes:
- `B904`: `qday_clock/build.py:351` — added `from exc` on the SystemExit
  re-raise so the original ValueError chain is preserved.
- `UP042` × 2: `qday_clock/core/schemas.py` — `class EvidenceClass(str, Enum)`
  and `class AxisId(str, Enum)` migrated to `StrEnum`. **Verified
  canonical-safe**: both golden replay hashes
  (`696887e1…` v0.1, `96eb797b…` v0.2) still match byte-for-byte after
  the change, confirming Pydantic JSON-mode serialization uses `.value`
  identically for both base patterns.
- `B905` × 2: `axis_physical_scaling.py:142`, `axis_resource_estimate.py:251`
  — added `strict=False` to `zip(anchors, anchors[1:])` (intentional
  pair-wise sliding window, length difference is expected).
- `B017` × 2: `tests/core/test_schemas.py:57, 80` — `pytest.raises(Exception)`
  → `pytest.raises(ValidationError)` (the actual exception Pydantic
  raises on the [0,1] clip and frozen-mutation paths).
- `E501` × 8 manual: line wraps in `schemas.py`, `classifier.py`,
  `score/clock.py` (intermediate-variable extraction in the
  confidence-band calculation), `tests/test_smoke.py` (extracted
  `lowered = html_method.lower()`).
- `E501` × 5 via per-file ignore: `qday_clock/render/svg_clock.py` —
  added `[tool.ruff.lint.per-file-ignores]` entry. The long lines are
  literal SVG markup inside an f-string; splitting them would inject
  whitespace into the rendered SVG output.

Files changed:
- `pyproject.toml`: per-file-ignores block added; version `0.2.4 → 0.2.5`.
- `qday_clock/__init__.py`: `__version__ = "0.2.5"`.
- 27 source/test files touched by `ruff --fix` and manual edits.

### Verification — Path G
- `python3 -m ruff check qday_clock tests` — `All checks passed!`
- `python3 -m pytest tests/` — 230 passed (no test deletions or
  threshold relaxations per CLAUDE.md §7).
- `python3 -m pytest tests/golden/` — both canonical hashes still
  byte-identical after the StrEnum migration (the canonical-safety
  question I flagged in the §7 honest-flag).
- `clock_state.json` artifact is byte-identical to v0.2.4 (no
  re-lock needed).

This is a pure CI/code-quality cleanup with no public-facing artifact
change. Nothing in the signed `clock_state.json` moves.

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

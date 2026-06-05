# Q-day Clock — Architecture

This document is the v0.1.0 MVP architecture reference. Anything that
changes the data flow described here must update this file (per
CLAUDE.md §5).

---

## Data flow

```
data/seed_signals.json
       │
       ▼
qday_clock.ingest.seed_signals.load_seed_signals()
       │  returns list[Signal]
       │
       │  (v0.2: Curator manifest is read here as well —
       │   loose coupling via signed JSON, never direct SQLite)
       │
       ▼
qday_clock.extract.axis_logical_qubits.extract()
       │  (v0.2: axes 2-5 extractors wired in here)
       │
       ▼
qday_clock.score.axes.aggregate_axis()
       │  per-axis aggregation; applies SingleSourceCapGate
       │  if any one source dominates the axis pre-cap
       │
       ▼
qday_clock.score.clock.compute_clock_state()
       │  combines axes 1-4 with weights;
       │  axis 5 (PQC migration) subtracts.
       │  Cold-start axes (no live signals) fall back to GRI baseline.
       │  Confidence band derives from per-axis bands.
       │
       ▼
qday_clock.render.manifest.write_signed_manifest()
       │  - Pydantic dump
       │  - RFC 8785 canonicalization
       │  - Ed25519 signature embedded inline
       │  - Writes site/data/clock_state.json (canonical bytes)
       │
       ▼
qday_clock.render.templates.render_{index,methodology,about}()
       │  Jinja2 with StrictUndefined; missing vars raise.
       │  index page includes inline SVG (no JS required).
       │
       ▼
site/index.html
site/methodology.html
site/about.html
```

---

## Module map

| Module | Role |
|---|---|
| `qday_clock.core.schemas` | All pydantic models (Signal, AxisReading, RubricWeights, ClockState, CuratorManifest). Sum-to-1 weight invariant and band-ordering invariant enforced at construction. |
| `qday_clock.core.canonical` | RFC 8785 JSON canonicalization for signing. Rejects NaN, Inf, non-string keys, and cycles. |
| `qday_clock.core.signing` | Ed25519 keygen/sign/verify; signs the canonical form. |
| `qday_clock.core.errors` | Typed errors with `error_code` so callers (and the CHANGELOG) can categorize failures. |
| `qday_clock.core.time` | UTC normalization and `days_between()`. |
| `qday_clock.ingest.seed_signals` | Reads `data/seed_signals.json` into `Signal` objects. Hash-based deterministic `signal_id`. |
| `qday_clock.extract.keywords` | Per-axis keyword catalogues. v0.1.0 ships axis-1 keywords; axes 2-5 stubbed. |
| `qday_clock.extract.axis_logical_qubits` | The only live extractor at v0.1.0. Returns `LogicalQubitExtraction` or `None`. |
| `qday_clock.score.weights` | Default rubric (re-exported from schemas for convenience). |
| `qday_clock.score.gri_baseline` | GRI 2024 anchor; hard-coded at v0.1.0, CSV-loaded at v0.2. |
| `qday_clock.score.axes` | Per-axis aggregation; applies SingleSourceCapGate. |
| `qday_clock.score.clock` | Combines axes into a `ClockState`. |
| `qday_clock.score.gates` | StaticPointGate, SingleSourceCapGate, ThresholdGuard (v0.1.0). The five remaining gates are scheduled for v0.2. |
| `qday_clock.score.mosca` | Mosca's-inequality calculator (informational; not in the headline clock). |
| `qday_clock.render.svg_clock` | Server-rendered 24-hour SVG; aria-label on the root for WCAG 2.1 AA. |
| `qday_clock.render.manifest` | Signed, canonicalized JSON writer + history.jsonl appender. |
| `qday_clock.render.templates` | Jinja2 renderers for index/methodology/about. |
| `qday_clock.verify.replay` | CLI: `--check <signed.json>` and `--replay <fixture.json>`. Used by CI. |

---

## Determinism contract

1. **Signal IDs are content-hashed.** `_stable_signal_id(source, title, published_at)` returns a deterministic 16-hex-char prefix; same inputs always produce the same ID. Required for golden replay.

2. **Canonical JSON is RFC 8785.** Keys sorted lexicographically (UTF-16 code unit comparison), no insignificant whitespace, NaN/Inf rejected, non-string keys rejected, cycles rejected. Two different processes with the same input dict produce byte-identical output.

3. **Signing is over the unsigned body.** Before signing we pop `signature` and `signing_pubkey`; after signing we attach them. Verification re-derives the canonical bytes of the unsigned body and checks the signature.

4. **`generated_at` is the one non-deterministic field.** The golden replay test pins it via `model_copy` so canonical hashes are reproducible.

---

## Failure-class table

Per CLAUDE.md §8, errors are never silently swallowed. The table below lists each `error_code` and where it can fire.

| `error_code` | Raised by | Meaning |
|---|---|---|
| `schema.weights_not_one` | `RubricWeights._sum_to_one` | Axes 1-4 weights don't sum to 1.0 ± 1e-9. |
| `schema.bad_band` | `AxisReading._band_ordering` | `confidence_band_low > confidence_band_high`. |
| `schema.bad_axis_key` | `ClockState._axes_keys_are_valid` | Unknown axis ID in the `axes` dict. |
| `ingest.seed_missing` | `load_seed_signals` | Seed file not on disk. |
| `ingest.seed_bad_json` | `load_seed_signals` | Seed file not valid JSON. |
| `ingest.seed_bad_shape` | `load_seed_signals` | Seed file missing `signals` key. |
| `ingest.seed_missing_field` | `load_seed_signals` | Per-entry KeyError. |
| `ingest.seed_bad_value` | `load_seed_signals` | Enum / cast failure. |
| `ingest.bad_datetime` | `_parse_dt` | Malformed ISO-8601 string. |
| `signing.bad_signature` | `verify_payload` | Signature does not verify; CLI exits non-zero. |
| `threshold.drift` | `ThresholdGuard.assert_locked` | Display thresholds differ from the locked file. |
| `threshold.missing_lock` | `ThresholdGuard.check` | `threshold_lock.json` not on disk. |

---

## Deliberately deferred to v0.2 / v0.3

| Item | Reason |
|---|---|
| Curator manifest ingest | v0.1.0 ships seed signals only; loose-coupled JSON contract designed but not wired. |
| Axes 2-5 extractors | v0.1.0 ships axis-1 only; remaining axes fall back to GRI baseline. |
| 5 additional Goodhart gates | StaticPointGate / SingleSourceCapGate / ThresholdGuard ship; AntiStiffnessGate, ContrastSaturationGate, MultiSourceConfirmationGate, RoadmapWeightCapGate, StaleSignalGate are v0.2. |
| Daily refresh workflow | Avoid auto-merge without human review until v0.2 (rigor §1). |
| Dashboard + sources pages | MVP ships symbolic clock only. |
| Interactive Mosca calculator | v0.3. |
| Public CORS API | v0.3. |

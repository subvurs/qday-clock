# Q-day Clock — Signal Catalog

What each extractor looks for, and the anchor map it uses to translate
a numeric hit into a `[0, 1]` normalized value. Per plan §D part 3,
this catalog is part of the credibility moat: extractor behavior is
public and reviewable.

---

## Keyword matching semantics (token-boundary, all axes)

Every axis gate (`matches()`) routes its keyword tuple through
`qday_clock.extract.keywords.keyword_hit`, which matches each keyword as
a **token** rather than a raw substring. A keyword fires only when it is
not flanked by an alphanumeric character on either side
(`(?<![A-Za-z0-9])…(?![A-Za-z0-9])`, case-insensitive).

Punctuation — hyphen, `+`, space, comma — counts as a boundary, so
compound terms still match: `CRYSTALS-Kyber`, `SPHINCS+`, `FIPS 203`,
`ecc-256`, `RSA-2048`. What no longer matches are substring accidents
that previously tripped a gate spuriously:

| Keyword | Used to false-fire inside | Now |
|---|---|---|
| `shor` | "shorten", "offshore" | rejected |
| `ecc` | "Rebecca", "ecclesiastical" | rejected |
| `crystals` | "quasicrystals" | rejected |

The live-manifest regression that motivated this: a quasicrystals
materials-science article ("…materials known as quasicrystals…") tripped
the **inverse** axis-5 (PQC migration) gate via the `crystals` substring,
fabricating a PQC-adoption signal from an article with no cryptographic
content. See `tests/extract/test_keyword_boundary.py`.

---

## Axis 1 — Logical qubit progress (v0.1.0 — LIVE)

**Weight**: 0.25
**Module**: `qday_clock.extract.axis_logical_qubits`
**Keywords**: `qday_clock.extract.keywords.LOGICAL_QUBIT_KEYWORDS`

Keywords matched against `title.lower() + summary.lower()`:

- `logical qubit`, `logical qubits`
- `surface code`
- `qldpc`, `ldpc code`
- `bivariate bicycle`, `bb code`
- `magic state`
- `below threshold`, `below the threshold`
- `fault-tolerant`, `fault tolerant`
- `code distance`

Numeric patterns (require ≥ 1 hit before the article contributes):

- `distance-N`, `distance N`, `distance_N` (1..99)
- `d = N`, `d=N` (1..99)
- `code distance N` (1..99)
- `N logical qubits?` (1..999)

Anchor map (METHODOLOGY.md §3 Axis 1):

| Extracted | Normalized | Rationale |
|---|---|---|
| Shor's algorithm + RSA-2048 + hardware/device/IBM/Google | 1.0 | Literal CRQC claim. |
| ≥ 10 logical qubits + "below threshold" | 0.85 | Multi-logical at low error rate. |
| ≥ 10 logical qubits, no threshold hint | 0.70 | Multi-logical, conservative. |
| 4-9 logical qubits + "below threshold" | 0.65 | Smaller multi-logical at low error. |
| 4-9 logical qubits, no threshold hint | 0.55 | Smaller multi-logical, conservative. |
| `distance ≤ 3` | 0.00 | Historical baseline. |
| `distance = 4..5` | 0.35 | Linear interp d=3 → 0.0, d=7 → 0.5. |
| `distance = 6..11` | 0.50 | Small-scale FT. |
| `distance = 12..17` | 0.60 | Mid-scale FT. |
| `distance > 17` | 0.70 | Large-scale FT. |

**Fail-conservative**: if a keyword matches but no numeric is
extractable, returns `None`. CLAUDE.md §10.

---

## Axis 2 — Physical qubit scaling (v0.2 — STUBBED)

**Weight**: 0.15
**Keywords**: `qday_clock.extract.keywords.PHYSICAL_SCALING_KEYWORDS`

Keyword list shipped; extractor module not yet wired. Falls back to
GRI baseline floor at v0.1.0.

Planned anchor map: log-scale 100 → 10k → 1M → 20M physical qubits.
SingleSourceCapGate caps single-vendor announcements at axis
contribution 0.6 until corroborated.

---

## Axis 3 — Algorithmic / resource estimate (v0.2 — STUBBED)

**Weight**: 0.30 (highest)
**Keywords**: `qday_clock.extract.keywords.RESOURCE_ESTIMATE_KEYWORDS`

Keyword list shipped; extractor module not yet wired.

Planned anchor map:

- 0.0 ← original Gidney-Ekera 2019 estimate (~20M qubits / 8 hours)
- 0.5 ← any peer-reviewed estimate ≤ 1M qubits or ≤ 1 hour
- 1.0 ← any peer-reviewed estimate ≤ 100k qubits or ≤ 1 minute

AES-128 / Grover sub-axis folded in at weight 0.3 internally (so AES
contributes ~0.09 of the total clock; matches the "weakens not breaks"
framing from THREAT_MODEL.md).

---

## Axis 4 — Error rate floor (v0.2 — STUBBED)

**Weight**: 0.30 (note: 0.15 in METHODOLOGY.md §4; the extra 0.15 is
reallocated from `physical_scaling` at MVP, see `RubricWeights.default`
docstring for rationale.)

**Keywords**: `qday_clock.extract.keywords.ERROR_RATE_KEYWORDS`

The keyword set includes `fidelity` (added 2026-06-29): the axis-4
extractor already converts a reported gate fidelity `F` to an implied
error `1 − F`, but until now an article that cited *only* a fidelity
(e.g. "99.9 % two-qubit gate fidelity") with no explicit "gate error"
phrase never passed the keyword gate, so the conversion path was
unreachable from the live manifest. With `fidelity` admitted, such
articles reach the extractor and contribute their implied error.

Anchor map: 0.0 ← 1 % gate error (NISQ floor), 1.0 ← 10⁻⁵ gate
error (well below surface-code threshold).

---

## Axis 5 — PQC migration friction (v0.2 — STUBBED, INVERSE)

**Weight**: 0.5 (subtraction coefficient — more PQC adoption pushes
clock back)

**Keywords**: `qday_clock.extract.keywords.PQC_MIGRATION_KEYWORDS`

Keyword list shipped; extractor not yet wired. Feeds the `x + z` side
of Mosca's inequality (migration time + secrecy lifetime); axes 1-4
feed `y` (time to CRQC). Mosca's-inequality calculator lives in
`qday_clock.score.mosca` but is informational only — never in the
headline clock value.

---

## Adding a new signal source

1. Add the keyword tokens to `qday_clock.extract.keywords`.
2. Write or extend the extractor; the function must be deterministic
   and pure (no I/O, no LLM, no randomness).
3. Add an entry to this catalog under the matching axis.
4. Add a unit test in `tests/extract/`.
5. Open a CHANGELOG.md entry under "Added" with rationale (CLAUDE.md §5).

---

## Seed signals

`data/seed_signals.json` carries the hand-curated MVP seed set. Each
entry must include:

- `axis` ∈ `{logical_qubits, physical_scaling, resource_estimate, error_rate, pqc_migration}`
- `title`, `summary`, `source`, `published_at`
- `evidence_class` ∈ `{theory, simulation, hardware, roadmap, policy, survey}`
- `raw_value`, `normalized_value` (both numeric)
- optional `url`, `confidence`

Per CLAUDE.md §5, anything pulled from press releases or roadmaps must
be tagged `roadmap` so the future RoadmapWeightCapGate can cap it.

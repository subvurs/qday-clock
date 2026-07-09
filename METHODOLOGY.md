# Q-day Clock — Methodology

This is the credibility document. Read it before drawing any
inference from the clock hand.

The clock displays a *reading* — a normalized synthesis of public
evidence about cryptographically-relevant quantum-computer (CRQC)
capability. It is not a prediction, a probability, or a forecast.
The page text never says "Q-day will be in YYYY"; it says
"as of `<date>`, public evidence reads `<hour>` on a 24-hour Q-day
clock, with the GRI threat-timeline median at `<year>` and NSA
CNSA 2.0 mandatory at 2033."

## 1. Threat model

See [`THREAT_MODEL.md`](THREAT_MODEL.md). In brief: **RSA-2048 (Shor)
+ AES-128 weakening (Grover)**, public evidence only.

## 2. External anchors (the "not-our-opinion" base layer)

These are the load-bearing external references. The clock must stay
broadly consistent with them; large divergences trigger a CHANGELOG
entry and a methodology review.

| Anchor | Role |
|---|---|
| **GRI Quantum Threat Timeline** (Global Risk Institute, annual cryptographer survey, 2019–present) | Provides 5 / 10 / 15-year confidence intervals; shown on dashboard as a visible baseline. |
| **NIST FIPS 203 / 204 / 205** (ML-KEM, ML-DSA, SLH-DSA) | Standardized PQC algorithms; publication dates anchor Axis 5. |
| **NSA CNSA 2.0** | 2025 (software signing) / 2030 (default) / 2033 (mandatory) — authoritative migration windowing. |
| **Gidney & Ekera 2019** (arXiv:1905.09749) | Reference resource estimate (~20M physical qubits, ~8 hours) for Axis 3. Successor estimates: Regev 2023, Chevignard 2024. |

These are listed in `data/` as CSV / JSON so they can be re-validated
against original sources.

## 3. The five axes

Each axis produces a normalized reading in `[0, 1]` where
`0 = far from Q-day` and `1 = imminent`.

### Axis 1 — Logical qubit progress (weight 0.25)

Tracks fault-tolerant logical-qubit demonstrations with measured
distance, threshold-below-pseudothreshold milestones, and code-family
transitions (repetition → surface → qLDPC).

Keywords: `logical qubit`, `distance-N`, `surface code`, `qLDPC`,
`bicycle`, `BB code`, `magic state`, `threshold`.

Anchor mapping:

- `0.0` ← d=3 distance demos (the historical baseline)
- `0.5` ← d=7..11 small-scale fault-tolerant logical qubits
- `0.9` ← multi-logical-qubit algorithms at low logical error rate
- `1.0` ← Shor on >2048-bit RSA on real hardware

### Axis 2 — Physical qubit scaling (weight 0.15)

Largest physical-qubit machines online, gate fidelity at scale,
connectivity. Numeric qubit counts in titles, vendor-tracked
(IBM Condor / Flamingo / Kookaburra, Google Sycamore / Willow, IonQ
Tempo, Quantinuum H / Helios, Atom Computing, PsiQuantum).

Anchor mapping: log-scale 100 → 10k → 1M → 20M physical qubits.

Cap: single-vendor announcements capped at 0.6 axis contribution
(`SingleSourceCapGate`) until corroborated by independent benchmark.

### Axis 3 — Algorithmic / resource estimate (weight 0.30, highest)

Gidney-Ekera-class resource estimates for RSA-2048 and ECC-256;
Grover-attack estimates against AES-128; factoring-algorithm
improvements.

Keywords: `Shor`, `factoring`, `RSA`, `RSA-2048`, `ECC`, `ECDLP`,
`ECDSA`, `secp256k1`, `elliptic curve`, `discrete logarithm`,
`discrete log`, `Grover`, `AES-128`, `T-count`, `T-depth`, `physical
qubits to factor`, `space-time tradeoff`.

Anchor mapping (physical qubits / wall-clock time; shared by both
Shor channels below):

- `0.0` ← original 2019 Gidney-Ekera estimate (~20M qubits, ~8 h)
- `0.5` ← any peer-reviewed estimate ≤ 1M qubits or ≤ 1 hour
- `1.0` ← any peer-reviewed estimate ≤ 100k qubits or ≤ 1 minute

Two Shor channels share this anchor map (both are full-weight, per the
THREAT_MODEL.md "primary target, same axis" declaration):

- `shor_rsa` — RSA-2048 factoring. Calibration anchor: Gidney 2025
  ("How to factor 2048 bit RSA integers with less than a million noisy
  qubits", arXiv 2505.15917) parses to 1M physical qubits → `0.5`.
- `shor_ecc` — ECDLP-256 / secp256k1 discrete-log. Calibration anchor:
  Google Quantum AI 2026 ("Securing Elliptic Curve Cryptocurrencies…",
  arXiv 2603.28846) at < 500k physical qubits → ≈ `0.65` (interpolated
  on the shared 1M→0.5 / 100k→1.0 anchors).

The anchor map is on **physical** qubits. A *logical*-qubit count
(e.g. the ECC paper's ≈ 1450 logical qubits) is Axis 1's scale, not
Axis 3's; the extractor deliberately excludes "logical qubits" from
the physical anchor and fails conservative (returns `None`) rather
than pegging to 1.0 off a small logical count.

AES-128 / Grover contributes weight 0.3 *inside* this axis, so AES
weakening contributes ~0.09 of the total clock.

### Axis 4 — Error rate floor (weight 0.15)

Physical 2-qubit gate error rates, T1 / T2 coherence times,
measurement fidelity, qubit-loss rate (neutral atom).

Anchor mapping: `0.0` ← 1% gate error (NISQ floor),
`1.0` ← 10⁻⁵ gate error (well below surface-code threshold).

### Axis 5 — PQC migration friction (weight 0.15, **inverse**)

Higher PQC adoption = lower clock urgency. Tracks NIST FIPS 203/204/205
deployments, NSA CNSA 2.0 progress, browser / TLS PQ rollouts,
crypto-agility audits.

Keywords: `Kyber`, `Dilithium`, `SPHINCS+`, `ML-KEM`, `ML-DSA`,
`CRYSTALS`, `PQC migration`, `crypto-agility`, `hybrid TLS`, `BSI`,
`NSA`, `NIST`.

Mosca's-inequality role: Axis 5 feeds the `x + z` side of Mosca's
inequality (migration time + secrecy lifetime). Axes 1–4 feed `y`
(time to CRQC). The Mosca calculator on the dashboard makes this
explicit; the headline clock does not display Mosca directly.

### Combination

```
clock_score = sum(weight_i * axis_reading_i for i in [1..4]) - 0.5 * axis_5
clock_score = clip(clock_score, 0.0, 1.0)
clock_hours = 24 * (1.0 - clock_score)   # midnight = Q-day
```

Weights MUST sum to 1.0 across axes 1–4 (validated by pydantic at
construction).

**Cold-start fallback.** When an axis has no live signals (extractor
not yet wired, or no qualifying article in the current window), it
falls back to a GRI-anchored floor so the clock does not read `0.0`
merely for lack of an extraction. The floor is **sign-aware**:

- Additive axes (1–4): fall back to the GRI baseline floor
  (`baseline_axis_floor`, currently `0.58` for the GRI-2024 median
  CRQC year 2034). This is threat-neutral — it stands in for
  GRI-median progress.
- Inverse axis (5, PQC migration): falls back to **`0.0`**, not the
  GRI floor. Because axis 5 is *subtracted*, a positive floor would
  credit the clock for defensive deployment we cannot observe and back
  the clock off without evidence. `0.0` is the threat-conservative
  default ("no evidence of PQC migration → assume none deployed").

Prior to this change axis 5 also inherited the `0.58` floor, which
subtracted `0.5 × 0.58 = 0.29` from every cold-start reading — an
unevidenced ~7-hour backoff. See CHANGELOG.

## 4. Weights (current values)

| Axis | Weight | Justification |
|---|---|---|
| 1. Logical qubits | 0.25 | Direct precursor to Shor; well-measured |
| 2. Physical scaling | 0.15 | Necessary but not sufficient |
| 3. Resource estimate | 0.30 | Most direct map to RSA-2048 cost |
| 4. Error rate | 0.15 | Gates the fault-tolerance overhead |
| 5. PQC migration | 0.15 (subtracts) | Reduces urgency, doesn't reduce capability |

Every weight change is a CHANGELOG entry with rationale (CLAUDE.md
§5). Sum-to-1.0 is enforced at runtime by `RubricWeights`.

## 5. Goodhart gates

Every gate is enumerated here with its trigger and effect. Full
implementation lives in `qday_clock/score/gates.py`; full operational
detail in `docs/GATE_CATALOG.md`.

| Gate | Type | Trigger | Effect |
|---|---|---|---|
| **StaticPointGate** (imported from gh_eval) | Generic | A signal has been constant at the same value across > N readings | Caps that signal's contribution (multiplier ≤ 0.5) |
| **SingleSourceCapGate** (new) | Per-axis | One source contributes > 0.6 of an axis | Caps that source's contribution to 0.6 |
| **MultiSourceConfirmationGate** (new, v0.2) | Per-axis | Step-change > 0.15 in any axis | Requires ≥ 2 independent sources within 30 days; otherwise blunt |
| **RoadmapWeightCapGate** (new, v0.2) | Per-signal | Signal tagged `roadmap` | Caps roadmap signals at 0.3 axis contribution |
| **StaleSignalGate** (new, v0.2) | Per-signal | Signal older than 18 months | Linear decay to 0 contribution at 36 months |
| **AntiStiffnessGate** (imported, v0.2) | Per-axis | Day-over-day swing > 0.4 | Halves the swing magnitude |
| **ContrastSaturationGate** (imported, v0.2) | Per-signal | Any single observation dominates an axis | Caps individual contribution |
| **ThresholdGuard** (new, hash-locked) | Global | The clock-hand display thresholds drift from `data/threshold_lock.json` | CI fails; site does not deploy |

MVP (v0.1.0) ships with **StaticPointGate**, **SingleSourceCapGate**,
and **ThresholdGuard** live. The remaining five gates are scheduled
for v0.2.

## 6. Uncertainty representation

The clock displays a **confidence band**, not a point. Band width is
derived from:

1. Per-axis disagreement — variance of `axis_reading_i` over the most
   recent 30-day window.
2. Signal age — older signals contribute less to confidence.
3. Number of independent sources backing each axis.

When confidence is wide (e.g. at the cold-start of a new axis), the
clock hand renders as a shaded arc, not a line. The numeric reading
is reported with `±` bounds.

## 7. What this clock cannot tell you

- **Whether your data is at risk.** That depends on your secrecy
  lifetime — use the Mosca calculator on the dashboard.
- **When a specific adversary will achieve CRQC capability.** Public
  evidence only; classified programs may or may not be ahead.
- **Probabilities.** This is a reading, not a Bayesian posterior.
- **Which post-quantum scheme to adopt.** NIST has standardized
  ML-KEM, ML-DSA, SLH-DSA; that's a policy decision, not a clock
  output.
- **Whether the GRI survey is right.** We anchor to it, but the
  axis-by-axis evidence may diverge — that divergence is itself a
  signal.

## 8. Reading the clock honestly

When the clock moves, the right questions are:

- Which axis moved, and by how much?
- Did any gates fire? (If yes, see CHANGELOG.)
- Did the GRI baseline move in the same direction?
- Are the contributing signals independent?
- Is the step-change supported by ≥ 2 sources?

The CHANGELOG records every reading change, every gate fire, and
every reversal. Reversals get the same prominence as advances
(CLAUDE.md §1).

## 9. Failure-reporting parity

Per CLAUDE.md §1, this project reports reversals in the same place
it reports advances. If a previously-cited result is retracted, if a
gate uncovers a previously-undetected exploit, or if the methodology
itself is revised, that goes in the CHANGELOG under "Reversals" with
the same prominence as a positive update.

## 10. Calibrated language

Per CLAUDE.md §10, the site copy never uses:

- "prediction" / "predicted" (forbidden)
- "guaranteed" / "will happen by YYYY" (forbidden)
- "breakthrough" / "revolutionary" (forbidden in non-quoted text)
- "quantum supremacy" (forbidden — superseded term)

A forbidden-language CI lint enforces this on every PR.

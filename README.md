# Q-day Clock

An evidence-driven *reading* — not a prediction — of how close
cryptographically-relevant quantum computers (CRQCs) are to arriving,
under a public-evidence-only threat model targeting **RSA-2048 (Shor)**
and **AES-128 weakening (Grover)**.

This project produces a single signed JSON artifact (`clock_state.json`)
plus a static site that displays:

1. A symbolic 24-hour clock (general-public framing)
2. A 5-axis dashboard with per-axis drill-down (rigor framing)
3. A methodology page explaining every input, weight, and gate

## What this is

- A **reading** of public evidence, refreshed on a regular cadence.
- Anchored to external authoritative baselines:
  - [GRI Quantum Threat Timeline](https://globalriskinstitute.org/)
    (annual cryptographer survey)
  - NIST FIPS 203 / 204 / 205 (the standardized PQC algorithms)
  - NSA CNSA 2.0 migration deadlines (2025 / 2030 / 2033)
  - Gidney-Ekera 2019 (and peer-reviewed successors) for Shor resource estimates
- Hardened against Goodhart exploitation: every step-change requires
  multi-source confirmation; every gate that fires is logged in the
  CHANGELOG.

## What this is NOT

- **Not a prediction.** The page never says "Q-day will be in YYYY."
- **Not a probability.** This is a reading, not a Bayesian posterior.
- **Not financial or security advice.** See `docs/about.html`.
- **Not a substitute for** crypto-agility planning or a QKD-deployment
  audit. (For the latter, see [QCert](../../commercialization/path_d_qcert/).)
- **Not classified-aware.** Public evidence only.

## Read the methodology first

The credibility of this clock lives or dies on
[`METHODOLOGY.md`](METHODOLOGY.md). It documents:

- The threat model (`THREAT_MODEL.md`)
- The 5 axes and their `[0, 1]` anchor mappings
- Current weights and the rationale for each
- Every Goodhart gate and what it blocks
- Confidence-band derivation
- What this clock *cannot* tell you

## Layout

```
qday_clock/        # Python package
site/              # static site (HTML/SVG/CSS, no third-party trackers)
data/              # external anchor data (GRI, NIST/NSA, seed signals)
tests/             # unit, golden, adversarial, forbidden-language lint
docs/              # ARCHITECTURE / GATE_CATALOG / SIGNAL_CATALOG
.github/workflows/ # CI, refresh, pages-deploy
```

## License

MIT. See [`LICENSE`](LICENSE).

## Status

**MVP (v0.1.0)** — 1 of 5 axes live (Axis 1: Logical Qubit Progress),
3 of 8 gates live (`StaticPointGate`, `SingleSourceCapGate`,
`ThresholdGuard`). See [`CHANGELOG.md`](CHANGELOG.md) for the
post-MVP roadmap.

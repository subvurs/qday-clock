# Q-day Clock — Threat Model

This document fixes the threat scope of the Q-day Clock. Anything
outside this scope is *out of scope* by construction. Inclusion or
exclusion decisions made here are referenced from `METHODOLOGY.md` and
must not be silently widened.

## In scope

### Primary: RSA-2048 via Shor's algorithm
- Threat: a cryptographically-relevant quantum computer (CRQC) able to
  execute Shor's algorithm on a 2048-bit RSA modulus within a
  policy-relevant time window (hours, not millennia).
- Anchor: Gidney & Ekera (2019), arXiv:1905.09749 — ~20M physical
  qubits at 10⁻³ gate error, ~8 hours, surface code.
- Successor estimates (Regev 2023, Chevignard et al. 2024) tracked as
  algorithmic improvements that shift Axis 3.

### Primary: ECC-256 via Shor's algorithm
- Threat: Shor-style discrete-log attack against 256-bit elliptic-curve
  keys (P-256, secp256k1).
- Roughly comparable resource estimate to RSA-2048 (within a small
  constant factor at the leading order); tracked under the same axis.

### Secondary: AES-128 weakening via Grover's algorithm
- Threat: Grover-accelerated brute force reduces effective security
  of AES-128 from 2¹²⁸ to ~2⁶⁴ work, which is uncomfortable but not
  catastrophic.
- Framing: this **weakens** AES-128 — it does not break it. AES-256
  remains comfortably out of reach.
- Folded into Axis 3 with weight 0.3 inside the axis, so AES-128
  contributes ~0.09 of the total clock — matches the "weakens not
  breaks" framing.

### PQC migration progress (inverse signal)
- NIST FIPS 203 (ML-KEM), 204 (ML-DSA), 205 (SLH-DSA) deployment.
- NSA CNSA 2.0 milestones: 2025 (SW signing), 2030 (default),
  2033 (mandatory).
- Browser / TLS hybrid PQ rollouts.
- More migration = clock hand moves backward (Axis 5 subtracts).

## Out of scope

- **Symmetric ciphers beyond AES-128.** AES-192, AES-256, ChaCha20:
  Grover provides only modest reductions and they remain practically
  out of reach. We do not model them.
- **Hash functions.** SHA-256, SHA-3 are not modeled. Grover's
  speedup against generic preimage is treated as below the
  policy-action threshold.
- **Side-channel attacks.** Power, EM, timing, cache, Rowhammer,
  speculative-execution: these are real threats but unrelated to
  quantum capability. Out of scope.
- **Quantum cryptanalysis of post-quantum schemes.** If a structural
  break in ML-KEM or ML-DSA is discovered, that is *bigger* news than
  Q-day timing and out of scope for this clock.
- **Governance / regulation risk.** Export controls, mandates,
  enforcement risk are policy variables, not technical evidence.
- **Classified hardware programs.** We model only publicly-disclosed
  evidence. If a classified program is years ahead of the public
  one, this clock cannot see that.
- **Adversary modeling.** We do not estimate *which* adversary will
  achieve CRQC first, or whether they would deploy it. The clock is
  capability-only.
- **Harvest-now-decrypt-later (HNDL) attack rate.** We provide a
  Mosca's-inequality calculator on the dashboard so individuals and
  organizations can plug in their own `x` (migration time) and `z`
  (secrecy lifetime), but we do not estimate population-level HNDL
  exposure.

## Trust assumptions

- The Curator corpus is a fair (but biased) sample of public quantum
  literature. We use gates to attenuate vendor / press-release bias.
- The GRI Quantum Threat Timeline survey is a fair aggregation of
  expert opinion. We use it as a visible anchor, not ground truth.
- NIST / NSA / BSI policy dates are reported accurately by the
  respective standards bodies.
- Ed25519 signatures are unforgeable under current cryptographic
  assumptions. (When that assumption falls, this entire signing
  scheme has bigger problems — and so does much else.)

## What changes when the threat model changes

A revision to this threat model is a **breaking change**:

1. New CHANGELOG entry under "Threat-model revisions" with rationale.
2. All affected axis methodologies in `METHODOLOGY.md` updated.
3. All golden-test fixtures rebuilt and version-bumped.
4. The clock state version increments.
5. A dedicated `site/methodology.html` revision note explains the
   change to the public, in plain language.

Threat-model revisions cannot be merged silently.

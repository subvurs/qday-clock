# Q-day Clock — Gate Catalog

Per plan §I (Risk register) and CLAUDE.md §9 (Goodhart-aware
evaluation), every gate that contributes to scoring is enumerated here
with: what attack it blocks, when it fires, and where its adversarial
fixture lives.

The MVP (v0.1.0) ships **three** gates. The remaining five are
scheduled for v0.2.

---

## v0.1.0 — shipped gates

### StaticPointGate

- **Module**: `qday_clock.score.gates.StaticPointGate`
- **Attack blocked**: A vendor repeats the same announcement every
  quarter ("we have N logical qubits, distance d"). The headline
  value never changes. Without a gate, every republish would be
  scored as a fresh signal and the axis would freeze at the vendor's
  preferred value.
- **Fires when**: The last `window_readings` (default 5) entries for
  one `signal_id` are byte-identical.
- **Effect on firing**: Multiplier (default 0.5) applied to the
  signal's normalized value.
- **Fixture**: `tests/adversarial/test_static_point_gate.py`

### SingleSourceCapGate

- **Module**: `qday_clock.score.gates.SingleSourceCapGate`
- **Attack blocked**: A single vendor publishes five blog posts in
  one week, each claiming a different logical-qubit milestone. With
  no cap, that one source dominates the axis reading even though no
  independent party has corroborated any of the claims.
- **Fires when**: `source_share > cap` (default `cap=0.6`).
- **Effect on firing**: Multiplier `cap / source_share` brings the
  source's post-cap share back to exactly `cap`.
- **Fixture**: `tests/adversarial/test_single_source_cap_gate.py`

### ThresholdGuard

- **Module**: `qday_clock.score.gates.ThresholdGuard`
- **Attack blocked**: Someone edits the runtime display thresholds
  (which determine clock-hand colors and alert bands) without going
  through the CHANGELOG / signed-release process. Display drift then
  reads as a clock-position shift to the public.
- **Fires when**: The current thresholds don't byte-match the
  RFC 8785 canonical hash recorded in `data/threshold_lock.json`,
  *or* the lock file is missing.
- **Effect on firing**: `verdict.fired = True` with a "drift detected"
  or "missing" reason. `assert_locked()` raises `ThresholdDriftError`
  so the CI step blocks the release.
- **Fixture**: `tests/adversarial/test_threshold_guard.py`

---

## v0.2 — scheduled (not yet shipped)

### MultiSourceConfirmationGate
- **Attack**: One sensational paper swings the clock without
  independent corroboration.
- **Fires**: An axis step-change exceeds 0.15 within 30 days from a
  single source.

### RoadmapWeightCapGate
- **Attack**: Vendor roadmaps marketed as facts pull the clock toward
  hype.
- **Fires**: Any signal tagged `EvidenceClass.ROADMAP`; contribution
  capped at 0.3 of the axis.

### StaleSignalGate
- **Attack**: Old positive claims keep credit they no longer earn.
- **Fires**: Signal age > 18 months; linear decay to 0 at 36 months.

### AntiStiffnessGate (imported from gh_eval)
- **Attack**: A brittle extractor swings ±0.4 day-over-day.
- **Fires**: Day-over-day axis movement > 0.4.

### ContrastSaturationGate (imported from gh_eval)
- **Attack**: A single extreme outlier dominates an axis.
- **Fires**: Per-signal contribution capped via 1/(1+gain·excess).

---

## Test invariants (CLAUDE.md §7)

Every adversarial fixture is hash-locked in spirit: its expected
verdict.fired / verdict.multiplier values are written into the test
file and a CHANGELOG entry is required to change them. Per CLAUDE.md
§7, **do not silently relax these thresholds.**

If a new attack vector is discovered, the contract is:

1. Write the adversarial fixture *first* (it should fail).
2. Add the gate (or extend an existing gate) until the fixture passes.
3. Document the gate in this file before merge.
4. Document the discovery in CHANGELOG.md.

Per CLAUDE.md §9: assume the optimizer will exploit any loophole. The
fixtures are the contract.

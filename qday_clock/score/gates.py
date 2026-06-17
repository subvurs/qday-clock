"""Goodhart-resistance gates.

Per METHODOLOGY.md §5 and CLAUDE.md §9, every gate is enumerated, every
fire is logged, and every gate has at least one adversarial test fixture.

v0.1.0 shipped three live gates:

- :class:`StaticPointGate` — caps signals that have been constant across N readings
- :class:`SingleSourceCapGate` — caps any one source's contribution to an axis
- :class:`ThresholdGuard` — fails CI if the display-threshold lock file drifts

v0.2 adds:

- :class:`MultiSourceConfirmationGate` — blocks large axis step-changes
  unless ≥2 independent sources have spoken within a 30-day window
- :class:`RoadmapWeightCapGate` — caps vendor-roadmap signals so press
  releases cannot dominate hardware/peer-reviewed evidence
- :class:`StaleSignalGate` — linearly decays signals older than 18
  months to zero contribution at 36 months
- :class:`AntiStiffnessGate` — blunts brittle axis swings that exceed
  a per-refresh ``max_step`` (Q-day analog of the gh_eval Impax
  stiffness penalty, re-shaped onto axis-reading time series)
- :class:`ContrastSaturationGate` — caps any single signal's
  contribution to an axis so no one observation dominates (Q-day
  analog of the gh_eval saturation gate, re-shaped onto signal /
  axis-share inputs)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from qday_clock.core.errors import ThresholdDriftError
from qday_clock.core.schemas import EvidenceClass, Signal

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateVerdict:
    """Result of evaluating a gate against the current state."""

    name: str
    target: str
    fired: bool
    multiplier: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target": self.target,
            "fired": self.fired,
            "multiplier": self.multiplier,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# StaticPointGate — caps signals frozen at the same value for too long
# ---------------------------------------------------------------------------


@dataclass
class StaticPointGate:
    """If a signal has been constant at the same ``normalized_value``
    across more than ``window_readings`` observations, cap its
    contribution.

    The intent matches gh_eval's StaticPointGate: block adversarial
    "freeze at landmark" exploits where an optimizer (or, here, a
    publication bias pattern) holds a metric at a fixed value to
    inflate score.

    For Q-day Clock, this catches situations like a vendor repeating
    the same announcement quarterly without genuine progress.
    """

    name: str = "StaticPointGate"
    target: str = "axis"
    window_readings: int = 5
    multiplier: float = 0.5

    def check(
        self,
        signal_id: str,
        historical_values: list[float],
    ) -> GateVerdict:
        if len(historical_values) < self.window_readings:
            return GateVerdict(
                name=self.name,
                target=signal_id,
                fired=False,
                multiplier=1.0,
                reason=(
                    f"need {self.window_readings} historical readings, "
                    f"have {len(historical_values)}"
                ),
            )
        tail = historical_values[-self.window_readings :]
        if max(tail) - min(tail) < 1e-9:
            return GateVerdict(
                name=self.name,
                target=signal_id,
                fired=True,
                multiplier=self.multiplier,
                reason=(
                    f"signal value constant at {tail[0]:.4f} across last "
                    f"{self.window_readings} readings"
                ),
            )
        return GateVerdict(
            name=self.name,
            target=signal_id,
            fired=False,
            multiplier=1.0,
            reason="signal value varies",
        )


# ---------------------------------------------------------------------------
# SingleSourceCapGate — caps over-represented sources
# ---------------------------------------------------------------------------


@dataclass
class SingleSourceCapGate:
    """If any one ``source`` contributes more than ``cap`` of an axis,
    cap that source's contribution to ``cap``.

    Implementation: returns the per-source cap multiplier given the
    pre-cap share. Callers apply this multiplier when aggregating
    signal contributions per axis.
    """

    name: str = "SingleSourceCapGate"
    target: str = "axis"
    cap: float = 0.6

    def check(
        self,
        source: str,
        source_share: float,
    ) -> GateVerdict:
        if source_share <= self.cap:
            return GateVerdict(
                name=self.name,
                target=source,
                fired=False,
                multiplier=1.0,
                reason=f"share {source_share:.3f} ≤ cap {self.cap}",
            )
        # Cap multiplier so post-cap share == self.cap.
        multiplier = self.cap / source_share
        return GateVerdict(
            name=self.name,
            target=source,
            fired=True,
            multiplier=multiplier,
            reason=(
                f"source {source!r} pre-cap share {source_share:.3f} "
                f"> cap {self.cap}; multiplier {multiplier:.4f}"
            ),
        )


# ---------------------------------------------------------------------------
# MultiSourceConfirmationGate — blocks unconfirmed step-changes
# ---------------------------------------------------------------------------


@dataclass
class MultiSourceConfirmationGate:
    """Block large axis step-changes that lack independent corroboration.

    Per METHODOLOGY.md §5 and plan §D: a proposed step-change in an
    axis reading greater than ``min_step`` requires at least
    ``min_sources`` independent sources to have spoken within a
    ``window_days`` rolling window. Otherwise the gate fires and the
    contribution is multiplied by ``multiplier`` (default 0.5).

    Intent: catch the "one dramatic paper swings the clock" failure
    mode (CLAUDE.md §9). A single arXiv post or vendor blog claiming
    a >0.15 jump on any axis must be corroborated within 30 days,
    otherwise its weight is halved until corroboration arrives.

    Notes on independence
    ---------------------
    Sources are compared by the ``source`` string carried on each
    :class:`Signal`. Curator-side normalization (e.g. collapsing
    ``"IBM Research"`` and ``"IBM Quantum Blog"`` to a single entity)
    is the right place to handle PR-coordination patterns; this gate
    only counts distinct ``source`` strings.
    """

    name: str = "MultiSourceConfirmationGate"
    target: str = "axis"
    min_step: float = 0.15
    min_sources: int = 2
    window_days: int = 30
    multiplier: float = 0.5

    def check(
        self,
        axis: str,
        previous_reading: float,
        proposed_reading: float,
        contributing_signals: list[Signal],
        now: datetime,
    ) -> GateVerdict:
        step = abs(proposed_reading - previous_reading)
        # Tolerance so that subtractions like 0.45 - 0.30 (fp = 0.15...02)
        # land on the "no confirmation needed" side at exactly the threshold.
        if step <= self.min_step + 1e-9:
            return GateVerdict(
                name=self.name,
                target=axis,
                fired=False,
                multiplier=1.0,
                reason=(f"step {step:.3f} ≤ min_step {self.min_step} — no confirmation required"),
            )

        window_start = now - timedelta(days=self.window_days)
        recent_sources: set[str] = {
            sig.source for sig in contributing_signals if sig.observed_at >= window_start
        }
        if len(recent_sources) >= self.min_sources:
            return GateVerdict(
                name=self.name,
                target=axis,
                fired=False,
                multiplier=1.0,
                reason=(
                    f"step {step:.3f} confirmed by {len(recent_sources)} "
                    f"independent sources within {self.window_days}d window"
                ),
            )

        return GateVerdict(
            name=self.name,
            target=axis,
            fired=True,
            multiplier=self.multiplier,
            reason=(
                f"step {step:.3f} > {self.min_step} but only "
                f"{len(recent_sources)} independent source(s) "
                f"in {self.window_days}d window "
                f"(need ≥{self.min_sources})"
            ),
        )


# ---------------------------------------------------------------------------
# RoadmapWeightCapGate — caps vendor-roadmap signals
# ---------------------------------------------------------------------------


@dataclass
class RoadmapWeightCapGate:
    """Cap the per-signal contribution of roadmap-class evidence.

    Per METHODOLOGY.md §5 and plan §D: vendor roadmap announcements
    (``EvidenceClass.ROADMAP``) contribute at most ``cap`` of an axis
    reading; peer-reviewed papers, measured demos, and hardware
    results contribute fully.

    Rationale (CLAUDE.md §3 — evidence-class distinction): a vendor's
    five-year qubit roadmap is a marketing artifact until silicon
    ships. Treating "we plan to build a million-qubit machine by
    2033" as equivalent to "we measured 99.9% gate fidelity at 1,000
    qubits" would let press releases drive the clock. This gate
    enforces the asymmetry.

    The gate evaluates per signal. The returned multiplier brings the
    signal's normalized contribution to at most ``cap``; signals
    already at or below ``cap`` pass through unchanged.
    """

    name: str = "RoadmapWeightCapGate"
    target: str = "signal"
    cap: float = 0.3

    def check(self, signal: Signal) -> GateVerdict:
        if signal.evidence_class != EvidenceClass.ROADMAP:
            return GateVerdict(
                name=self.name,
                target=signal.signal_id,
                fired=False,
                multiplier=1.0,
                reason=(
                    f"evidence_class={signal.evidence_class.value} (not roadmap) — no cap applied"
                ),
            )
        if signal.normalized_value <= self.cap:
            return GateVerdict(
                name=self.name,
                target=signal.signal_id,
                fired=False,
                multiplier=1.0,
                reason=(
                    f"roadmap signal at {signal.normalized_value:.3f} already ≤ cap {self.cap}"
                ),
            )
        # Apply cap: multiplier scales contribution to cap exactly.
        multiplier = self.cap / signal.normalized_value
        return GateVerdict(
            name=self.name,
            target=signal.signal_id,
            fired=True,
            multiplier=multiplier,
            reason=(
                f"roadmap signal at {signal.normalized_value:.3f} "
                f"exceeds cap {self.cap}; multiplier {multiplier:.4f}"
            ),
        )


# ---------------------------------------------------------------------------
# StaleSignalGate — linearly decays old signals out of the reading
# ---------------------------------------------------------------------------


@dataclass
class StaleSignalGate:
    """Decay a signal's contribution as it ages out of the corpus.

    Per METHODOLOGY.md §5 and plan §D: signals retain full weight up
    to ``fresh_days``, then decay linearly to zero at ``stale_days``.
    Beyond ``stale_days`` they contribute nothing. Defaults: 18-month
    freshness, 36-month decay floor.

    Rationale: a 3-year-old "we will have a million-qubit machine"
    announcement that has not been refreshed or corroborated is no
    longer evidence of progress — it is evidence of stalled progress
    (CLAUDE.md §1, failure-reporting parity). The clock should age
    such claims out automatically rather than holding them at full
    weight forever.

    Implementation note: the gate evaluates each signal's
    ``observed_at`` against a caller-supplied ``now`` so tests stay
    deterministic. The multiplier is what the caller multiplies the
    signal's contribution by; ``fired=True`` whenever any decay is
    applied (including the >stale_days floor).
    """

    name: str = "StaleSignalGate"
    target: str = "signal"
    fresh_days: int = 18 * 30  # ~18 months
    stale_days: int = 36 * 30  # ~36 months

    def check(self, signal: Signal, now: datetime) -> GateVerdict:
        age = now - signal.observed_at
        age_days = age.total_seconds() / 86400.0
        if age_days <= self.fresh_days:
            return GateVerdict(
                name=self.name,
                target=signal.signal_id,
                fired=False,
                multiplier=1.0,
                reason=(
                    f"signal age {age_days:.0f}d ≤ fresh window {self.fresh_days}d — full weight"
                ),
            )
        if age_days >= self.stale_days:
            return GateVerdict(
                name=self.name,
                target=signal.signal_id,
                fired=True,
                multiplier=0.0,
                reason=(
                    f"signal age {age_days:.0f}d ≥ stale floor "
                    f"{self.stale_days}d — zero contribution"
                ),
            )
        # Linear decay over [fresh_days, stale_days].
        span = self.stale_days - self.fresh_days
        if span <= 0:
            # Misconfiguration: collapse to zero contribution beyond fresh.
            return GateVerdict(
                name=self.name,
                target=signal.signal_id,
                fired=True,
                multiplier=0.0,
                reason="StaleSignalGate misconfigured: stale_days ≤ fresh_days",
            )
        multiplier = 1.0 - (age_days - self.fresh_days) / span
        multiplier = max(0.0, min(1.0, multiplier))
        return GateVerdict(
            name=self.name,
            target=signal.signal_id,
            fired=True,
            multiplier=multiplier,
            reason=(
                f"signal age {age_days:.0f}d in decay window "
                f"[{self.fresh_days}d, {self.stale_days}d]; "
                f"multiplier {multiplier:.4f}"
            ),
        )


# ---------------------------------------------------------------------------
# AntiStiffnessGate — blunts brittle axis swings
# ---------------------------------------------------------------------------


@dataclass
class AntiStiffnessGate:
    """Blunt axis readings that swing by more than ``max_step`` between
    consecutive refreshes.

    Q-day analog of the gh_eval Impax v3 stiffness penalty
    (gh_eval.exploit_gate.AntiStiffnessGate), re-shaped onto Q-day's
    axis-reading time series. The gh_eval version watches ``std_d``
    on an OpenEvolve trajectory; Q-day has no trajectory, but it does
    refresh axis readings daily. The semantic intent is identical:
    "this thing moves more than the underlying mechanism plausibly
    allows — soften the contribution rather than trust the swing".

    Per plan §D and METHODOLOGY.md §5: an axis whose reading swings by
    more than ``max_step`` in a single refresh (default 0.4) triggers
    a ``multiplier`` (default 0.5) on the new step until corroboration
    arrives. Distinct from MultiSourceConfirmationGate, which is about
    source independence: this gate fires on magnitude alone, independent
    of source count.

    Rationale (CLAUDE.md §9): an evaluator that lets a single refresh
    move an axis from 0.30 → 0.85 is brittle by construction. Even
    when corroboration exists, a step of that size warrants
    discounting until a second refresh confirms it persists.
    """

    name: str = "AntiStiffnessGate"
    target: str = "axis"
    max_step: float = 0.4
    multiplier: float = 0.5

    def check(
        self,
        axis: str,
        previous_reading: float,
        proposed_reading: float,
    ) -> GateVerdict:
        step = abs(proposed_reading - previous_reading)
        if step <= self.max_step + 1e-9:
            return GateVerdict(
                name=self.name,
                target=axis,
                fired=False,
                multiplier=1.0,
                reason=(f"step {step:.3f} ≤ max_step {self.max_step} — no stiffness penalty"),
            )
        return GateVerdict(
            name=self.name,
            target=axis,
            fired=True,
            multiplier=self.multiplier,
            reason=(
                f"step {step:.3f} > max_step {self.max_step}; "
                f"applying stiffness multiplier {self.multiplier}"
            ),
        )


# ---------------------------------------------------------------------------
# ContrastSaturationGate — caps per-signal axis share
# ---------------------------------------------------------------------------


@dataclass
class ContrastSaturationGate:
    """Cap any one signal's share of an axis reading.

    Q-day analog of the gh_eval ContrastSaturationGate
    (gh_eval.exploit_gate.ContrastSaturationGate). The gh_eval version
    catches the "normalize by small constant" Goodhart on a rate
    metric; Q-day's version catches the structurally identical
    pathology on signal contributions: one observation whose
    normalized share of its axis is so large that any small change in
    that one signal would swing the whole clock.

    Per plan §D: caps individual signal contribution to prevent any
    one observation from dominating. Distinct from
    SingleSourceCapGate, which caps per-*source* (a vendor producing
    five signals can still dominate by source). This gate caps
    per-*signal* (one outlier observation, even if it sits alone from
    a unique source, gets capped).

    Inputs:
        signal_id: the signal being evaluated
        signal_share: that signal's normalized contribution to its
            axis (already source-capped if SingleSourceCapGate runs
            before this one)
    """

    name: str = "ContrastSaturationGate"
    target: str = "signal"
    cap: float = 0.5

    def check(self, signal_id: str, signal_share: float) -> GateVerdict:
        if signal_share <= self.cap:
            return GateVerdict(
                name=self.name,
                target=signal_id,
                fired=False,
                multiplier=1.0,
                reason=(f"signal share {signal_share:.3f} ≤ cap {self.cap}"),
            )
        multiplier = self.cap / signal_share
        return GateVerdict(
            name=self.name,
            target=signal_id,
            fired=True,
            multiplier=multiplier,
            reason=(
                f"signal {signal_id!r} share {signal_share:.3f} "
                f"> cap {self.cap}; multiplier {multiplier:.4f}"
            ),
        )


# ---------------------------------------------------------------------------
# ThresholdGuard — fails CI if display-threshold lock file drifts
# ---------------------------------------------------------------------------


@dataclass
class ThresholdLockEntry:
    """One row of the hash-locked threshold file."""

    name: str
    threshold: float


@dataclass
class ThresholdGuard:
    """The hash-locked guard around display thresholds.

    The site's clock-hand colors and alert bands are *content-hashed* in
    ``data/threshold_lock.json``. Any drift between the runtime config
    and the lock file means someone moved a threshold without recording
    it in the CHANGELOG — that's a CI fail.
    """

    name: str = "ThresholdGuard"
    target: str = "display"
    lock_path: Path | None = None

    def check(self, current_thresholds: dict[str, float]) -> GateVerdict:
        if self.lock_path is None:
            return GateVerdict(
                name=self.name,
                target=self.target,
                fired=True,
                multiplier=0.0,
                reason="ThresholdGuard.lock_path not configured",
            )
        if not self.lock_path.exists():
            return GateVerdict(
                name=self.name,
                target=self.target,
                fired=True,
                multiplier=0.0,
                reason=f"threshold lock file missing: {self.lock_path}",
            )

        try:
            locked = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return GateVerdict(
                name=self.name,
                target=self.target,
                fired=True,
                multiplier=0.0,
                reason=f"threshold lock file is not valid JSON: {exc}",
            )

        locked_hash = locked.get("hash")
        locked_thresholds = locked.get("thresholds")
        if locked_hash is None or locked_thresholds is None:
            return GateVerdict(
                name=self.name,
                target=self.target,
                fired=True,
                multiplier=0.0,
                reason="threshold lock file missing 'hash' or 'thresholds'",
            )

        current_hash = _hash_thresholds(current_thresholds)
        if current_hash != locked_hash:
            return GateVerdict(
                name=self.name,
                target=self.target,
                fired=True,
                multiplier=0.0,
                reason=(
                    f"threshold drift detected — runtime hash "
                    f"{current_hash[:12]}... ≠ locked "
                    f"{locked_hash[:12]}..."
                ),
            )

        return GateVerdict(
            name=self.name,
            target=self.target,
            fired=False,
            multiplier=1.0,
            reason="thresholds match lock",
        )

    def assert_locked(self, current_thresholds: dict[str, float]) -> None:
        """Raise :class:`ThresholdDriftError` if the gate fires.

        Used in CI to fail-closed on drift (per CLAUDE.md §7 — no silent
        test weakening).
        """
        verdict = self.check(current_thresholds)
        if verdict.fired:
            raise ThresholdDriftError(
                verdict.reason,
                error_code="gate.threshold_drift",
            )


def _hash_thresholds(thresholds: dict[str, float]) -> str:
    """Canonical hash of a threshold dict.

    We hash the JSON with sorted keys + fixed float formatting so that
    insignificant whitespace cannot create false drift.
    """
    normalized = {k: float(v) for k, v in sorted(thresholds.items())}
    blob = json.dumps(normalized, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def lock_thresholds(thresholds: dict[str, float], out_path: Path) -> str:
    """Write a new threshold lock file. Returns the hash.

    Intended for use during release prep when an intentional threshold
    change is being recorded (always paired with a CHANGELOG entry).
    """
    normalized = {k: float(v) for k, v in sorted(thresholds.items())}
    h = _hash_thresholds(normalized)
    payload = {
        "hash": h,
        "thresholds": normalized,
        "schema_version": "1.0",
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return h


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


@dataclass
class AxisStepProposal:
    """Per-axis step-change being evaluated by MultiSourceConfirmationGate."""

    axis: str
    previous_reading: float
    proposed_reading: float
    contributing_signals: list[Signal]


@dataclass
class GateBundle:
    """Convenience container for the MVP + v0.2 gate set."""

    static_point: StaticPointGate = field(default_factory=StaticPointGate)
    single_source: SingleSourceCapGate = field(default_factory=SingleSourceCapGate)
    multi_source: MultiSourceConfirmationGate = field(default_factory=MultiSourceConfirmationGate)
    roadmap_cap: RoadmapWeightCapGate = field(default_factory=RoadmapWeightCapGate)
    stale_signal: StaleSignalGate = field(default_factory=StaleSignalGate)
    anti_stiffness: AntiStiffnessGate = field(default_factory=AntiStiffnessGate)
    contrast_saturation: ContrastSaturationGate = field(default_factory=ContrastSaturationGate)
    threshold_guard: ThresholdGuard | None = None

    def all_verdicts(
        self,
        signals: list[Signal],
        per_source_share: dict[str, float],
        signal_history: dict[str, list[float]],
        current_thresholds: dict[str, float] | None = None,
        axis_step_proposals: list[AxisStepProposal] | None = None,
        per_signal_share: dict[str, float] | None = None,
        now: datetime | None = None,
    ) -> list[GateVerdict]:
        verdicts: list[GateVerdict] = []
        # Per-signal checks: static-point, roadmap-cap, contrast-saturation,
        # and stale-signal (when a clock-time is supplied).
        check_now = now if now is not None else datetime.now().astimezone()
        for signal in signals:
            history = signal_history.get(signal.signal_id, [])
            verdicts.append(self.static_point.check(signal.signal_id, history))
            verdicts.append(self.roadmap_cap.check(signal))
            if now is not None:
                verdicts.append(self.stale_signal.check(signal, now=check_now))
            if per_signal_share is not None and signal.signal_id in per_signal_share:
                verdicts.append(
                    self.contrast_saturation.check(
                        signal.signal_id, per_signal_share[signal.signal_id]
                    )
                )
        # Source-cap checks
        for src, share in per_source_share.items():
            verdicts.append(self.single_source.check(src, share))
        # Step-change checks: multi-source confirmation + anti-stiffness
        if axis_step_proposals:
            for proposal in axis_step_proposals:
                verdicts.append(
                    self.multi_source.check(
                        axis=proposal.axis,
                        previous_reading=proposal.previous_reading,
                        proposed_reading=proposal.proposed_reading,
                        contributing_signals=proposal.contributing_signals,
                        now=check_now,
                    )
                )
                verdicts.append(
                    self.anti_stiffness.check(
                        axis=proposal.axis,
                        previous_reading=proposal.previous_reading,
                        proposed_reading=proposal.proposed_reading,
                    )
                )
        # Threshold guard
        if self.threshold_guard is not None and current_thresholds is not None:
            verdicts.append(self.threshold_guard.check(current_thresholds))
        return verdicts

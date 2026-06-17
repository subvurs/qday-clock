"""Pydantic schemas for Q-day Clock.

All on-disk and in-memory artifacts pass through these models. Sum-to-1
weight validation and `[0,1]` axis-reading clipping happen at construction
time so that invalid state cannot reach the scoring pipeline.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qday_clock.core.errors import SchemaError

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EvidenceClass(StrEnum):
    """Per CLAUDE.md §3, every signal is tagged with its evidence class."""

    THEORY = "theory"
    SIMULATION = "simulation"
    HARDWARE = "hardware"
    ROADMAP = "roadmap"
    POLICY = "policy"
    SURVEY = "survey"


class AxisId(StrEnum):
    """The five axes. v0.1.0 has Axis 1 live; others stubbed."""

    LOGICAL_QUBITS = "logical_qubits"
    PHYSICAL_SCALING = "physical_scaling"
    RESOURCE_ESTIMATE = "resource_estimate"
    ERROR_RATE = "error_rate"
    PQC_MIGRATION = "pqc_migration"


# ---------------------------------------------------------------------------
# Signal — a single piece of evidence
# ---------------------------------------------------------------------------


class Signal(BaseModel):
    """A single piece of evidence contributing to one axis.

    Signals are immutable once recorded; revisions create new signal IDs
    and the old signal is marked superseded in the history log.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_id: str = Field(..., description="Stable opaque ID, hashed from content")
    axis: AxisId
    title: str
    summary: str
    source: str = Field(
        ...,
        description="Authoritative source identifier (publisher, vendor, journal)",
    )
    url: str | None = None
    published_at: datetime
    observed_at: datetime = Field(..., description="When this signal was ingested into the corpus")
    evidence_class: EvidenceClass
    raw_value: float = Field(..., description="Raw numeric extraction (e.g. qubit count, distance)")
    normalized_value: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Value mapped onto [0,1] per axis rubric",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Per-axis reading
# ---------------------------------------------------------------------------


class AxisReading(BaseModel):
    """The aggregated reading for one axis at a single point in time."""

    model_config = ConfigDict(extra="forbid")

    axis: AxisId
    reading: float = Field(..., ge=0.0, le=1.0)
    contributing_signal_ids: list[str] = Field(default_factory=list)
    n_independent_sources: int = Field(default=0, ge=0)
    confidence_band_low: float = Field(..., ge=0.0, le=1.0)
    confidence_band_high: float = Field(..., ge=0.0, le=1.0)
    note: str | None = None

    @model_validator(mode="after")
    def _band_ordering(self) -> AxisReading:
        if self.confidence_band_low > self.confidence_band_high:
            raise SchemaError(
                f"confidence_band_low ({self.confidence_band_low}) "
                f"> confidence_band_high ({self.confidence_band_high})",
                error_code="schema.bad_band",
            )
        return self


# ---------------------------------------------------------------------------
# Weights — must sum to 1.0 across primary axes
# ---------------------------------------------------------------------------


class RubricWeights(BaseModel):
    """Per-axis combination weights.

    Axes 1–4 sum to 1.0 and contribute additively to the clock score.
    Axis 5 (PQC migration) is an *inverse* axis; it has its own
    subtraction coefficient ``pqc_subtraction``.

    Per CLAUDE.md §5, every weight change must be a CHANGELOG entry
    with rationale.
    """

    model_config = ConfigDict(extra="forbid")

    logical_qubits: float = Field(..., ge=0.0, le=1.0)
    physical_scaling: float = Field(..., ge=0.0, le=1.0)
    resource_estimate: float = Field(..., ge=0.0, le=1.0)
    error_rate: float = Field(..., ge=0.0, le=1.0)
    pqc_subtraction: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> RubricWeights:
        total = (
            self.logical_qubits + self.physical_scaling + self.resource_estimate + self.error_rate
        )
        if abs(total - 1.0) > 1e-9:
            raise SchemaError(
                f"axes 1-4 weights must sum to 1.0 (got {total:.12f})",
                error_code="schema.weights_not_one",
            )
        return self

    @classmethod
    def default(cls) -> RubricWeights:
        """The MVP default weights documented in METHODOLOGY.md §4.

        Note: METHODOLOGY.md §4 documents weights 0.25 / 0.15 / 0.30 / 0.15
        (summing to 0.85). For sum-to-1.0 invariant compliance, the
        remaining 0.15 is reallocated to ``error_rate`` until v0.2 weight
        re-tuning. This reallocation is itself a CHANGELOG entry (see
        CHANGELOG "Deferred to v0.2" — weight re-tuning).
        """
        return cls(
            logical_qubits=0.25,
            physical_scaling=0.15,
            resource_estimate=0.30,
            error_rate=0.30,
            pqc_subtraction=0.5,
        )


# NOTE: with only Axis 1 active in v0.1.0, axes 2-4 are filled by
# `gri_baseline` fallback at runtime so the rubric still validates.


# ---------------------------------------------------------------------------
# ClockState — the signed artifact
# ---------------------------------------------------------------------------


class ClockState(BaseModel):
    """The signed top-level artifact served at ``site/data/clock_state.json``.

    Per CLAUDE.md §5 the structure is foundational: any change to it is
    a CHANGELOG entry and a version bump.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(..., description='Schema version, e.g. "0.1.0"')
    generated_at: datetime
    clock_score: float = Field(..., ge=0.0, le=1.0)
    clock_hours: float = Field(..., ge=0.0, le=24.0)
    confidence_band_hours_low: float = Field(..., ge=0.0, le=24.0)
    confidence_band_hours_high: float = Field(..., ge=0.0, le=24.0)
    axes: dict[str, AxisReading]
    weights: RubricWeights
    gri_baseline_year: int
    gri_baseline_label: str
    gates_fired: list[dict] = Field(default_factory=list)
    methodology_url: str
    signature: str | None = None
    signing_pubkey: str | None = None

    @field_validator("axes")
    @classmethod
    def _axes_keys_are_valid(cls, v: dict[str, AxisReading]) -> dict[str, AxisReading]:
        valid = {a.value for a in AxisId}
        bad = [k for k in v if k not in valid]
        if bad:
            raise SchemaError(
                f"unknown axis keys: {bad}",
                error_code="schema.bad_axis_key",
            )
        return v


# ---------------------------------------------------------------------------
# Curator manifest — loose coupling to the Quantum Curator project
# ---------------------------------------------------------------------------


class CuratorArticleRef(BaseModel):
    """A single article exported from the Quantum Curator corpus."""

    model_config = ConfigDict(extra="forbid")

    post_id: str
    title: str
    url: str
    source: str
    topics: list[str]
    published_at: datetime
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    summary: str


class CuratorManifest(BaseModel):
    """The JSON manifest exported by Curator.

    Q-day Clock reads this rather than the Curator SQLite DB directly,
    so the two projects stay loosely coupled. The manifest itself is
    Ed25519-signed.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(..., description="Manifest schema version")
    generated_at: datetime
    curator_commit: str
    articles: list[CuratorArticleRef]
    db_row_counts: dict[str, int]
    signature: str | None = None
    signing_pubkey: str | None = None

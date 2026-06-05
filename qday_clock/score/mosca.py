"""Mosca's inequality calculator.

Mosca's inequality (Michele Mosca, 2015): if ``x`` is the number of
years needed to migrate to PQC, ``y`` is the number of years until a
CRQC exists, and ``z`` is the number of years your data needs to
remain secret, then you are already exposed if::

    x + z > y

This is a useful framing for HNDL ("harvest now, decrypt later") risk.
It is shown on the dashboard (v0.2) as an interactive calculator. The
headline symbolic clock does not display Mosca directly because the
relevant ``x`` and ``z`` depend on the reader's own situation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MoscaResult:
    """Outcome of evaluating Mosca's inequality for one (x, y, z) triple."""

    x_migration_years: float
    y_crqc_years: float
    z_secrecy_years: float
    exposed: bool
    margin_years: float

    def explain(self) -> str:
        if self.exposed:
            return (
                f"Already exposed by {abs(self.margin_years):.1f} years: "
                f"migration ({self.x_migration_years}) + secrecy "
                f"({self.z_secrecy_years}) > CRQC time ({self.y_crqc_years})."
            )
        return (
            f"Within margin of {self.margin_years:.1f} years: "
            f"migration ({self.x_migration_years}) + secrecy "
            f"({self.z_secrecy_years}) < CRQC time ({self.y_crqc_years})."
        )


def evaluate(
    x_migration_years: float,
    y_crqc_years: float,
    z_secrecy_years: float,
) -> MoscaResult:
    """Evaluate Mosca's inequality.

    All inputs are non-negative year counts. The interpretation is the
    reader's; the calculator does not assume any particular ``y``.
    """
    if min(x_migration_years, y_crqc_years, z_secrecy_years) < 0:
        raise ValueError("Mosca inputs must be non-negative")
    margin = y_crqc_years - (x_migration_years + z_secrecy_years)
    return MoscaResult(
        x_migration_years=x_migration_years,
        y_crqc_years=y_crqc_years,
        z_secrecy_years=z_secrecy_years,
        exposed=margin < 0,
        margin_years=margin,
    )

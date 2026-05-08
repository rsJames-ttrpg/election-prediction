"""Compute swings between 2024 GE shares and today's PNS."""
from __future__ import annotations

import pandas as pd

# The five GB-wide majors that get a swing applied.
SWING_PARTIES: tuple[str, ...] = ("RFM", "CON", "LAB", "GRN", "LDM")


def compute_national_2024(ge2024: pd.DataFrame) -> pd.Series:
    """National GB share per major party from the 2024 GE.

    Denominator is total votes across all 650 constituencies (UK-wide,
    not GB-only — NI is small enough that this distinction doesn't move
    the swing materially).
    """
    totals = ge2024.groupby("party")["votes"].sum()
    grand_total = totals.sum()
    shares = totals / grand_total
    return shares.reindex(SWING_PARTIES).fillna(0.0)


def compute_swing(pns: pd.Series, ge2024_national: pd.Series) -> pd.Series:
    """Swing per major party: PNS minus 2024 national share.

    Both inputs are expressed as fractions (0.0–1.0). Output is in the
    same units (e.g. -0.125 means a 12.5pp drop).
    """
    pns_majors = pns.reindex(SWING_PARTIES).fillna(0.0)
    return pns_majors - ge2024_national

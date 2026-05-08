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


def apply_uns(ge2024: pd.DataFrame, swing: pd.Series) -> pd.DataFrame:
    """Apply Uniform National Swing to per-constituency 2024 shares.

    For the five majors: projected_share = max(0, ge2024_share + swing[party]).
    For all other parties: projected_share = ge2024_share (held flat).
    Then renormalise within each constituency so projected_shares sum to 1.0.

    Input ge2024: long-form DataFrame with (constituency_id, constituency_name,
                  country, party, votes, share).
    Input swing:  Series indexed by SWING_PARTIES (fractional pp shifts).

    Returns: a copy of `ge2024` with an added `projected_share` column.
    """
    out = ge2024.copy()

    # Apply swings to the majors; clamp to 0 below.
    swing_lookup = swing.to_dict()
    is_major = out["party"].isin(SWING_PARTIES)
    out["projected_share"] = out["share"]  # default: flat
    out.loc[is_major, "projected_share"] = (
        out.loc[is_major, "share"]
        + out.loc[is_major, "party"].map(swing_lookup)
    ).clip(lower=0.0)

    # Renormalise within each constituency.
    constituency_total = out.groupby("constituency_id")["projected_share"].transform("sum")
    out["projected_share"] = out["projected_share"] / constituency_total.where(
        constituency_total > 0, 1.0
    )

    return out

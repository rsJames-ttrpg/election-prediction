"""Compute the Projected National Share (PNS) from cleaned ward data."""
from __future__ import annotations

import pandas as pd


def compute_pns(long_df: pd.DataFrame) -> pd.Series:
    """Compute PNS as the all-votes denominator share per party.

    Input: long-form DataFrame from clean.normalise_council_results,
    with columns (council, ward, party, votes).

    Output: Series indexed by party code, values summing to 1.0.
    """
    totals = long_df.groupby("party")["votes"].sum()
    return (totals / totals.sum()).sort_values(ascending=False)

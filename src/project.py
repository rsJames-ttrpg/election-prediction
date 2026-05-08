"""Pick winners per constituency and tabulate seat totals vs 2024."""
from __future__ import annotations

import pandas as pd


def pick_winners(projected: pd.DataFrame) -> pd.DataFrame:
    """For each constituency, return the party with the highest projected share.

    Input: DataFrame from swing.apply_uns with columns including
           (constituency_id, constituency_name, country, party, projected_share).

    Output: DataFrame with one row per constituency:
            (constituency_id, constituency_name, country, projected_winner).
    """
    idx = projected.groupby("constituency_id")["projected_share"].idxmax()
    winners = projected.loc[idx, [
        "constituency_id", "constituency_name", "country", "party"
    ]].rename(columns={"party": "projected_winner"}).reset_index(drop=True)
    return winners


def seat_totals(projected: pd.DataFrame, ge2024: pd.DataFrame) -> pd.DataFrame:
    """Return a per-party comparison of projected seats vs 2024 GE seats.

    Columns: party, projected_seats, ge2024_seats, change.
    """
    projected_winners = pick_winners(projected)
    proj_totals = (
        projected_winners["projected_winner"]
        .value_counts()
        .rename_axis("party")
        .rename("projected_seats")
    )

    # 2024 actual winners: argmax of share within each constituency.
    idx = ge2024.groupby("constituency_id")["share"].idxmax()
    ge_winners = ge2024.loc[idx, "party"]
    ge_totals = ge_winners.value_counts().rename_axis("party").rename("ge2024_seats")

    table = (
        pd.concat([proj_totals, ge_totals], axis=1)
        .fillna(0)
        .astype(int)
        .reset_index()
    )
    table["change"] = table["projected_seats"] - table["ge2024_seats"]
    return table.sort_values("projected_seats", ascending=False).reset_index(drop=True)

"""Normalise the wide council-results sheet into long form."""
from __future__ import annotations

import pandas as pd

# Column names in the source sheet → our canonical party codes.
MAJOR_PARTY_COLUMNS: dict[str, str] = {
    "RFM": "RFM",
    "CON": "CON",
    "LAB": "LAB",
    "GRN": "GRN",
    "LDM": "LDM",
}

# All other party-like columns get summed into the OTH bucket.
OTHER_PARTY_COLUMNS: tuple[str, ...] = (
    "Ind / NoDsc / Ind Nwrk",
    "Localist",
    "TUSC",
    "Workers Party",
    "SDP",
    "Aspire",
    "Christian Peoples Alliance",
    "Heritage",
    "Your Party",
    "Advance UK",
    "Rejoin EU",
    "MRLP",
    "Communist Party of Britain",
    "UKIP",
    "GYF (Restore)",
    "Other",
)


def normalise_council_results(raw: pd.DataFrame) -> pd.DataFrame:
    """Melt the wide council sheet into a long-form DataFrame.

    Returns a DataFrame with columns (council, ward, party, votes), where
    `party` is one of {RFM, CON, LAB, GRN, LDM, OTH}. A ward is included
    only if at least one party column is populated. The Completed? flag
    is ignored, per the spec.
    """
    df = raw[["Council", "Ward"] + list(MAJOR_PARTY_COLUMNS.keys())
             + list(OTHER_PARTY_COLUMNS)].copy()

    # Coerce all party columns to numeric (blanks → 0).
    party_cols = list(MAJOR_PARTY_COLUMNS.keys()) + list(OTHER_PARTY_COLUMNS)
    for col in party_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Drop wards where every party column is 0 (uncovered/missing).
    df = df.loc[df[party_cols].sum(axis=1) > 0].copy()

    # Build the long-form output: one row per (ward, major party) plus one OTH row per ward.
    majors_long = df.melt(
        id_vars=["Council", "Ward"],
        value_vars=list(MAJOR_PARTY_COLUMNS.keys()),
        var_name="party",
        value_name="votes",
    )

    df["OTH"] = df[list(OTHER_PARTY_COLUMNS)].sum(axis=1)
    other_long = df[["Council", "Ward", "OTH"]].rename(columns={"OTH": "votes"})
    other_long["party"] = "OTH"
    other_long = other_long[["Council", "Ward", "party", "votes"]]

    out = pd.concat([majors_long, other_long], ignore_index=True)
    out = out.rename(columns={"Council": "council", "Ward": "ward"})
    out["votes"] = out["votes"].astype(int)
    return out[["council", "ward", "party", "votes"]]

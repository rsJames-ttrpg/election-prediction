"""Data loaders for the two upstream sources.

The council-results sheet is fetched live (cached locally). The 2024 GE
results CSV is bundled in the repo as immutable historical data — see
data/2024-ge/ — because the upstream Parliament server is behind
Cloudflare TLS-fingerprint detection that httpx cannot bypass.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# The Parliament file server is behind Cloudflare and rejects default httpx
# user agents with a JS challenge. Use a browser-like UA for all fetches.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _fetch_to_cache(url: str, cache_path: Path, refresh: bool) -> Path:
    """Fetch `url` to `cache_path` if missing (or `refresh=True`). Returns the path."""
    if refresh or not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(follow_redirects=True, timeout=120.0, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
    return cache_path


COUNCIL_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "14Fh1iHQwD3fhhwrmST5tOo6WH2bCj1rqFbIOEdPs3pQ/"
    "gviz/tq?tqx=out:csv&gid=349596975"
)


# The per-ward vote columns in the source CSV are a merged range starting at
# column index 9 (one per party, 21 parties total).  The header row only
# populates the *first* cell of that range with a long merged-cell string; the
# remaining 20 cells are blank, so pandas names them "Unnamed: 10" …
# "Unnamed: 29".  The party names themselves appear at columns 34-54 as a
# sidebar key, with no per-row data beneath them.  We rename after loading so
# that downstream code can reference party columns by their canonical names.
_COUNCIL_PARTY_COLUMNS: tuple[str, ...] = (
    "RFM",
    "CON",
    "LAB",
    "GRN",
    "LDM",
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

# The merged-header cell at column index 9 gets this pandas column name.
_MERGED_HEADER_COL = (
    "Top Candidate's Number of Votes from Each Party"
    " (Treat INDs/Local Groups as Same Party in Multi-Member Wards)"
)


def load_council_results(refresh: bool = False) -> pd.DataFrame:
    """Load the 2026 council ward-level results from the Google Sheet.

    Caches the raw CSV to data/cache/council_results.csv. Pass refresh=True
    to bypass the cache.

    Returns a DataFrame with one row per ward.  Per-party vote columns are
    named using the canonical party names in ``_COUNCIL_PARTY_COLUMNS``
    (e.g. ``RFM``, ``CON``, ``LAB`` …).
    """
    path = _fetch_to_cache(COUNCIL_SHEET_CSV_URL, CACHE_DIR / "council_results.csv", refresh)
    df = pd.read_csv(path, header=0, skiprows=[1, 2])

    # Build the rename map: first party → merged-header col; rest → Unnamed: N.
    rename: dict[str, str] = {_MERGED_HEADER_COL: _COUNCIL_PARTY_COLUMNS[0]}
    for i, party in enumerate(_COUNCIL_PARTY_COLUMNS[1:], start=10):
        rename[f"Unnamed: {i}"] = party

    df = df.rename(columns=rename)

    # Drop the sidebar-key columns that live at original positions 34–54.
    # After the rename above those columns now share names with the real vote
    # columns (positions 9–29), so we drop them by integer position.
    # Positions 34–54 = iloc indices 34–54 in the current frame.
    sidebar_positions = list(range(34, 55))
    df = df.iloc[:, [i for i in range(len(df.columns)) if i not in sidebar_positions]]

    return df


# HoC Library column names → canonical party codes used elsewhere in this project.
_GE2024_PARTY_COLS: dict[str, str] = {
    "Con": "CON",
    "Lab": "LAB",
    "LD": "LDM",
    "RUK": "RFM",
    "Green": "GRN",
    "SNP": "SNP",
    "PC": "PC",
    "DUP": "DUP",
    "SF": "SF",
    "SDLP": "SDLP",
    "UUP": "UUP",
    "APNI": "APNI",
    "All other candidates": "OTH",
}


def load_ge2024_constituency() -> pd.DataFrame:
    """Load the 2024 GE per-constituency results from the bundled CSV.

    Returns a long-form DataFrame with columns:
      constituency_id, constituency_name, country, party, votes, share

    `country` is one of {'England', 'Scotland', 'Wales', 'Northern Ireland'}.
    `party` codes: CON, LAB, LDM, GRN, RFM, SNP, PC, DUP, SF, SDLP, UUP, APNI, OTH.
    Shares are computed against the per-constituency sum of these party columns
    (which equals `Valid votes` in the source file).

    The CSV is bundled at data/2024-ge/HoC-GE2024-results-by-constituency.csv
    (originally fetched from
    https://researchbriefings.files.parliament.uk/documents/CBP-10009/HoC-GE2024-results-by-constituency.csv).
    It's not refetched at runtime because the Parliament server's Cloudflare
    rules block httpx, and 2024 GE results are immutable.
    """
    raw = pd.read_csv(DATA_DIR / "2024-ge" / "HoC-GE2024-results-by-constituency.csv")

    metadata = raw[["ONS ID", "Constituency name", "Country name"]].rename(columns={
        "ONS ID": "constituency_id",
        "Constituency name": "constituency_name",
        "Country name": "country",
    })

    party_cols_raw = list(_GE2024_PARTY_COLS.keys())
    votes_wide = raw[party_cols_raw].apply(pd.to_numeric, errors="coerce").fillna(0).astype(int)

    long = pd.concat([metadata, votes_wide], axis=1).melt(
        id_vars=["constituency_id", "constituency_name", "country"],
        value_vars=party_cols_raw,
        var_name="party_raw",
        value_name="votes",
    )
    long["party"] = long["party_raw"].map(_GE2024_PARTY_COLS)
    long = long.drop(columns=["party_raw"])

    totals = long.groupby("constituency_id")["votes"].transform("sum")
    long["share"] = long["votes"] / totals.where(totals > 0, 1)

    return long[["constituency_id", "constituency_name", "country", "party", "votes", "share"]]

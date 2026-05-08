"""Cached fetchers for the two upstream data sources."""
from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

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


def load_council_results(refresh: bool = False) -> pd.DataFrame:
    """Load the 2026 council ward-level results from the Google Sheet.

    Caches the raw CSV to data/cache/council_results.csv. Pass refresh=True
    to bypass the cache.
    """
    path = _fetch_to_cache(COUNCIL_SHEET_CSV_URL, CACHE_DIR / "council_results.csv", refresh)
    return pd.read_csv(path, header=0, skiprows=[1, 2])


GE2024_CSV_URL = (
    "https://researchbriefings.files.parliament.uk/documents/"
    "CBP-10009/HoC-GE2024-results-by-constituency.csv"
)

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


def load_ge2024_constituency(refresh: bool = False) -> pd.DataFrame:
    """Load the 2024 GE per-constituency results from the HoC Library CSV.

    Returns a long-form DataFrame with columns:
      constituency_id, constituency_name, country, party, votes, share

    `country` is one of {'England', 'Scotland', 'Wales', 'Northern Ireland'}.
    `party` codes: CON, LAB, LDM, GRN, RFM, SNP, PC, DUP, SF, SDLP, UUP, APNI, OTH.
    Shares are computed against the per-constituency sum of these party columns
    (which equals `Valid votes` in the source file).
    """
    path = _fetch_to_cache(GE2024_CSV_URL, CACHE_DIR / "ge2024_constituency.csv", refresh)
    raw = pd.read_csv(path)

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

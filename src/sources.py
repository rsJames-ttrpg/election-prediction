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

# GE Projection from Council Votes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Jupyter notebook that takes today's UK council election results and projects a hypothetical GE seat-totals result via the standard PNS+UNS psephology model.

**Architecture:** A package of small, single-purpose modules under `src/` (sources → clean → pns → swing → project), driven by a thin notebook (`notebooks/ge-projection.ipynb`) that calls each in order. All HTTP fetches are cached to `data/cache/`. No tests (per the spec — exploratory project); each module is verified by running it on the real data and inspecting output, with sanity-check assertions inline in the notebook.

**Tech Stack:** Python 3.13, uv (package management), pandas, httpx, tabulate (for table rendering), jupyterlab, jupytext (for cleaner notebook diffs).

**Spec:** [docs/superpowers/specs/2026-05-08-ge-projection-from-council-votes-design.md](../specs/2026-05-08-ge-projection-from-council-votes-design.md)

---

## File Structure

Files we will create:

| Path | Responsibility |
|---|---|
| `src/__init__.py` | Marks `src/` as a package |
| `src/sources.py` | Cached fetchers: `load_council_results()`, `load_ge2024_constituency()` |
| `src/clean.py` | `normalise_council_results(df)` → long-form DataFrame with synthetic OTH bucket |
| `src/pns.py` | `compute_pns(long_df)` → Series of national shares |
| `src/swing.py` | `compute_national_2024(df)`, `compute_swing(pns, nat)`, `apply_uns(ge2024_df, swing)` |
| `src/project.py` | `pick_winners(projected_df)`, `seat_totals(projected_df, ge2024_df)` |
| `notebooks/ge-projection.ipynb` | Thin driver + explainer + caveats |
| `data/cache/` | Cached CSVs/xlsx (gitignored) |
| `pyproject.toml` | Updated with dependencies |
| `.gitignore` | Updated to ignore `data/cache/` and `.ipynb_checkpoints/` |

Files modified:

- `pyproject.toml` — add deps
- `.gitignore` — add cache + notebook checkpoints

---

## Task 1: Project scaffolding

**Files:**
- Create: `src/__init__.py` (empty)
- Create: `notebooks/.gitkeep` (empty)
- Create: `data/cache/.gitkeep` (empty)
- Modify: `pyproject.toml`
- Modify: `.gitignore`

- [ ] **Step 1: Create the directory structure and stub files**

```bash
mkdir -p src notebooks data/cache
touch src/__init__.py notebooks/.gitkeep data/cache/.gitkeep
```

- [ ] **Step 2: Add dependencies via uv**

Run from project root:

```bash
uv add pandas httpx tabulate jupyterlab ipykernel jupytext
```

This will modify `pyproject.toml` and create/update `uv.lock`.

- [ ] **Step 3: Update `.gitignore`**

Append these lines to `.gitignore`:

```
# Notebook artifacts
.ipynb_checkpoints/

# Cached HTTP fetches
data/cache/*
!data/cache/.gitkeep
```

- [ ] **Step 4: Verify install works**

Run:

```bash
uv run python -c "import pandas, httpx, openpyxl, tabulate; print('ok')"
```

Expected output: `ok`

- [ ] **Step 5: Commit**

```bash
git add src/ notebooks/ data/ pyproject.toml uv.lock .gitignore
git commit -m "chore: scaffold project structure and dependencies"
```

---

## Task 2: `src/sources.py` — council results fetcher

**Files:**
- Create: `src/sources.py`

The Google Sheet's gviz CSV endpoint is publicly accessible and returns CSV. We cache it locally so we don't refetch on every notebook re-run.

- [ ] **Step 1: Create `src/sources.py` with the council loader**

```python
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
```

The `skiprows=[1, 2]` drops the headline-totals and percentages rows — we want only the per-ward data rows. The header row (row 0) gives column names.

- [ ] **Step 2: Smoke-test it**

```bash
uv run python -c "
from src.sources import load_council_results
df = load_council_results()
print('rows:', len(df))
print('columns:', list(df.columns)[:12])
print(df.head(3)[['Ward', 'Council', 'WINNER', 'Completed?']])
"
```

Expected: hundreds of rows; first columns include `ORDER`, `Ward`, `Council`, `No. Seats Up`, `Seat 1 Winner`, etc. The first three data rows should be wards in `Adur` council with WINNER values like `LAB`/`RFM`.

- [ ] **Step 3: Commit**

```bash
git add src/sources.py
git commit -m "feat(sources): add cached loader for council results sheet"
```

---

## Task 3: `src/sources.py` — 2024 GE constituency loader

The HoC Library publishes per-constituency 2024 GE results as a CSV at
`https://researchbriefings.files.parliament.uk/documents/CBP-10009/HoC-GE2024-results-by-constituency.csv` (briefing page: <https://commonslibrary.parliament.uk/research-briefings/cbp-10009/>).

The CSV is wide-format: one row per constituency (650 rows), with metadata columns followed by per-party vote-total columns. Columns we'll use:

- Metadata: `ONS ID`, `Constituency name`, `Country name`
- Per-party vote totals: `Con`, `Lab`, `LD`, `RUK`, `Green`, `SNP`, `PC`, `DUP`, `SF`, `SDLP`, `UUP`, `APNI`, `All other candidates`

Per-row arithmetic: `Con + Lab + LD + RUK + Green + SNP + PC + DUP + SF + SDLP + UUP + APNI + All other candidates == Valid votes` (already verified on the live file).

We melt this into long form `(constituency_id, constituency_name, country, party, votes, share)` and map party labels to our canonical codes. `All other candidates` becomes our `OTH` bucket.

**Files:**
- Modify: `src/sources.py`

- [ ] **Step 1: Append `load_ge2024_constituency` to `src/sources.py`**

```python
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
```

- [ ] **Step 2: Smoke-test it**

```bash
uv run python -c "
from src.sources import load_ge2024_constituency
df = load_ge2024_constituency()
print('rows:', len(df))
print('seats:', df['constituency_id'].nunique())
print('parties:', sorted(df['party'].unique()))
print('countries:', sorted(df['country'].unique()))
print('---')
print(df.query(\"constituency_name == 'Islington North'\")
        [['party','votes','share']]
        .sort_values('votes', ascending=False).head(6))
print('---')
sums = df.groupby('constituency_id')['share'].sum()
print(f'share sums per seat: min={sums.min():.6f}, max={sums.max():.6f}')
"
```

Expected:
- `rows: 8450` (650 seats × 13 parties)
- `seats: 650`
- parties exactly `['APNI', 'CON', 'DUP', 'GRN', 'LAB', 'LDM', 'OTH', 'PC', 'RFM', 'SDLP', 'SF', 'SNP', 'UUP']`
- countries: `['England', 'Northern Ireland', 'Scotland', 'Wales']`
- Islington North: top row is OTH (Corbyn won as an independent in 2024 — verifies our OTH bucket works)
- per-constituency share sums: 1.000000 in both min and max

- [ ] **Step 3: Commit**

```bash
git add src/sources.py
git commit -m "feat(sources): add cached loader for 2024 GE per-constituency results"
```

---

## Task 4: `src/clean.py` — normalise council data

We melt the wide council sheet into long form `(council, ward, party_code, votes)` for the five major parties, plus a synthetic `OTH` row per ward summing all other parties' votes. The `OTH` row exists so downstream PNS uses an all-votes denominator.

**Files:**
- Create: `src/clean.py`

- [ ] **Step 1: Create `src/clean.py`**

```python
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
```

- [ ] **Step 2: Smoke-test it**

```bash
uv run python -c "
from src.sources import load_council_results
from src.clean import normalise_council_results
raw = load_council_results()
clean = normalise_council_results(raw)
print('long rows:', len(clean))
print('parties:', sorted(clean['party'].unique()))
print('wards:', clean[['council','ward']].drop_duplicates().shape[0])
print(clean.head(8))
"
```

Expected: 6 rows (5 majors + OTH) per included ward; parties exactly `{CON, GRN, LAB, LDM, OTH, RFM}`; ward count in the high hundreds to low thousands; first few rows are Adur council wards with sensible vote counts.

- [ ] **Step 3: Commit**

```bash
git add src/clean.py
git commit -m "feat(clean): normalise wide council sheet into long form"
```

---

## Task 5: `src/pns.py` — compute Projected National Share

Sum top-candidate votes per party across all included wards, divide by total. Result is a Series whose values sum to 1.0 over `{RFM, CON, LAB, GRN, LDM, OTH}`.

**Files:**
- Create: `src/pns.py`

- [ ] **Step 1: Create `src/pns.py`**

```python
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
```

- [ ] **Step 2: Smoke-test against the headline figures from the source sheet**

The source sheet's headline percentages (top of the data) were RFM 25.0%, LAB 21.2%, GRN 18.8%, CON 17.0%, LDM 12.7%. Our PNS should land within ~0.5pp of those.

```bash
uv run python -c "
from src.sources import load_council_results
from src.clean import normalise_council_results
from src.pns import compute_pns
raw = load_council_results()
pns = compute_pns(normalise_council_results(raw))
print(pns.round(4))
print('sums to:', pns.sum().round(6))
"
```

Expected: shares matching the sheet's headline figures; total is 1.0 exactly.

If discrepancies are larger than ~1pp, suspect a column-mapping issue — print the per-party vote totals and compare against the totals row in the source sheet.

- [ ] **Step 3: Commit**

```bash
git add src/pns.py
git commit -m "feat(pns): compute Projected National Share from ward votes"
```

---

## Task 6: `src/swing.py` — national 2024 + swing calculation

**Files:**
- Create: `src/swing.py`

- [ ] **Step 1: Create `src/swing.py` with `compute_national_2024` and `compute_swing`**

```python
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
```

- [ ] **Step 2: Smoke-test**

```bash
uv run python -c "
from src.sources import load_council_results, load_ge2024_constituency
from src.clean import normalise_council_results
from src.pns import compute_pns
from src.swing import compute_national_2024, compute_swing
ge = load_ge2024_constituency()
nat = compute_national_2024(ge)
pns = compute_pns(normalise_council_results(load_council_results()))
swing = compute_swing(pns, nat)
print('2024 national:'); print(nat.round(4))
print('PNS:'); print(pns.reindex(swing.index).round(4))
print('swing (pp):'); print((swing * 100).round(2))
"
```

Expected: 2024 national shares broadly LAB ~0.337, CON ~0.237, RFM ~0.143, LDM ~0.122, GRN ~0.067. Swings reflect the dramatic shifts in the council results (Reform up large, Labour and Conservative down).

- [ ] **Step 3: Commit**

```bash
git add src/swing.py
git commit -m "feat(swing): compute national 2024 shares and swings vs PNS"
```

---

## Task 7: `src/swing.py` — apply UNS

Apply the swings to per-constituency 2024 shares for the five majors; hold all other parties flat; renormalise within each constituency.

**Files:**
- Modify: `src/swing.py`

- [ ] **Step 1: Append `apply_uns` to `src/swing.py`**

```python
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
```

- [ ] **Step 2: Smoke-test**

```bash
uv run python -c "
from src.sources import load_council_results, load_ge2024_constituency
from src.clean import normalise_council_results
from src.pns import compute_pns
from src.swing import compute_national_2024, compute_swing, apply_uns
ge = load_ge2024_constituency()
pns = compute_pns(normalise_council_results(load_council_results()))
swing = compute_swing(pns, compute_national_2024(ge))
proj = apply_uns(ge, swing)

# Sanity: every constituency's projected_share should sum to ~1.0
sums = proj.groupby('constituency_id')['projected_share'].sum()
print('min sum:', sums.min(), 'max sum:', sums.max())

# Inspect a constituency (Holborn & St Pancras: Starmer's safe Lab seat in 2024)
print(proj.query(\"constituency_name == 'Holborn and St Pancras'\")[['party','share','projected_share']]
      .sort_values('projected_share', ascending=False).head(8))
"
```

Expected: all per-constituency sums very close to 1.0 (within 1e-9); Holborn and St Pancras shows LAB still ahead but with a reduced projected share vs 2024, with RFM/GRN higher.

- [ ] **Step 3: Commit**

```bash
git add src/swing.py
git commit -m "feat(swing): apply UNS to 2024 per-constituency shares"
```

---

## Task 8: `src/project.py` — pick winners + seat totals

**Files:**
- Create: `src/project.py`

- [ ] **Step 1: Create `src/project.py`**

```python
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
```

- [ ] **Step 2: Smoke-test**

```bash
uv run python -c "
from src.sources import load_council_results, load_ge2024_constituency
from src.clean import normalise_council_results
from src.pns import compute_pns
from src.swing import compute_national_2024, compute_swing, apply_uns
from src.project import pick_winners, seat_totals
ge = load_ge2024_constituency()
pns = compute_pns(normalise_council_results(load_council_results()))
swing = compute_swing(pns, compute_national_2024(ge))
proj = apply_uns(ge, swing)
print('projected total seats:', pick_winners(proj).shape[0])
print(seat_totals(proj, ge).to_string(index=False))
"
```

Expected: 650 total constituencies; the table shows projected vs 2024 seats per party with a `change` column. Sums of `projected_seats` and `ge2024_seats` should both equal 650.

- [ ] **Step 3: Commit**

```bash
git add src/project.py
git commit -m "feat(project): pick per-constituency winners and tabulate seat totals"
```

---

## Task 9: Notebook scaffolding

We'll author the notebook as a `.py` "percent-format" file first (one Python file with `# %%` cell markers — easy to diff and review), then convert it to `.ipynb`. This keeps cell-level git diffs sane.

**Files:**
- Create: `notebooks/ge_projection.py` (percent-format source)
- Create: `notebooks/ge-projection.ipynb` (generated)

- [ ] **Step 1: Add jupytext to dev deps**

```bash
uv add --dev jupytext
```

- [ ] **Step 2: Create `notebooks/ge_projection.py`**

```python
# %% [markdown]
# # GE Projection from 2026 Council Election Votes
#
# This notebook takes the ward-level votes from today's UK council elections and projects
# what a General Election held on the same day might have looked like in seat terms.
# It uses the standard **PNS + UNS** model (see next cell).
#
# **This is a thought experiment, not a prediction.** Council elections differ from GEs
# in turnout, ballot dynamics, candidate effects, and salience. Read the seat totals
# accordingly. The full caveats are listed at the bottom.

# %% [markdown]
# ## What is PNS + UNS?
#
# **PNS — Projected National Share.** The councils that voted today are not a
# representative sample of GB. PNS estimates what the national vote share *would*
# have been if the whole country had voted today, derived from the wards that did.
# We use a simple unweighted aggregation across wards (the full Curtice technique
# weights wards by historical patterns; see Caveats).
#
# **UNS — Uniform National Swing.** A *swing* is the change in a party's vote share
# vs the last GE. UNS applies the same percentage-point shift to every constituency:
#
# > `projected_share[c, p] = max(0, GE2024_share[c, p] + swing[p])`
#
# After applying, we renormalise within each constituency so shares sum to 100% and
# pick the party with the highest projected share.
#
# **Worked example.** If Lab's 2024 national share was 33.7% and our PNS for Lab is
# 21.2%, the Lab swing is −12.5pp. In a seat where Lab had 50% in 2024, our model
# projects 37.5%. In a seat where Lab had 25%, our model projects 12.5%. Same shift
# everywhere — that's the "uniform" part. UNS is simple and surprisingly accurate
# as a first approximation, but it misses real-world non-uniformity (parties tend
# to collapse hardest where they were strongest).
#
# **Parties without a swing signal** (SNP, Plaid Cymru, NI parties, independents)
# keep their 2024 per-constituency shares unchanged. We compute swings only for the
# five GB-wide majors: RFM, CON, LAB, GRN, LDM.

# %% [markdown]
# ## Setup

# %%
import sys
from pathlib import Path

# Make `src/` importable regardless of where Jupyter was launched.
PROJECT_ROOT = Path.cwd()
if PROJECT_ROOT.name == "notebooks":
    PROJECT_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

# %load_ext autoreload
# %autoreload 2

import pandas as pd

from src.sources import load_council_results, load_ge2024_constituency
from src.clean import normalise_council_results
from src.pns import compute_pns
from src.swing import compute_national_2024, compute_swing, apply_uns
from src.project import pick_winners, seat_totals

pd.set_option("display.float_format", "{:.4f}".format)

# %% [markdown]
# ## Load data

# %%
council_raw = load_council_results()
ge2024 = load_ge2024_constituency()

print(f"Council rows (raw):       {len(council_raw):,}")
print(f"GE2024 long rows:         {len(ge2024):,}")
print(f"GE2024 unique seats:      {ge2024['constituency_id'].nunique():,}")

# %% [markdown]
# ## Clean council data

# %%
council_long = normalise_council_results(council_raw)
n_wards = council_long[['council', 'ward']].drop_duplicates().shape[0]
print(f"Wards with results: {n_wards:,}")
council_long.head(8)

# %% [markdown]
# ## Compute PNS
#
# Sanity check: this should land within ~0.5pp of the headline percentages at the
# top of the source sheet (RFM 25.0%, LAB 21.2%, GRN 18.8%, CON 17.0%, LDM 12.7%).

# %%
pns = compute_pns(council_long)
pns_table = (pns * 100).round(2).rename("PNS (%)").to_frame()
pns_table

# %%
assert abs(pns.sum() - 1.0) < 1e-9, "PNS does not sum to 1.0"

# %% [markdown]
# ## 2024 national shares and swings

# %%
ge_national = compute_national_2024(ge2024)
swing = compute_swing(pns, ge_national)

table = pd.DataFrame({
    "GE2024 (%)": (ge_national * 100).round(2),
    "PNS 2026 (%)": (pns.reindex(ge_national.index) * 100).round(2),
    "Swing (pp)": (swing * 100).round(2),
})
table

# %% [markdown]
# ## Apply UNS to per-constituency 2024 shares

# %%
projected = apply_uns(ge2024, swing)

# Sanity: every constituency's projected shares sum to 1.0.
sums = projected.groupby("constituency_id")["projected_share"].sum()
assert (sums - 1.0).abs().max() < 1e-9, "renormalisation failed somewhere"
print(f"Per-constituency share sums: min={sums.min():.6f}, max={sums.max():.6f}")

# %% [markdown]
# ### Sample constituencies (before vs after)

# %%
samples = [
    "Holborn and St Pancras",     # safe Lab (Starmer's seat)
    "Witney",                     # safe Con
    "Sheffield Hallam",           # Lab/LD marginal type
    "Glasgow North",              # Scotland (SNP share held flat)
    "Cardiff South and Penarth",  # Wales (PC share held flat)
]
for name in samples:
    print(f"\n--- {name} ---")
    seat = (
        projected.query("constituency_name == @name")
        .assign(share_pct=lambda d: (d["share"] * 100).round(2),
                proj_pct=lambda d: (d["projected_share"] * 100).round(2))
        [["party", "share_pct", "proj_pct"]]
        .sort_values("proj_pct", ascending=False)
        .head(6)
    )
    print(seat.to_string(index=False))

# %% [markdown]
# ## Headline result: projected seat totals vs 2024

# %%
totals = seat_totals(projected, ge2024)
totals

# %% [markdown]
# ## Caveats — please read before quoting any of these numbers
#
# 1. **PNS is computed naively.** We aggregate ward vote shares with equal weights
#    instead of the Curtice-style weighting that corrects for non-representative
#    electing-council geography. If the electing councils lean systematically one way,
#    our PNS is biased in that direction.
# 2. **Top-candidate votes are not party totals.** The source sheet records the
#    highest-polling candidate per party in each ward. Parties fielding a full slate
#    in multi-member wards have more total votes than this column shows, so they're
#    slightly under-counted in PNS.
# 3. **Independents and local-group votes don't generate a swing.** They're in the
#    PNS denominator (so the major-party shares are honest) and held flat per
#    constituency in the projection. There's no clean signal for "the independent vote"
#    as a coherent national bloc.
# 4. **UNS is a first approximation.** Real swings aren't uniform across regions or
#    constituency types — a party that's collapsing tends to collapse harder where it
#    was strongest. UNS misses this.
# 5. **Parties without a swing signal are held flat.** SNP, Plaid Cymru, NI parties,
#    independents, minor parties all keep their 2024 per-constituency shares.
#    Renormalisation within each constituency keeps shares summing to 100%.
# 6. **Parties new to a seat.** Where a party had no 2024 candidate, applying a
#    positive swing produces a non-zero projected share — the model treats it as if
#    they fielded a candidate.
# 7. **This is a model, not a prediction.** Council ballot dynamics differ from GE
#    ballot dynamics. Read the seat totals as a thought experiment.
```

- [ ] **Step 3: Generate the .ipynb from the .py source**

```bash
uv run jupytext --to ipynb notebooks/ge_projection.py -o notebooks/ge-projection.ipynb
```

- [ ] **Step 4: Execute the notebook end-to-end**

```bash
uv run jupyter nbconvert --to notebook --execute --inplace notebooks/ge-projection.ipynb
```

Expected: notebook executes with no exceptions; the final cell produces a seat-totals table whose `projected_seats` and `ge2024_seats` columns each sum to 650.

If a cell fails, the most likely cause is a column-mapping issue in `src/sources.py::load_ge2024_constituency` — re-inspect the xlsx structure and adjust.

- [ ] **Step 5: Commit**

```bash
git add notebooks/ pyproject.toml uv.lock
git commit -m "feat(notebook): assemble PNS+UNS GE projection notebook"
```

---

## Task 10: README + final polish

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write a short README**

Replace the empty `README.md` with:

```markdown
# Election Prediction

A Jupyter notebook that projects a hypothetical UK General Election seat result from
the 2026 council election votes, using the standard PNS + UNS psephology model.

## Quick start

```bash
uv sync
uv run jupyter lab notebooks/ge-projection.ipynb
```

Or just look at the executed notebook checked into git.

## What's in here

- [`docs/superpowers/specs/`](docs/superpowers/specs/) — design spec
- [`src/`](src/) — small modules: data loaders, PNS, swing, projection
- [`notebooks/ge-projection.ipynb`](notebooks/ge-projection.ipynb) — the analysis
- [`data/cache/`](data/cache/) — cached HTTP fetches (gitignored)

## Caveats

The notebook leads with a section explaining what PNS+UNS is, and ends with a
caveats section. Read both before quoting any numbers — this is exploratory
analysis, not a prediction.
```

- [ ] **Step 2: Remove the placeholder `main.py`**

The `main.py` from `uv init` isn't used:

```bash
git rm main.py
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README and remove unused main.py"
```

---

## Verification checklist

After all tasks complete, verify:

- [ ] `uv run python -c "from src.project import seat_totals; print('ok')"` succeeds
- [ ] `notebooks/ge-projection.ipynb` opens in Jupyter and all cells execute without errors
- [ ] The seat totals table at the bottom sums to 650 in both the `projected_seats` and `ge2024_seats` columns
- [ ] PNS shares match the source sheet's headline percentages (within ~0.5pp)
- [ ] Per-constituency projected shares sum to 1.0 (asserted in the notebook)
- [ ] `data/cache/` is gitignored (run `git status` after a fresh notebook run — cache files should not appear)

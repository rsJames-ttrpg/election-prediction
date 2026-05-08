# Design: GE projection from 2026 council election votes

**Date:** 2026-05-08
**Status:** Approved

## Goal

Build a Jupyter notebook that takes today's UK council election results and produces a hypothetical "what if these were General Election votes" projection. The headline output is a per-party seat totals table comparing the projection against the July 2024 GE result.

This is exploratory analysis, not a prediction. The notebook should be honest about its limitations and lead with caveats.

## Methodology

**Ward-to-constituency aggregation, with 2024 GE fallback for uncovered seats.**

For each parliamentary constituency:

- If every ward the constituency contains has results in today's data, project a winner from those results.
- Otherwise, use the 2024 GE result for that constituency.

Aggregate winners into per-party seat totals; compare against 2024.

### Why this approach

The user explicitly chose ward aggregation over the more standard PNS+UNS swing model. The trade-off: this approach is conceptually simple and grounded in real votes cast, but produces a partial picture (most constituencies will inherit 2024) and slightly under-counts the leading parties because the source records top-candidate votes rather than total party votes (see Caveats).

## Data sources

All three are fetched once and cached to `data/cache/`.

### 1. Council results — Google Sheet

URL: `https://docs.google.com/spreadsheets/d/14Fh1iHQwD3fhhwrmST5tOo6WH2bCj1rqFbIOEdPs3pQ/edit?gid=349596975`

Fetched as CSV via the gviz endpoint:
`https://docs.google.com/spreadsheets/d/14Fh1iHQwD3fhhwrmST5tOo6WH2bCj1rqFbIOEdPs3pQ/gviz/tq?tqx=out:csv&gid=349596975`

**Columns of interest:**

- `Ward`, `Council`
- `No. Seats Up`, `Seat 1 Winner`, `Seat 2 Winner`, `Seat 3 Winner`, `WINNER` (concatenated)
- `Completed?`
- Per-party vote columns: `RFM`, `CON`, `LAB`, `GRN`, `LDM`, `Ind / NoDsc / Ind Nwrk`, `Localist`, plus a long tail of minor parties

**Important note about the vote columns:** The header text reads *"Top Candidate's Number of Votes from Each Party (Treat INDs/Local Groups as Same Party in Multi-Member Wards)"*. These are the highest-polling candidate per party in each ward, not party totals. In multi-member wards (common in London/met boroughs), a party's true vote pool is larger than what's recorded.

### 2. Ward → constituency lookup — ONS

ONS Open Geography Portal: "Wards (December 2024) to Westminster Parliamentary Constituencies (July 2024) Best Fit Lookup in the UK".

Best-fit assigns each ward to the single constituency containing the majority of the ward's population. Wards that straddle constituency boundaries are resolved by majority share, so small slivers in another constituency are absorbed. Acceptable for an exploratory model — we will note it.

### 3. 2024 GE baseline — HoC Library

House of Commons Library publishes a per-constituency results spreadsheet for the July 2024 General Election. We need at minimum the winner per constituency; vote shares would be useful for future swing analysis but are not required for this design.

## Code structure

```
src/
  sources.py    # cached fetchers for the three sources
  clean.py      # column normalisation, party code mapping, melt to long form
  match.py      # join wards to constituencies (council+ward name normalisation)
  project.py    # aggregate, classify coverage, pick winner, build totals
notebooks/
  ge-projection.ipynb
data/
  cache/        # cached HTTP fetches and lookup CSVs (gitignored)
```

The notebook is a thin driver: each cell calls one helper, prints a small inspection result, and moves on. Logic lives in `src/` so it's testable.

### Module responsibilities

**`sources.py`** — three functions: `load_council_results()`, `load_ward_lookup()`, `load_ge2024()`. Each checks the cache directory, fetches if missing, returns a DataFrame. Fetches use `httpx`. Cache files are CSV.

**`clean.py`** — normalisation:

- `normalise_council_results(df)` → returns a long-form DataFrame with columns `(council, ward, party_code, votes, ind_won_seat)`. The `ind_won_seat` flag is True if any of `Seat 1/2/3 Winner` is `IND` or a local-group code.
- Party code mapping: drop minor parties; keep `RFM`, `CON`, `LAB`, `GRN`, `LDM`, `SNP`, `PC` only.
- Coverage rule: a ward is included if any major-party vote column is populated, regardless of `Completed?`.

**`match.py`** — `attach_constituency(wards_df, lookup_df)`:

- Normalise council and ward names on both sides: lowercase, strip punctuation, collapse whitespace, `&` ↔ `and`, drop suffixes like `" Ward"`.
- Inner-join on `(council_norm, ward_norm)`.
- Return both the matched DataFrame and a list of unmatched wards. The notebook will display unmatched wards so the user can spot systematic issues.

**`project.py`** — three functions:

- `aggregate_to_constituency(matched_df)` → sum votes per `(constituency, party)`; carry forward an `any_ind_won` flag (True if any covered ward in the constituency had an IND seat winner).
- `classify_coverage(matched_df, lookup_df)` → for each constituency, compute `wards_total` (from lookup) and `wards_covered` (from data); classify as `full`, `partial`, or `none`.
- `project_winner(constituency_df, ge2024_df)` → for each constituency:
  - If coverage is `full` and `any_ind_won` is True → winner is `OTH`.
  - If coverage is `full` → winner is argmax over major-party sums.
  - Otherwise → winner is the 2024 GE winner from the baseline.
- `seat_totals(projection_df, ge2024_df)` → group by party, build comparison table with columns `(party, projected_seats, ge2024_seats, change)`.

## Notebook structure

1. **Header markdown cell** — one paragraph stating what this is and what it isn't, with a bullet list of caveats (see Caveats below).
2. **Setup** — imports, data loading via `sources.py`. Show row counts for each source.
3. **Clean & inspect** — call `clean.normalise_council_results`. Show the headline national share from the loaded data; print the count of wards with any IND seat winner.
4. **Match wards to constituencies** — call `match.attach_constituency`. Display unmatched wards in a table; if more than ~5% are unmatched, the notebook should print a loud warning.
5. **Aggregate and classify coverage** — show the count of `full` / `partial` / `none` constituencies. This is a key sanity check: it tells the reader how much of the projection is actually data-driven vs. inherited from 2024.
6. **Project winners** — apply the rule above; show 10 sample constituencies (covered ones first) with both 2024 winner and projected winner.
7. **Seat totals comparison table** — the headline output. Per-party `(projected, 2024, change)` table. Render with pandas or `tabulate`.
8. **Re-stated caveats** — repeat the limitations at the bottom so anyone scrolling to the result can't miss them.

## Caveats (shown prominently in the notebook)

1. **Top-candidate votes are not party totals.** In multi-member wards, the source records only the highest-polling candidate per party. A party running a full slate has a larger true vote pool than what we sum. This systematically under-counts the leading parties in multi-member wards, but the relative ranking within a ward is preserved.
2. **Best-fit ward → constituency mapping.** Some wards are split across constituencies; ONS best-fit assigns each ward to one constituency. Small boundary splits are ignored.
3. **Independents and local-group votes are excluded from vote sums.** They do however trigger the "Other" override at the constituency level (see Methodology).
4. **Most constituencies inherit the 2024 result.** Scotland, Wales, Northern Ireland, and any English seat that contains wards in non-electing councils will fall back to 2024. The seat-totals comparison reflects only the constituencies where today's data drove the projection.
5. **This is a model, not a prediction.** Council elections are local and use different ballot dynamics (multi-member wards, candidate effects, lower turnout). Treat the seat totals as a thought experiment.

## Out of scope

- Constituency-level map / choropleth (excluded by user).
- Vote-share comparison (excluded by user; only seat totals).
- Bar charts of seat totals (excluded by user; table only).
- Uniform-swing fallback for partial-coverage constituencies — partial-coverage seats fall back to 2024.
- Tests for `src/` modules — exploratory project, no test suite.

## Open questions

None at design time. Implementation will likely surface ward-name matching issues that need ad-hoc fixes; the unmatched-wards display in step 4 is the mechanism for catching them.

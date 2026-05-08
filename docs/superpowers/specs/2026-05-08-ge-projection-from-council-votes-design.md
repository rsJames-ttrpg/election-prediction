# Design: GE projection from 2026 council election votes

**Date:** 2026-05-08
**Status:** Approved (revised — methodology switched from ward aggregation to PNS+UNS)

## Goal

Build a Jupyter notebook that takes today's UK council election results and produces a hypothetical "what if these were General Election votes" projection. The headline output is a per-party seat totals table comparing the projection against the July 2024 GE result.

This is exploratory analysis, not a prediction. The notebook should be honest about its limitations and lead with caveats — and should walk the reader through the methodology so the numbers are interpretable.

## Methodology — PNS + UNS

This is the standard psephology approach used on local-election night by John Curtice / the BBC. It has two stages.

### Stage 1: Projected National Share (PNS)

The councils that voted today are not a representative sample of Great Britain — there's no Scotland, no Wales, no Northern Ireland, and only some English councils. So you can't read national vote share directly off the ballot box.

**PNS** is an estimate of *what the national vote share would have been if the entire country had voted today*, derived from the wards that did. The full Curtice technique re-weights wards by historical patterns to correct for the non-representative geography. We will use a simpler version (described in Caveats) — aggregate vote share across all wards that voted, weighted equally — and flag the limitation.

For each major party `p`:

```
PNS[p] = sum(votes_p across all covered wards) / sum(ALL votes across all covered wards)
```

**Important:** the denominator includes independents and minor-party votes, even though we exclude those parties from the projected outcomes. This keeps PNS comparable to the 2024 GE national share (which also uses an all-votes denominator). If we excluded independents from the denominator we'd inflate PNS for the major parties relative to 2024, producing spurious swings.

### Stage 2: Uniform National Swing (UNS)

A **swing** is the change in a party's vote share from one election to the next. The **uniform national swing** assumption says: whatever change we observe at the national level, apply that same percentage-point shift to every constituency.

For each party `p`:

```
swing[p] = PNS[p] - GE2024_national_share[p]
```

For each constituency `c` and party `p`:

```
projected_share[c, p] = max(0, GE2024_share[c, p] + swing[p])
```

After applying, renormalise within each constituency so per-party shares sum to 100%. The party with the highest projected share is the projected winner. Sum across constituencies for seat totals.

### Worked example

Suppose:

- Lab GE2024 national share = 33.7%; today's PNS for Lab = 21.2% → `swing_LAB = -12.5pp`.
- In a constituency where Lab won 50% in 2024, projected Lab share is `50 - 12.5 = 37.5%`.
- In a constituency where Lab won 25% in 2024, projected Lab share is `25 - 12.5 = 12.5%`.
- Same swing applied everywhere — that's the "uniform" part.

After doing this for every party, re-rank within each constituency to find the new winner.

### Why UNS (and what it gets wrong)

UNS is widely used because it's simple, transparent, and surprisingly accurate as a first approximation. Its main weakness is that swings are not actually uniform: a party that's collapsing tends to collapse hardest where it was strongest, and vice versa. UNS misses this and other regional dynamics. Treat the projection as "the simplest defensible model" rather than a forecast.

### Handling parties without a swing signal

We compute swings for the five GB-wide majors only: `RFM`, `CON`, `LAB`, `GRN`, `LDM`.

Every other party in the 2024 baseline — SNP, Plaid Cymru, the NI parties, independents, minor parties — has its 2024 share **held flat** in every constituency. They receive zero swing. This is the honest treatment given we have no data on their movement.

After applying swings to the five majors and holding everything else flat, the per-constituency shares no longer sum to 100%. We renormalise within each constituency to fix that. The winner is whichever party (major or otherwise) has the highest projected share — so a constituency can still be won by SNP, PC, an NI party, or even an independent if their flat 2024 share exceeds every major's swung share.

### Parties not standing in 2024

If a party (e.g. Reform) had no candidate in a given 2024 constituency, their `GE2024_share[c, p]` is 0. Applying a positive swing produces a positive projected share, which is treated as that party fielding a candidate this time. Real-world parties don't appear out of nowhere, but for an exploratory model this is the simplest consistent rule.

## Data sources

All fetched once and cached to `data/cache/`.

### 1. Council results — Google Sheet

URL: `https://docs.google.com/spreadsheets/d/14Fh1iHQwD3fhhwrmST5tOo6WH2bCj1rqFbIOEdPs3pQ/edit?gid=349596975`

CSV endpoint: `https://docs.google.com/spreadsheets/d/14Fh1iHQwD3fhhwrmST5tOo6WH2bCj1rqFbIOEdPs3pQ/gviz/tq?tqx=out:csv&gid=349596975`

**Columns of interest:** `Ward`, `Council`, `Completed?`, and per-party vote columns (`RFM`, `CON`, `LAB`, `GRN`, `LDM`, `Ind / NoDsc / Ind Nwrk`, `Localist`, plus a long tail of minor parties).

**Caveat:** the per-party numbers record the *top candidate's* votes for each party in each ward, not party totals. In multi-member wards a party fielding a full slate of candidates has more votes than this column shows. This means our PNS calculation slightly under-counts parties with broader slates relative to single-candidate parties.

### 2. 2024 GE per-constituency vote shares — HoC Library

The House of Commons Library publishes a per-constituency results spreadsheet for the July 2024 General Election with vote totals (and shares) per party per constituency. We need the full per-party shares per seat — not just the winner — because UNS operates on shares.

If a clean machine-readable source proves unavailable, fall back to the Electoral Commission CSV.

### 3. 2024 GE national vote shares — derived

Computable from source 2 by summing votes per party across all GB constituencies. We will compute this rather than hardcode, so the spec stays correct if the data source updates.

### Dropped from previous design

The ONS ward → constituency lookup is **no longer needed**. PNS+UNS works off national-level vote shares; we don't need to map individual wards to constituencies.

## Code structure

```
src/
  sources.py    # cached fetchers for the two sources
  clean.py      # column normalisation, party code mapping, melt to long form
  pns.py        # compute Projected National Share from cleaned ward data
  swing.py      # compute swings and apply UNS to per-constituency 2024 shares
  project.py    # pick winner per constituency, build seat totals comparison
notebooks/
  ge-projection.ipynb
data/
  cache/        # cached HTTP fetches (gitignored)
```

The notebook is a thin driver: each cell calls one helper, shows a small inspection result, and moves on. Logic lives in `src/`.

### Module responsibilities

**`sources.py`** — `load_council_results()`, `load_ge2024_constituency()`. Each checks the cache, fetches if missing, returns a DataFrame.

**`clean.py`** — `normalise_council_results(df)` returns a long-form DataFrame `(council, ward, party_code, votes)` covering the five majors (`RFM`, `CON`, `LAB`, `GRN`, `LDM`) plus a synthetic `OTH` row per ward summing all other parties' votes (independents, locals, minor parties). The `OTH` row exists so PNS can use an all-votes denominator. Includes a ward only if at least one party column is populated; ignores the `Completed?` flag.

**`pns.py`** — `compute_pns(long_df)` returns a Series `{party_code: share}` over the five majors plus `OTH`, summing to 1.0.

**`swing.py`** —
- `compute_national_2024(ge2024_df)` returns the national share Series for the five majors.
- `compute_swing(pns, ge2024_national)` returns a Series `{party: pp_change}` for the five majors only.
- `apply_uns(ge2024_df, swing)` returns a DataFrame `(constituency, party, projected_share)`. For the five majors: `projected = max(0, ge2024_share + swing[party])`. For all other parties (SNP, PC, NI parties, IND, etc.): `projected = ge2024_share` (flat). Then renormalise within each constituency so shares sum to 1.0.

**`project.py`** —
- `pick_winners(projected_df)` → `(constituency, projected_winner)`.
- `seat_totals(projected_df, ge2024_df)` → comparison table with columns `(party, projected_seats, ge2024_seats, change)`.

## Notebook structure

1. **Header markdown cell** — one paragraph stating what this is and isn't.
2. **What is PNS + UNS?** — a markdown cell with the explanation from the Methodology section above (PNS, UNS, worked example, why we're using it).
3. **Setup** — imports, data loading via `sources.py`. Show row counts.
4. **Clean council data** — call `clean.normalise_council_results`. Show how many wards we kept.
5. **Compute PNS** — call `pns.compute_pns`. Display the resulting share by party as a small table. Sanity-check against the headline percentages at the top of the source sheet (RFM 25.0%, LAB 21.2%, etc.) and note any difference.
6. **Compute 2024 baseline + swing** — load 2024 per-constituency, compute national shares, compute swings. Display the swings prominently.
7. **Apply UNS** — produce projected per-constituency shares. Show 5 sample constituencies (a Lab/Con marginal, a safe Lab seat, a safe Con seat, a Scottish seat, a Welsh seat) with before-and-after shares so the reader can see UNS in action.
8. **Pick winners and tabulate** — produce the seat totals comparison table. The headline output.
9. **Re-stated caveats** — repeat the limitations at the bottom so anyone scrolling straight to the result can't miss them.

## Caveats (shown prominently in the notebook)

1. **PNS is computed naively.** We aggregate ward vote shares with equal weights instead of the Curtice-style weighting that corrects for non-representative electing-council geography. If the electing councils lean systematically one way (e.g. more Tory-leaning shires than Labour cities), our PNS is biased in that direction.
2. **Top-candidate votes are not party totals.** In multi-member wards, the source records only the highest-polling candidate per party. Parties fielding a full slate have a larger true vote pool than what we sum, which under-counts them in PNS.
3. **Independents and local-group votes don't generate a swing.** They're included in the PNS denominator (so the major-party shares are honest) and their 2024 per-constituency shares are held flat in the projection. We just don't compute a national swing for them, because there's no clean signal for "the independent vote" as a coherent national bloc.
4. **UNS is a first-approximation model.** Real swings are not uniform across regions or constituency types; a party that's collapsing tends to collapse harder where it was strongest. UNS misses this.
5. **Parties with no swing signal are held flat.** SNP, Plaid Cymru, NI parties, independents, and minor parties all keep their 2024 per-constituency shares. The five GB-wide majors get the swing. Renormalisation within each constituency keeps shares summing to 100%. A constituency can still be won by SNP/PC/IND/NI parties if their (flat) 2024 share beats every swung major.
6. **Parties new to a seat.** Where a party had no 2024 candidate, applying a positive swing produces a non-zero projected share — the model treats it as if they fielded a candidate.
7. **This is a model, not a prediction.** Council ballot dynamics differ from GE ballot dynamics (multi-member wards, candidate effects, lower turnout). Read the seat totals as a thought experiment.

## Out of scope

- Constituency-level map / choropleth (excluded by user).
- Vote-share comparison table (excluded by user; only seat totals).
- Bar charts of seat totals (excluded by user; table only).
- Curtice-style weighted PNS (would require historical ward data — beyond exploratory scope).
- Regional-swing variants (e.g. separate swings per region) — out of scope; UNS only.
- Tests for `src/` modules — exploratory project, no test suite.

## Open questions

None at design time. Implementation will likely surface data-format quirks in the HoC Library 2024 GE spreadsheet that need ad-hoc handling.

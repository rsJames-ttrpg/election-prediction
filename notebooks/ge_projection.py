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

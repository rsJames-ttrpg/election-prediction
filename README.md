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
- [`data/2024-ge/`](data/2024-ge/) — bundled 2024 GE per-constituency CSV (immutable, in repo)

## Caveats

The notebook leads with a section explaining what PNS+UNS is, and ends with a
caveats section. Read both before quoting any numbers — this is exploratory
analysis, not a prediction.

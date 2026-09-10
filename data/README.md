# Data

**Source**: CDC NNDSS Weekly Data (Socrata dataset `x9gk-5huc`), pulled live from
`https://data.cdc.gov/resource/x9gk-5huc.json`. Weekly, state-level (all 50
states + NYC/DC/territories) case counts across 139 nationally notifiable
diseases. Rolling window, currently 2022–2026 (older years get pruned by CDC,
so this is not a permanent historical archive — raw pulls should be re-run
regularly and archived if longer history is needed).

## Schema notes

| Field | Meaning |
|---|---|
| `states` | Reporting area (state name, `TOTAL`, `US TERRITORIES`, census regions, etc.) |
| `year` / `week` | MMWR year / week |
| `label` | Disease name |
| `m1` | Current week case count — **omitted from the row (not `0`) when the count is zero**; `ingest_nndss.py` fills this as `0.0` |
| `m2` | Previous 52-week max |
| `m3` / `m4` | Cumulative YTD, current / previous MMWR year |

**Bug found and fixed**: `states` silently changed casing convention at
the 2024→2025 boundary — ALL CAPS through 2024 (`"TEXAS"`), Title Case
from 2025 on (`"Texas"`) — for the exact same underlying region. This hit
66 of 140 region strings (basically every state). Left alone, any region
whose history spans that boundary gets treated as two different regions
by every downstream groupby: detection sees a truncated series (missing
years' worth of baseline), alerts key on two different partition keys for
the same state, and a map would show duplicate/incomplete states.
`eda.py`'s `normalize_region_casing` fixes this by canonicalizing each
region to whichever casing it used most recently (2022–2024 data included
— it wasn't actually missing, just invisible under the wrong case). This
materially changed the Phase 2 backtest numbers, not just cosmetically —
see `detection/README.md`.

## Scripts

- `ingest_nndss.py` — pages through the Socrata API and writes a raw JSON
  snapshot to `raw/nndss_weekly_<date>.json`. This is the script the weekly
  ingestion Lambda will wrap.
- `eda.py` — loads the latest raw snapshot, builds a tidy
  `(region, disease, year, week) -> cases` panel (normalizing region
  casing along the way — see above), and writes it to
  `processed/nndss_weekly_panel.parquet`.

## Identified backtest events (Phase 1)

1. **2025 Texas measles outbreak** (`region="Texas"`, `disease="Measles,
   Indigenous"`) — the real Gaines County, TX outbreak. With the casing
   fix, this series now correctly spans 2022–2026 (244 weeks, not the 88
   we originally saw): a flat 0 baseline for three full years plus 7 more
   weeks, then a sharp spike (peak 50 cases/week at MMWR week 15) across
   weeks 8–21 of 2025, then back to ~0. Clean point-source anomaly with a
   long, genuine baseline — ideal for testing onset latency and false
   positives against a well-characterized zero baseline.
2. **2024 national pertussis resurgence** (`region="Total"`,
   `disease="Pertussis"`) — a real, well-documented, gradual multi-month
   surge (annual totals 862 → 2,512 → 11,145 → 8,989 → 2,902 across
   2022–2026). Complements event 1 by testing detection of a slow-building
   elevated baseline rather than a sharp spike.

Both will be used in `detection/` for the STL-residual vs. changepoint
head-to-head comparison (see project CLAUDE.md §6).

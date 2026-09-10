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

## Scripts

- `ingest_nndss.py` — pages through the Socrata API and writes a raw JSON
  snapshot to `raw/nndss_weekly_<date>.json`. This is the script the weekly
  ingestion Lambda will wrap.
- `eda.py` — loads the latest raw snapshot, builds a tidy
  `(region, disease, year, week) -> cases` panel, and writes it to
  `processed/nndss_weekly_panel.parquet`.

## Identified backtest events (Phase 1)

1. **2025 Texas measles outbreak** (`region="Texas"`, `disease="Measles,
   Indigenous"`) — the real Gaines County, TX outbreak. Cases go from a flat
   0 baseline for 7 weeks to a sharp spike (peak 50 cases/week at MMWR week
   15) across weeks 8–21, then return to ~0. Clean point-source anomaly —
   ideal for testing whether a detector flags onset with low latency and
   low false positives on the surrounding zero-baseline.
2. **2024 national pertussis resurgence** (`region="TOTAL"`,
   `disease="Pertussis"`) — a real, well-documented, gradual multi-month
   surge (annual totals 862 → 2,512 → 11,145 cases across 2022–2024).
   Complements event 1 by testing detection of a slow-building elevated
   baseline rather than a sharp spike.

Both will be used in `detection/` for the STL-residual vs. changepoint
head-to-head comparison (see project CLAUDE.md §6).

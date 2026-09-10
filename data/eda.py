"""Phase 1 EDA: load the raw NNDSS pull, build a tidy weekly panel, and
confirm the known outbreak events we'll backtest detection against.

Run after `python data/ingest_nndss.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent / "processed"


def load_latest_raw() -> pd.DataFrame:
    latest = sorted(RAW_DIR.glob("nndss_weekly_*.json"))[-1]
    rows = json.loads(latest.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    return df


def build_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Tidy weekly panel: one row per (state, disease, year, week)."""
    keep = ["states", "label", "year", "week", "m1"]
    panel = df[keep].rename(columns={"states": "region", "label": "disease", "m1": "cases"})
    panel = panel.sort_values(["region", "disease", "year", "week"]).reset_index(drop=True)
    return panel


def summarize(panel: pd.DataFrame) -> None:
    print(f"Panel rows: {len(panel):,}")
    print(f"Regions: {panel['region'].nunique()}  Diseases: {panel['disease'].nunique()}")
    print(f"Year range: {panel['year'].min()}-{panel['year'].max()}")


def check_known_outbreaks(panel: pd.DataFrame) -> None:
    print("\n=== Candidate backtest event 1: 2025 Texas measles outbreak ===")
    tx_measles = panel[
        (panel.region == "Texas")
        & (panel.disease == "Measles, Indigenous")
        & (panel.year == 2025)
    ].sort_values("week")
    print(tx_measles[["week", "cases"]].to_string(index=False))
    peak = tx_measles.loc[tx_measles["cases"].idxmax()]
    print(f"Peak: week {int(peak.week)} with {peak.cases:.0f} cases (baseline elsewhere in year: 0)")

    print("\n=== Candidate backtest event 2: 2024 national pertussis resurgence ===")
    pertussis_national = panel[
        (panel.region == "TOTAL") & (panel.disease == "Pertussis")
    ]
    yearly = pertussis_national.groupby("year")["cases"].sum()
    print(yearly.to_string())


def main() -> None:
    df = load_latest_raw()
    panel = build_panel(df)
    summarize(panel)
    check_known_outbreaks(panel)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "nndss_weekly_panel.parquet"
    panel.to_parquet(out_path, index=False)
    print(f"\nSaved tidy panel -> {out_path}")


if __name__ == "__main__":
    main()

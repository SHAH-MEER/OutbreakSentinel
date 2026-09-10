"""Pull weekly state-level notifiable disease case counts from CDC NNDSS.

Source: CDC Socrata dataset x9gk-5huc ("NNDSS Weekly Data") — the live,
rolling weekly table covering all 50 states, NYC, DC, and US territories
across ~139 notifiable diseases. Retains roughly the current + prior few
MMWR years; it is not a full historical archive.

Schema quirks handled here:
  - `m1` ("Current week" count) is *omitted* from a row when the count is
    zero and the corresponding `m1_flag` is "-". We fill these as 0.
  - Values arrive as strings; numeric columns are cast explicitly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import requests

SOCRATA_BASE = "https://data.cdc.gov/resource/x9gk-5huc.json"
PAGE_SIZE = 50000
RAW_DIR = Path(__file__).resolve().parent / "raw"

NUMERIC_COLS = ["m1", "m2", "m3", "m4"]


def fetch_all(where: str | None = None, page_size: int = PAGE_SIZE) -> list[dict]:
    """Page through the Socrata API and return every matching row."""
    rows: list[dict] = []
    offset = 0
    while True:
        params = {"$limit": page_size, "$offset": offset, "$order": ":id"}
        if where:
            params["$where"] = where
        resp = requests.get(SOCRATA_BASE, params=params, timeout=60)
        resp.raise_for_status()
        page = resp.json()
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
        time.sleep(0.2)  # be polite to the unauthenticated endpoint
    return rows


def clean(rows: list[dict]) -> list[dict]:
    """Cast numeric fields, filling the CDC's "no cases" omission with 0."""
    cleaned = []
    for row in rows:
        r = dict(row)
        for col in NUMERIC_COLS:
            raw = r.get(col)
            r[col] = float(raw) if raw not in (None, "") else 0.0
        r["year"] = int(r["year"])
        r["week"] = int(r["week"])
        cleaned.append(r)
    return cleaned


def save_raw(rows: list[dict], pull_date: dt.date | None = None) -> Path:
    pull_date = pull_date or dt.date.today()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"nndss_weekly_{pull_date.isoformat()}.json"
    out_path.write_text(json.dumps(rows), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--where",
        default=None,
        help="Optional Socrata SoQL $where clause to filter server-side "
        "(e.g. \"year='2025'\"). Omit to pull the full current dataset.",
    )
    args = parser.parse_args()

    rows = fetch_all(where=args.where)
    rows = clean(rows)
    out_path = save_raw(rows)
    print(f"Pulled {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    main()

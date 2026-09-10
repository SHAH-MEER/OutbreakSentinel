"""Production detection driver.

Runs the STL-residual detector (the method chosen in Phase 2's
head-to-head benchmark — see detection/README.md) over every (region,
disease) series in the latest processed panel, and returns the anomalies
flagged in the *most recent* MMWR week for each series — i.e. "is this
week's pull anomalous," which is what a weekly production run cares
about, not the whole history (that's what detection/backtest.py is for).

Note this was changepoint detection through most of Phase 2/3 — a region-
name casing bug (see data/README.md) was truncating backtest series short
enough that STL couldn't run its real seasonal decomposition and fell
back to a crude rolling-median mode, making it look structurally unable
to catch gradual surges. Fixing that bug let STL run properly, and it
now generalizes better (consistent 1-week detection latency on both
backtest events vs. changepoint's holdout latency of "never, within 12
weeks") — see detection/README.md for the full reversal writeup.

Parallelized across processes, AND shardable across separate Lambda
invocations: scoring is CPU-heavy enough that serially scoring the full
panel (~10.2k series, corrected) takes ~15 minutes — over half of a
Lambda's 900s hard cap on its own, before any of the usual production
margin (real Lambda vCPUs are typically slower per-core than a dev
machine; cold starts add more). So this is sharded exactly like
changepoint detection was: `infra/step_functions.tf` fans out a Map state
across `num_shards` parallel Lambda invocations, each scoring a
`num_shards`-fraction of the panel (selected by `shard_index`/`num_shards`
below) — comfortably under the timeout per invocation, with a large
safety margin instead of a razor-thin one.

Kept free of boto3/AWS so it can be unit-tested and run locally against a
parquet file; infra/lambda_app/handlers.py is the thin AWS wrapper around
this.
"""
from __future__ import annotations

import datetime as dt
import os
import zlib
from concurrent.futures import ProcessPoolExecutor
from functools import partial

import numpy as np
import pandas as pd

from detection.stl_baseline import detect

MIN_SERIES_LEN = 8  # too few points for segmentation to mean anything

# One series per worker call, not one point — group-level parallelism.
# Below this many series, process-pool startup overhead isn't worth it.
MIN_SERIES_FOR_PARALLEL = 50


def series_shard(region: str, disease: str, num_shards: int) -> int:
    """Deterministic (region, disease) -> shard assignment, stable across
    processes and runs. Python's built-in hash() is NOT stable across
    processes (string hashing is randomized per-process by default), so
    this uses crc32 instead."""
    key = f"{region}#{disease}".encode("utf-8")
    return zlib.crc32(key) % num_shards


def _score_one(
    item: tuple[str, str, np.ndarray, np.ndarray, np.ndarray], run_date_iso: str
) -> dict | None:
    region, disease, years, weeks, cases = item
    series = pd.Series(cases, dtype=float)
    result = detect(series, k=3.0)
    latest_idx = len(series) - 1
    if not bool(result.loc[latest_idx, "anomaly"]):
        return None
    return {
        "region_disease": f"{region}#{disease}",
        "week_id": f"{int(years[-1])}-W{int(weeks[-1]):02d}",
        "region": region,
        "disease": disease,
        "year": int(years[-1]),
        "week": int(weeks[-1]),
        "cases": float(cases[-1]),
        "severity": float(result.loc[latest_idx, "severity"]),
        "method": "stl",
        "detected_at": run_date_iso,
    }


def build_alerts(
    panel: pd.DataFrame,
    run_date: dt.date | None = None,
    max_workers: int | None = None,
    shard_index: int = 0,
    num_shards: int = 1,
) -> list[dict]:
    """`shard_index`/`num_shards`: score only the (region, disease) series
    assigned to this shard (see `series_shard`) — lets the full panel be
    split across independent Lambda invocations. Defaults to a single
    shard covering everything, for local/ad hoc use."""
    run_date = run_date or dt.date.today()
    run_date_iso = run_date.isoformat()

    items = []
    for (region, disease), group in panel.groupby(["region", "disease"], sort=False):
        if num_shards > 1 and series_shard(region, disease, num_shards) != shard_index:
            continue
        if len(group) < MIN_SERIES_LEN:
            continue
        group = group.sort_values(["year", "week"])
        items.append(
            (region, disease, group["year"].to_numpy(), group["week"].to_numpy(), group["cases"].to_numpy())
        )

    score = partial(_score_one, run_date_iso=run_date_iso)
    max_workers = max_workers if max_workers is not None else (os.cpu_count() or 1)

    if max_workers <= 1 or len(items) < MIN_SERIES_FOR_PARALLEL:
        results = [score(item) for item in items]
    else:
        chunksize = max(1, len(items) // (max_workers * 4))
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(score, items, chunksize=chunksize))

    return [r for r in results if r is not None]


def main() -> None:
    panel = pd.read_parquet("data/processed/nndss_weekly_panel.parquet")
    alerts = build_alerts(panel)
    n_series = panel[["region", "disease"]].drop_duplicates().shape[0]
    print(f"{len(alerts)} anomalies flagged in the latest MMWR week across {n_series} series")
    for a in sorted(alerts, key=lambda a: -a["severity"])[:20]:
        print(a)


if __name__ == "__main__":
    main()

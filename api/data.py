"""Data access layer for the API.

Two data sources, each with a local-dev fallback so this can run and be
tested without any AWS deployment:

- **Alerts**: DynamoDB (`ALERTS_TABLE` env var) in production, written by
  the Detect Lambda (infra/lambda_app/handlers.py). Locally, computed on
  the fly from the processed panel via `detection.run_detection` — capped
  to a sample for interactive dev speed (see `DEV_SAMPLE_SERIES`; scoring
  the full ~10.2k-series panel takes minutes, not something you want to
  wait on every API restart).
- **Series history**: the processed panel — from S3 (`PROCESSED_BUCKET`)
  in production, or the local parquet file in dev.

Both are cached in memory for the life of the process; this is a
read-mostly demo API, not a system serving live writes.
"""
from __future__ import annotations

import os
from functools import lru_cache

import pandas as pd

from data.eda import PROCESSED_DIR
from detection.run_detection import build_alerts
from detection.stl_baseline import detect

ALERTS_TABLE = os.environ.get("ALERTS_TABLE")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET")
LOCAL_PANEL_PATH = os.environ.get("LOCAL_PANEL_PATH") or str(PROCESSED_DIR / "nndss_weekly_panel.parquet")

# Local-dev only: scoring the full panel serially takes minutes (see
# detection/README.md) — fine for a weekly batch Lambda, not for an
# interactive `uvicorn --reload` loop. Sampled alerts always include the
# two documented backtest series so the dashboard has guaranteed,
# recognizable content to show.
DEV_SAMPLE_SERIES = int(os.environ.get("DEV_SAMPLE_SERIES", "3000"))
GUARANTEED_SERIES = [
    ("Texas", "Measles, Indigenous"),
    ("Total", "Pertussis"),
]


def _load_panel_from_s3() -> pd.DataFrame:
    import boto3

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=PROCESSED_BUCKET, Prefix="nndss_panel_"):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    if not keys:
        raise FileNotFoundError(f"No processed panel found in s3://{PROCESSED_BUCKET}")
    latest_key = sorted(keys)[-1]
    local_path = f"/tmp/{latest_key.split('/')[-1]}"
    s3.download_file(PROCESSED_BUCKET, latest_key, local_path)
    return pd.read_parquet(local_path)


@lru_cache(maxsize=1)
def _panel() -> pd.DataFrame:
    if PROCESSED_BUCKET:
        return _load_panel_from_s3()
    return pd.read_parquet(LOCAL_PANEL_PATH)


def _sample_panel_for_dev(panel: pd.DataFrame) -> pd.DataFrame:
    keys = panel[["region", "disease"]].drop_duplicates()
    sample_keys = keys.sample(n=min(DEV_SAMPLE_SERIES, len(keys)), random_state=42)
    guaranteed = pd.DataFrame(GUARANTEED_SERIES, columns=["region", "disease"])
    sample_keys = pd.concat([sample_keys, guaranteed]).drop_duplicates()
    return panel.merge(sample_keys, on=["region", "disease"])


def _scan_dynamodb_alerts() -> list[dict]:
    import boto3
    from boto3.dynamodb.conditions import Attr  # noqa: F401  (kept for future filtered scans)

    table = boto3.resource("dynamodb").Table(ALERTS_TABLE)
    items: list[dict] = []
    kwargs: dict = {}
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


@lru_cache(maxsize=1)
def _dev_alerts() -> list[dict]:
    sample = _sample_panel_for_dev(_panel())
    return build_alerts(sample)


def get_alerts(region: str | None = None, disease: str | None = None, min_severity: float = 0.0) -> list[dict]:
    items = _scan_dynamodb_alerts() if ALERTS_TABLE else _dev_alerts()
    if region:
        items = [i for i in items if i["region"] == region]
    if disease:
        items = [i for i in items if i["disease"] == disease]
    if min_severity:
        items = [i for i in items if float(i["severity"]) >= min_severity]
    return sorted(items, key=lambda i: -float(i["severity"]))


def get_series(region: str, disease: str) -> dict | None:
    panel = _panel()
    sub = panel[(panel.region == region) & (panel.disease == disease)].sort_values(["year", "week"])
    if sub.empty:
        return None

    result = detect(sub["cases"].reset_index(drop=True), k=3.0)
    return {
        "region": region,
        "disease": disease,
        "weeks": [f"{int(y)}-W{int(w):02d}" for y, w in zip(sub["year"], sub["week"])],
        "cases": sub["cases"].tolist(),
        "anomaly": result["anomaly"].tolist(),
        "severity": result["severity"].tolist(),
    }


def list_regions_and_diseases() -> dict:
    panel = _panel()
    return {
        "regions": sorted(panel["region"].unique().tolist()),
        "diseases": sorted(panel["disease"].unique().tolist()),
    }

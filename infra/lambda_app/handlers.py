"""AWS Lambda entrypoints for the weekly NNDSS pipeline.

Kept deliberately thin: all real logic lives in `data/` and `detection/`,
which are pure pandas/stdlib modules, unit-tested without any AWS
dependency. These handlers just wire that logic to S3/DynamoDB and are
invoked in sequence by the Step Functions state machine defined in
infra/step_functions.tf:

    Ingest -> Process -> Detect

Each handler's return value becomes the next state's input (Step
Functions passes it through automatically), so the small dicts below
double as the interface between pipeline stages.
"""
from __future__ import annotations

import json
import os
import time

import boto3
import pandas as pd

from data.eda import build_panel
from data.ingest_nndss import clean, fetch_all
from detection.run_detection import build_alerts

RAW_BUCKET = os.environ.get("RAW_BUCKET")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET")
ALERTS_TABLE = os.environ.get("ALERTS_TABLE")

_s3 = boto3.client("s3")
_dynamodb = boto3.resource("dynamodb")


def ingest_handler(event, context):
    """Pull the latest NNDSS data from CDC and land it in the raw S3 zone."""
    rows = clean(fetch_all())
    raw_key = f"nndss_weekly_{time.strftime('%Y-%m-%d')}.json"
    _s3.put_object(Bucket=RAW_BUCKET, Key=raw_key, Body=json.dumps(rows))
    return {"raw_key": raw_key, "row_count": len(rows)}


def process_handler(event, context):
    """Build the tidy (region, disease, year, week, cases) panel and land
    it in the processed S3 zone."""
    raw_key = event["raw_key"]
    obj = _s3.get_object(Bucket=RAW_BUCKET, Key=raw_key)
    rows = json.loads(obj["Body"].read())

    panel = build_panel(pd.DataFrame(rows))
    processed_key = raw_key.replace("nndss_weekly_", "nndss_panel_").replace(".json", ".parquet")
    local_path = f"/tmp/{processed_key}"
    panel.to_parquet(local_path, index=False)
    _s3.upload_file(local_path, PROCESSED_BUCKET, processed_key)
    return {"processed_key": processed_key}


def detect_handler(event, context):
    """Run the changepoint detector over this shard's slice of series and
    write flagged anomalies for the latest week to DynamoDB.

    `shard_index`/`num_shards` come from the Step Functions Map state
    (infra/step_functions.tf) — each of the `num_shards` parallel Lambda
    invocations scores a disjoint ~1/num_shards fraction of the panel, so
    each invocation finishes well inside the timeout even though scoring
    the whole panel serially would not (see detection/run_detection.py).
    Default 0/1 (the whole panel, single invocation) covers manual/ad hoc
    invocation outside the Map state.
    """
    processed_key = event["processed_key"]
    shard_index = event.get("shard_index", 0)
    num_shards = event.get("num_shards", 1)

    local_path = f"/tmp/{processed_key}"
    _s3.download_file(PROCESSED_BUCKET, processed_key, local_path)

    panel = pd.read_parquet(local_path)
    alerts = build_alerts(panel, shard_index=shard_index, num_shards=num_shards)

    table = _dynamodb.Table(ALERTS_TABLE)
    with table.batch_writer() as batch:
        for alert in alerts:
            batch.put_item(Item=alert)
    return {"alerts_written": len(alerts), "shard_index": shard_index}

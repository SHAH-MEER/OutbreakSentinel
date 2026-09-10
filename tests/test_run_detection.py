import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detection.run_detection import build_alerts, series_shard  # noqa: E402


def _series_rows(region: str, disease: str, values: list[float]) -> list[dict]:
    return [
        {"region": region, "disease": disease, "year": 2024, "week": i + 1, "cases": v}
        for i, v in enumerate(values)
    ]


def test_flags_series_with_anomalous_latest_week():
    rows = _series_rows("Texas", "Measles, Indigenous", [2.0] * 20 + [80.0])
    panel = pd.DataFrame(rows)
    alerts = build_alerts(panel)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["region_disease"] == "Texas#Measles, Indigenous"
    assert alert["week_id"] == "2024-W21"
    assert alert["cases"] == 80.0
    assert alert["method"] == "changepoint"


def test_does_not_flag_stable_series():
    rows = _series_rows("California", "Mumps", [5.0] * 20)
    panel = pd.DataFrame(rows)
    alerts = build_alerts(panel)
    assert alerts == []


def test_skips_series_shorter_than_min_length():
    rows = _series_rows("Guam", "Cholera", [0.0, 0.0, 50.0])
    panel = pd.DataFrame(rows)
    alerts = build_alerts(panel)
    assert alerts == []


def test_handles_multiple_independent_series():
    rows = _series_rows("Texas", "Measles, Indigenous", [2.0] * 20 + [80.0])
    rows += _series_rows("California", "Mumps", [5.0] * 21)
    panel = pd.DataFrame(rows)
    alerts = build_alerts(panel)
    assert len(alerts) == 1
    assert alerts[0]["region"] == "Texas"


def test_parallel_path_matches_serial_path():
    # Force the ProcessPoolExecutor branch (needs >= MIN_SERIES_FOR_PARALLEL
    # series) and check it agrees with the serial path — this is the only
    # test that would catch a pickling/spawn regression in the parallel
    # code path (small panels in the other tests never leave it).
    rows = []
    for i in range(60):
        region, disease = f"Region{i}", "Disease"
        values = [5.0] * 20 + ([80.0] if i == 0 else [5.0])
        rows += _series_rows(region, disease, values)
    panel = pd.DataFrame(rows)

    serial = build_alerts(panel, max_workers=1)
    parallel = build_alerts(panel, max_workers=2)

    assert len(serial) == 1
    assert sorted(a["region_disease"] for a in serial) == sorted(a["region_disease"] for a in parallel)


def test_series_shard_is_stable_across_calls():
    # Must be deterministic across process restarts, unlike Python's
    # built-in hash() for strings (randomized per-process). This is what
    # lets a sharded Lambda invocation reliably own the same subset of
    # series every run.
    assert series_shard("Texas", "Measles, Indigenous", 10) == series_shard("Texas", "Measles, Indigenous", 10)


def test_series_shard_distributes_across_range():
    shards = {series_shard(f"Region{i}", "Disease", 10) for i in range(100)}
    assert shards == set(range(10))


def test_build_alerts_only_scores_its_own_shard():
    # 20 series, each with its own anomalous spike — every shard should
    # find exactly the anomalies belonging to series assigned to it, and
    # summing across all shards should reproduce the unsharded result.
    rows = []
    for i in range(20):
        rows += _series_rows(f"Region{i}", "Disease", [5.0] * 20 + [80.0])
    panel = pd.DataFrame(rows)

    unsharded = build_alerts(panel)
    assert len(unsharded) == 20

    num_shards = 4
    sharded_alerts = []
    for shard_index in range(num_shards):
        alerts = build_alerts(panel, shard_index=shard_index, num_shards=num_shards)
        for alert in alerts:
            assert series_shard(alert["region"], alert["disease"], num_shards) == shard_index
        sharded_alerts += alerts

    assert sorted(a["region_disease"] for a in sharded_alerts) == sorted(a["region_disease"] for a in unsharded)

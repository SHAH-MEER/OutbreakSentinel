import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detection import changepoint, stl_baseline  # noqa: E402


def test_stl_fallback_used_for_short_series():
    series = pd.Series([1.0] * 20 + [50.0] + [1.0] * 20)
    result = stl_baseline.detect(series, k=3.0)
    assert result.attrs["method"] == "rolling_median"
    assert result.loc[20, "anomaly"]
    assert not result.loc[0, "anomaly"]


def test_stl_uses_seasonal_decomposition_for_long_series():
    # 4 full seasonal cycles: STL needs several cycles' worth of history for
    # its seasonal smoother to average a spike into the residual rather
    # than absorbing it into the per-phase seasonal fit (see stl_baseline.detect).
    rng = np.random.default_rng(0)
    n = 208
    seasonal = 5 * np.sin(np.arange(n) * 2 * np.pi / 52)
    noise = rng.normal(0, 0.5, n)
    values = 10 + seasonal + noise
    values[150] += 40  # inject a sharp spike
    series = pd.Series(values)

    result = stl_baseline.detect(series, k=3.0)
    assert result.attrs["method"] == "stl"
    assert result.loc[150, "anomaly"]


def test_stl_severity_is_bounded_on_near_constant_sparse_series():
    # Regression test: a long, mostly-zero rare-disease series (real
    # example: Q fever in a low-incidence region) makes STL's residual
    # floating-point noise on the order of 1e-11 for most weeks. Before
    # the NOISE_FLOOR_SCALE fix, that noise was used directly as the
    # scale, producing severity scores in the hundreds of billions for
    # a real but modest 3-case bump — meaningless and dashboard-breaking.
    rng = np.random.default_rng(2)
    values = rng.choice([0.0, 0.0, 0.0, 0.0, 1.0], size=243).tolist() + [3.0]
    series = pd.Series(values)

    result = stl_baseline.detect(series, k=3.0)
    assert result.attrs["method"] == "stl"
    assert result["severity"].max() < 1000


def test_changepoint_flags_sustained_mean_shift():
    baseline = [10.0] * 40
    surge = [60.0] * 20
    series = pd.Series(baseline + surge)

    result = changepoint.detect(series, pen_scale=3.0, k=2.0)
    assert result.loc[:39, "anomaly"].sum() == 0
    assert result.loc[40:, "anomaly"].all()


def test_changepoint_no_false_positive_on_flat_series():
    rng = np.random.default_rng(1)
    series = pd.Series(10 + rng.normal(0, 0.2, 60))
    result = changepoint.detect(series, pen_scale=5.0, k=3.0)
    assert result["anomaly"].sum() == 0

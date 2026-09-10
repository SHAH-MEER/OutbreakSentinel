"""Changepoint-based anomaly detector.

Standardizes a weekly count series by its robust scale (median absolute
deviation), segments it with `ruptures` (PELT, L2 cost), and flags any
segment whose mean deviates from the series-wide median by more than
k * MAD as anomalous. Segment-relative severity puts both a single sharp
spike and a sustained elevated plateau on a comparable scale.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import ruptures as rpt


def _mad_scale(values: np.ndarray) -> tuple[float, float]:
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    scale = mad if mad > 0 else (float(values.std()) or 1.0)
    return median, scale


def _segments(standardized: np.ndarray, pen_scale: float) -> list[tuple[int, int]]:
    n = len(standardized)
    penalty = pen_scale * np.log(max(n, 2))
    algo = rpt.Pelt(model="l2").fit(standardized.reshape(-1, 1))
    bkps = algo.predict(pen=penalty)
    starts = [0] + bkps[:-1]
    return list(zip(starts, bkps))


def detect(series: pd.Series, pen_scale: float = 1.5, k: float = 2.0) -> pd.DataFrame:
    """Detect anomalies in a gap-free weekly count series.

    Returns a DataFrame aligned to `series.index` with columns:
      - segment_mean: mean case count of the segment each week belongs to
      - severity: |segment_mean - baseline_median| / MAD
      - anomaly: bool, severity > k
    """
    series = series.astype(float)
    values = series.values
    baseline_median, scale = _mad_scale(values)
    standardized = (values - baseline_median) / scale

    segment_mean = np.zeros(len(values))
    severity = np.zeros(len(values))
    anomaly = np.zeros(len(values), dtype=bool)

    for start, end in _segments(standardized, pen_scale):
        seg_mean = values[start:end].mean()
        sev = abs(seg_mean - baseline_median) / scale
        segment_mean[start:end] = seg_mean
        severity[start:end] = sev
        anomaly[start:end] = sev > k

    return pd.DataFrame(
        {"segment_mean": segment_mean, "severity": severity, "anomaly": anomaly},
        index=series.index,
    )

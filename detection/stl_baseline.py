"""STL-residual baseline anomaly detector.

Decomposes a weekly count series into trend + seasonal + residual via STL
(when there is enough history for a reliable seasonal cycle) and flags
points whose residual exceeds k * IQR-derived scale as anomalous. Falls
back to rolling-median detrending when there isn't enough history for STL
— many NNDSS state-level rare-disease series have well under two years of
data, so STL (which needs >= 2 full periods) simply cannot run on them.
"""
from __future__ import annotations

import pandas as pd
from statsmodels.tsa.seasonal import STL

SEASONAL_PERIOD = 52
MIN_STL_LEN = 2 * SEASONAL_PERIOD


# NNDSS counts are whole cases, so no real, meaningful week-to-week
# variation is smaller than 1 case. A scale below this is either exact-
# zero (a genuinely constant series), STL floating-point noise (~1e-11,
# on a near-constant series), or — found via a real example at exactly
# MIN_STL_LEN=104 — a near-degenerate STL fit that isn't literally
# floating-point noise but is just as meaningless: at exactly 2 seasonal
# cycles, the smoother has only 2 points per phase bin to fit and can
# nearly interpolate through most of a sparse series, leaving a highly
# bimodal residual whose IQR straddles near-zero for most points (~1e-5
# here, not ~1e-11, so a small epsilon check doesn't catch it — an
# unconditional floor on the final scale does). Any of these, used
# directly as a severity denominator, produces scores in the thousands
# to billions for a real but modest case-count bump (see
# detection/README.md) — meaningless, and dashboard-breaking.
NOISE_FLOOR_SCALE = 1.0


def _iqr_scale(residual: pd.Series, k: float) -> tuple[float, float]:
    q1, q3 = residual.quantile([0.25, 0.75])
    iqr = q3 - q1
    if iqr <= 0:
        iqr = (residual - residual.median()).abs().median()
    scale = max(iqr, NOISE_FLOOR_SCALE)
    return -k * scale, k * scale


def detect(series: pd.Series, k: float = 3.0) -> pd.DataFrame:
    """Detect anomalies in a gap-free weekly count series.

    Returns a DataFrame aligned to `series.index` with columns:
      - trend: the fitted trend(+seasonal) baseline
      - residual: series - trend
      - severity: |residual| standardized by the IQR-derived scale
      - anomaly: bool, residual outside +/- k * IQR-derived bounds
    `series.attrs`-style method name is stored on the result's `.attrs["method"]`
    ("stl" or "rolling_median").
    """
    series = series.astype(float)

    if len(series) >= MIN_STL_LEN:
        # A wide seasonal-smoother window (`seasonal`, must be > period and
        # odd) is deliberate: with statsmodels' default (7), a single sharp
        # spike gets absorbed into the seasonal component (fit per-phase
        # across cycle-subseries) rather than flagged as a residual outlier,
        # since each phase bin has few points to average against. Widening
        # the window forces the seasonal fit to average over many cycles,
        # pushing point anomalies back into the residual where they belong.
        stl = STL(series, period=SEASONAL_PERIOD, robust=True, seasonal=SEASONAL_PERIOD + 1).fit()
        trend = stl.trend + stl.seasonal
        method = "stl"
    else:
        window = max(5, min(13, len(series) // 4 or 1))
        trend = series.rolling(window, center=True, min_periods=1).median()
        method = "rolling_median"

    residual = series - trend
    lower, upper = _iqr_scale(residual, k)
    scale = (upper - lower) / (2 * k) if k > 0 else 1.0
    scale = scale if scale > 0 else 1.0

    out = pd.DataFrame(
        {
            "trend": trend,
            "residual": residual,
            "severity": (residual / scale).abs(),
            "anomaly": (residual < lower) | (residual > upper),
        },
        index=series.index,
    )
    out.attrs["method"] = method
    return out

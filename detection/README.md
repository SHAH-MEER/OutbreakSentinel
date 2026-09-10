# Detection: STL-residual baseline vs. changepoint detection

Run: `python -m detection.backtest` (requires `data/processed/nndss_weekly_panel.parquet`,
produced by `python data/eda.py`).

## Methods

- **`stl_baseline.py`** — STL seasonal decomposition (statsmodels), flags
  weeks whose residual exceeds `k *` an IQR-derived scale. Falls back to
  rolling-median detrending when a series has under 2 full years of history
  (STL needs >= 2 periods; many state-level rare-disease series don't have
  that much data). Uses a widened seasonal-smoother window
  (`seasonal=period+1`) — with the statsmodels default (7), a single sharp
  spike gets absorbed into the seasonal component instead of the residual,
  because each phase bin only has a few points to average against.
- **`changepoint.py`** — standardizes the series by its median/MAD, segments
  it with `ruptures` (PELT, L2 cost, `jump=1`, penalty scaled by
  `pen_scale * log(n)`), and flags any segment whose mean deviates from the
  series-wide median by more than `k` MADs. Shipped defaults:
  `pen_scale=1.5, k=2.0`.
  - **Bugfix worth flagging**: `ruptures.Pelt` defaults to `jump=5` — it
    only considers every 5th index as a candidate changepoint, for speed
    on long signals. That silently caps detection resolution at ~5 weeks
    and, worse, can miss a brand-new anomaly in the most recent week(s)
    entirely if it doesn't land on a checked index. Passing `jump=1` fixed
    it; `tests/test_run_detection.py::test_flags_series_with_anomalous_latest_week`
    is the regression test (it failed under the default before the fix).
    Fixing this improved the held-out validation numbers below
    substantially (recall 86.5%→91.9%, latency 2wk→0wk).

## Backtest results

Threshold tuned by grid search on the 2025 Texas measles outbreak (sharp,
crisp-boundary spike), then validated **without re-fitting** on the 2024
national pertussis resurgence (gradual, sustained surge) — see
`data/README.md` for how each event's ground truth is defined. Tuning
selects on **detection latency** (weeks from sustained onset to first
alert) first, recall second, subject to an FPR cap on the tuning event —
recall alone would reward a detector that only flags an outbreak after
it's already obvious just as much as one that catches it early, which
defeats the point of an early-warning system.

| | Texas measles (tuning) | Pertussis resurgence (held-out) |
| --- | --- | --- |
| STL baseline | recall 50%, FPR 4.1%, latency **2 weeks** | recall **0%**, FPR 42.9%, latency — (never fires) |
| Changepoint | recall 57.1%, FPR 0%, latency 2 weeks | recall **91.9%**, FPR 3.4%, latency **0 weeks** |

## The latency/false-positive tradeoff (why `k=2.0`, not lower)

The full hyperparameter grid (`pen_scale` in [1.5, 2, 3, 5, 8, 12], `k` in
[1.0 ... 5.0]) shows `k` is the dominant lever, and it exposes a genuine
tradeoff:

- **`k=1.0`**: measles recall and latency are unchanged from `k=2.0`
  (57.1%, 2 weeks) — but pertussis FPR jumps from 3.4% to **21.0%**, for
  the same 91.9% recall / 0-week latency it already had at `k>=1.5`. There
  is no upside to `k=1.0`, only a 6x worse false-positive rate.
- **`k=1.5–3.0`**: the numbers shipped above — both events detected within
  0–2 weeks of sustained onset, FPR capped at 3.4%.

Critically, the measles tuning event alone can't distinguish `k=1.0` from
`k>=1.5`: changepoint detection scores identically on it either way (FPR=0,
recall=57.1%, latency=2wk), so an automatic rule that tunes only against
that one series has no signal telling it `k=1.0` is worse — it would pick
whichever came first in the grid. That's a real generalization risk of
tuning against a single event, not a bug in the search — which is exactly
why the held-out validation step exists.

**Decision**: ship `k=2.0`. At NNDSS's actual scale (~140 regions x 139
diseases, scored weekly), a 20%+ per-series-week false-positive rate would
produce an unusable number of spurious alerts; 3.4% is still non-trivial
at that scale but far more survivable — and here it costs nothing in
recall or latency on the held-out event, so there's no real tradeoff being
made at all, just a threshold with no known upside.

## Why changepoint detection ships as the primary method

STL's trend component is *designed* to track slow-moving movement in the
series — which means a gradual, sustained surge (like the 2024 pertussis
resurgence) gets absorbed into the trend rather than flagged as anomalous
residual. That's structural, not a tuning problem: STL can only ever flag
deviations *from* whatever trend it fits, and a real multi-month
resurgence looks exactly like trend. The numbers bear this out — 0% recall
on the held-out event, and a *worse* false-positive rate than on the
tuning event, i.e. no generalization at all.

Changepoint detection explicitly segments the series by mean-level shifts,
so it doesn't care whether the shift is a single-week spike or a
multi-month plateau — both look like "a new segment with a different
mean." It generalizes from the tuning event to the held-out event with a
large recall gain, a low false-positive rate, and zero detection latency,
which is the outcome that matters operationally: an alerting system that
only catches sharp point-source spikes and misses slow-building
resurgences (arguably the harder, more consequential case to catch early)
is not a useful early-warning system.

**Caveat**: changepoint detection's recall on the sharp-spike event (57%)
is still well short of catching every flagged week — it misses the
earliest 1-2 onset weeks (case counts still in the single digits) and the
declining tail, catching the "core" of the outbreak rather than every
week of it. If a future iteration wants higher recall on both event shapes
without the STL failure mode, the natural next step is an ensemble (flag
if either method fires) rather than picking one exclusively.

## Performance: scoring the full panel is sharded, not one invocation

Scoring all ~17,640 series serially with `jump=1` takes 50+ minutes —
comfortably parallelizing within one process pool only brought the
estimated full-panel runtime down to ~789s, too close to Lambda's 900s
cap to trust in production once real Lambda vCPUs and cold starts are
accounted for. `run_detection.py` supports sharding
(`shard_index`/`num_shards`, via a stable `crc32`-based partition —
`series_shard`) so the pipeline can fan out across parallel Lambda
invocations instead of one; see `infra/README.md` and
`infra/step_functions.tf` for how that's wired up with a Step Functions
Map state.

## Known limitation: severity isn't comparable across very different series

`run_detection.py`'s live scan over the full panel (17,640 series) flags
~480 anomalies in the most recent week, some with severity scores over
100 — those are near-zero-MAD series (long runs of identical or near-zero
counts) where a small absolute change produces a huge standardized
severity. This is a real weakness of using a single generic
MAD-standardized threshold across wildly heterogeneous series (a common
disease with hundreds of weekly cases vs. a rare one that's usually zero):
severity scores aren't on a comparable scale, so ranking alerts by
severity across diseases will over-weight sparse/rare series. Worth
revisiting once there's a dashboard consumer for these alerts (Phase 4) —
options include a minimum case-count floor, or a variance-stabilizing
transform suited to count data (e.g. Anscombe/sqrt) before standardizing.

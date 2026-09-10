# Detection: STL-residual baseline vs. changepoint detection

Run: `python -m detection.backtest` (requires `data/processed/nndss_weekly_panel.parquet`,
produced by `python data/eda.py`).

## Note: this reverses an earlier conclusion in this project

Through most of Phase 2/3, this doc shipped changepoint detection as the
primary method and STL as "structurally unable to catch gradual surges."
That conclusion turned out to rest on a data bug, not a real limitation —
see "Why the original conclusion was wrong" below. **STL now ships as the
primary method.** The two bugs that led here are both worth reading if
you're auditing this project's rigor, not just its final numbers:
`ruptures.Pelt`'s `jump=5` default (changepoint.py) and CDC's silent
region-name casing change (data/README.md).

## Methods

- **`stl_baseline.py`** — STL seasonal decomposition (statsmodels), flags
  weeks whose residual exceeds `k *` an IQR-derived scale. Falls back to
  rolling-median detrending when a series has under 2 full years of history
  (STL needs >= 2 periods). Uses a widened seasonal-smoother window
  (`seasonal=period+1`) — with the statsmodels default (7), a single sharp
  spike gets absorbed into the seasonal component instead of the residual,
  because each phase bin only has a few points to average against. Shipped
  default: `k=3.0`.
- **`changepoint.py`** — standardizes the series by its median/MAD, segments
  it with `ruptures` (PELT, L2 cost, `jump=1`, penalty scaled by
  `pen_scale * log(n)`), and flags any segment whose mean deviates from the
  series-wide median by more than `k` MADs. Documented as the alternative
  method below, not shipped. Defaults: `pen_scale=1.5, k=2.0`.
  - **Bugfix worth flagging on its own**: `ruptures.Pelt` defaults to
    `jump=5` — it only considers every 5th index as a candidate
    changepoint, for speed on long signals. That silently caps detection
    resolution at ~5 weeks and, worse, can miss a brand-new anomaly in
    the most recent week(s) entirely if it doesn't land on a checked
    index. Passing `jump=1` fixed it;
    `tests/test_run_detection.py::test_flags_series_with_anomalous_latest_week`
    is the regression test (it failed under the default before the fix).
    This bug is real and independent of the casing bug below — it's
    still worth knowing about even though changepoint isn't the shipped
    method.

## Why the original conclusion was wrong

The original backtest data had a real bug: CDC's NNDSS feed silently
changed region-name casing at the 2024→2025 boundary (`"TEXAS"` →
`"Texas"`, same region — see data/README.md), and the fix wasn't applied
until after Phase 2/3's initial numbers had already shipped. That
truncated the Texas measles series to 88 weeks (only the post-switch
years were visible under the "Texas" spelling being queried) — just
short of STL's 104-week minimum for real seasonal decomposition, so it
silently ran in the rolling-median fallback mode instead. That fallback
is a much cruder detrending method, and it made STL look structurally
incapable of generalizing to the pertussis resurgence (0% holdout
recall). Once the casing bug was fixed, the measles series correctly
became 244 weeks (2022–2026), comfortably over the STL threshold — and
with *real* STL running, the conclusion flips.

This is why both bugs are documented prominently rather than quietly
patched over: the changepoint-detection conclusion wasn't wrong because
of bad reasoning, it was wrong because of an undetected data problem
upstream of the model entirely. That's a more common and more dangerous
failure mode than a bad model choice.

## Backtest results (corrected data)

Threshold tuned by grid search on the 2025 Texas measles outbreak (sharp
spike, now correctly 244 weeks including 3 years of genuine zero
baseline), then validated **without re-fitting** on the 2024 national
pertussis resurgence (gradual, sustained surge) — see `data/README.md`
for how each event's ground truth is defined. Tuning selects on
**detection latency** (weeks from sustained onset to first alert) first,
recall second, FPR as a final tie-break — recall alone would reward a
detector that only flags an outbreak after it's already obvious just as
much as one that catches it early, which defeats the point of an
early-warning system.

| | Texas measles (tuning) | Pertussis resurgence (held-out) |
| --- | --- | --- |
| STL baseline (`k=3.0`) | recall 78.6%, FPR 0.9%, latency **1 week** | recall **64.9%**, FPR 7.2%, latency **1 week** |
| Changepoint (`pen=1.5, k=2.0`) | recall 57.1%, FPR 0%, latency 2 weeks | recall 62.2%, FPR 4.3%, latency **— (never, within 12wk)** |

STL wins on the metric that matters most operationally: it detects both
events within 1 week of sustained onset, consistently. Changepoint's
"safe" (low-FPR) configurations, checked against the corrected holdout
data, don't fire on the pertussis surge within the 12-week detection
window at all — despite eventually contributing to a similar overall
recall number elsewhere in the series. A detector that's *eventually*
right but doesn't say so until well after the fact isn't much of an
early-warning system. STL's holdout FPR (7.2%) is higher than
changepoint's (4.3%), but a full-panel sanity check (800 random series)
found STL (`k=3.0`) and changepoint's shipped defaults produce
comparable real-world flag rates in practice — 5.0% vs. 4.3% — so the
backtest-measured gap doesn't translate into a wildly noisier production
system.

## Why STL's own threshold choice needed a guardrail too

`k` is **pinned to 3.0 in code**, not auto-selected by grid search
against the tuning event — that approach failed twice, for two different
reasons, and both are worth knowing:

1. On the measles tuning event alone, STL's recall and latency are
   **identical across most of the `k` range** (a wide plateau) — only
   FPR changes, monotonically decreasing as `k` grows. An automatic rule
   optimizing the tuning event alone has nothing telling it that pushing
   `k` higher eventually wrecks holdout latency (checked manually: `k=5`
   pushes the pertussis holdout to missing the surge within the 12-week
   window entirely).
2. After fixing the severity-scale bug below, re-running the automatic
   search picked `k=0.75` — the *lowest* FPR on the tuning event this
   time, not the highest `k`. Same underlying problem, opposite
   direction: `k=0.75` looked best on the one event being tuned against
   (FPR 3.0%) but generalizes badly (holdout FPR 30.9%, vs. 7.2% at
   `k=3.0`).

Both failures are the same lesson from two different angles: a single
tuning event can tell you a threshold generalizes *worse* than another,
but it can never tell you one generalizes *better* — there's no signal
in one event alone that rules out overfitting to it. `k=3.0` is a
manual pick from a full sweep against **both** events (`k` from 0.5 to
10, all reproducible via `detection.stl_baseline.detect` directly) — it
sits with real margin inside the region where 1-week latency holds on
both events (`k` in roughly [0.75, 4.0]) while getting a strong FPR on
both (0.9% tune / 7.2% holdout), rather than chasing whichever extreme a
single-event search finds attractive.

## Why changepoint detection is documented, not shipped

Changepoint detection isn't a bad method — it hits 0% FPR on the tuning
event and reasonable recall on both — but on the corrected data, every
configuration with a defensible false-positive rate misses the pertussis
surge within a reasonable detection window on holdout. STL's trend
component tracks slow-moving movement, which used to be framed as a
weakness (it can absorb a real gradual surge into "just trend"); with
enough real history behind it, that same behavior lets it establish a
meaningful seasonal baseline and flag deviations from it promptly on both
a sharp spike and a slow surge. Changepoint's segment-based approach,
by contrast, needs enough evidence to confidently place a new segment
boundary — which is inherently in tension with detecting *early*, before
much evidence has accumulated.

**Caveat**: STL's holdout FPR (7.2%) is genuinely higher than
changepoint's holdout FPR (4.3%), even if the full-panel check above
suggests it's not disastrous in practice. If a future iteration wants
lower FPR without giving up STL's latency advantage, the natural next
step is an ensemble (e.g. only alert if STL fires two weeks running) or
revisiting the IQR-based threshold to be less sensitive to the specific
IQR shape of a given series.

## Performance: scoring the full panel is sharded, not one invocation

Scoring all ~10.2k series (post-casing-fix) with STL takes ~884s
serially — over half of Lambda's 900s hard cap on its own, before any of
the usual production margin (real Lambda vCPUs are typically slower
per-core than a dev machine; cold starts add more). `run_detection.py`
supports sharding (`shard_index`/`num_shards`, via a stable
`crc32`-based partition — `series_shard`) so the pipeline fans out across
parallel Lambda invocations instead of running one; see
`infra/README.md` and `infra/step_functions.tf` for how that's wired up
with a Step Functions Map state.

## Fixed bug: severity blowup on near-constant sparse series

Found while building the production driver: a long, mostly-zero
rare-disease series (real example: Q fever in a low-incidence region)
makes STL's residual pure floating-point noise (~1e-11) for most weeks —
not a meaningful measure of variation. Using that noise directly as the
severity-scaling denominator produced severity scores in the **hundreds
of billions** for a real but modest 3-case bump.

The first fix attempt used an epsilon check (fall back to a floor only
when the computed IQR/MAD was below `1e-6`), which caught that case but
missed a second, subtler one: a real series at exactly
`MIN_STL_LEN=104` weeks (exactly 2 seasonal cycles) produced a
near-degenerate STL fit — not floating-point noise, but a genuinely tiny
IQR (~1e-5) because the seasonal smoother only has 2 points per phase
bin to fit and can nearly interpolate through most of a sparse series.
That's small enough to blow up severity (into the tens of thousands) but
not small enough to trip a `1e-6` epsilon. `stl_baseline.py`'s
`NOISE_FLOOR_SCALE` now applies an **unconditional floor** — `scale =
max(computed_scale, 1.0)` — rather than trying to detect "is this
noise" with an ever-smaller epsilon; 1.0 case is the smallest
meaningful unit of real variation for count data regardless of why the
computed scale came out tiny. See
`tests/test_detection.py::test_stl_severity_is_bounded_on_near_constant_sparse_series`.

## Remaining limitation: severity still isn't comparable across very different series

Even with that floor, a generic IQR/MAD-standardized threshold applied
uniformly across wildly heterogeneous series (a common disease with
hundreds of weekly cases vs. a rare one that's usually zero) produces
severity scores that aren't on a truly comparable scale. Ranking alerts
by severity across diseases will still over-weight sparse/rare series
somewhat. Worth revisiting once there's a dashboard consumer for these
alerts (Phase 4) — options include a minimum case-count floor on which
series get alerted on at all, or a variance-stabilizing transform suited
to count data (e.g. Anscombe/sqrt) before standardizing.

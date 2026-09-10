# Outbreak Sentinel

Early-warning **anomaly detection** system for CDC-notifiable disease
surveillance data. Detects when current case counts look abnormal *right
now* — a different problem from forecasting what they'll be next.

## Status

Phase 3 (AWS pipeline + Terraform) in progress.

- [x] Data source selected: CDC NNDSS Weekly Data (state-level, 139
      notifiable diseases, 2022–present) — see [data/README.md](data/README.md)
- [x] Ingestion script (`data/ingest_nndss.py`) pulls and cleans the full
      dataset from the CDC Socrata API
- [x] Backtest events identified: 2025 Texas measles outbreak (sharp
      point-source spike) and 2024 national pertussis resurgence (gradual
      surge) — see [data/README.md](data/README.md#identified-backtest-events-phase-1)
- [x] Detection models implemented and benchmarked head-to-head: STL
      seasonal-decomposition baseline vs. changepoint detection (`ruptures`)
      — changepoint ships as primary (91.9% recall / 3.4% FPR / 0-week
      detection latency on the held-out pertussis event vs. STL's 0%
      recall). Tuning is latency-aware, not just recall-aware, and the
      chosen threshold is a deliberately conservative pick off a
      documented latency-vs-false-positive-rate tradeoff. See
      [detection/README.md](detection/README.md)
- [x] Production detection driver (`detection/run_detection.py`) — scores
      the latest week across every (region, disease) series, separate
      from the historical backtest script. Parallelized and shardable:
      benchmarking showed scoring the full panel (~17.6k series) needs
      more than one Lambda invocation's worth of headroom under the
      900s timeout, so it's split across parallel invocations by a
      stable hash partition rather than run in one
- [x] AWS pipeline authored in Terraform: EventBridge (weekly cron) ->
      Step Functions (ingest -> process -> detect Lambdas, container
      images, detect fanned out via a Map state) -> S3 (raw + processed)
      -> DynamoDB alerts table -> CloudWatch alarms on failures.
      `terraform validate` passes; **not yet deployed** (deploying
      creates real, billable AWS resources — see
      [infra/README.md](infra/README.md) before running `apply`)
- [ ] API + dashboard — Phase 4
- [ ] CI/CD, monitoring, docs — Phase 5 (CI now also runs
      `terraform validate` on every push)

## Repo structure

```text
outbreak-sentinel/
├── data/          # ingestion scripts
├── detection/      # model + backtesting
├── api/            # FastAPI/Lambda handler
├── dashboard/      # Streamlit app
├── infra/          # Terraform
├── tests/
└── .github/workflows/
```

## Local setup

```bash
pip install -r requirements.txt
python data/ingest_nndss.py   # pulls raw data -> data/raw/
python data/eda.py            # builds tidy panel -> data/processed/
pytest tests/
```

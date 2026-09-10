# Outbreak Sentinel

Early-warning **anomaly detection** system for CDC-notifiable disease
surveillance data. Detects when current case counts look abnormal *right
now* — a different problem from forecasting what they'll be next.

## Status

Phase 1 (Data + EDA) in progress.

- [x] Data source selected: CDC NNDSS Weekly Data (state-level, 139
      notifiable diseases, 2022–present) — see [data/README.md](data/README.md)
- [x] Ingestion script (`data/ingest_nndss.py`) pulls and cleans the full
      dataset from the CDC Socrata API
- [x] Backtest events identified: 2025 Texas measles outbreak (sharp
      point-source spike) and 2024 national pertussis resurgence (gradual
      surge) — see [data/README.md](data/README.md#identified-backtest-events-phase-1)
- [ ] Detection models (STL-residual baseline, Bayesian changepoint) —
      Phase 2
- [ ] AWS pipeline + Terraform — Phase 3
- [ ] API + dashboard — Phase 4
- [ ] CI/CD, monitoring, docs — Phase 5

## Repo structure

```
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

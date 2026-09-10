"""Outbreak Sentinel API.

Serves current alerts and per-series history (with the STL anomaly
overlay) for the dashboard. Run locally:

    uvicorn api.main:app --reload

Deployed as a Lambda behind API Gateway via `api/lambda_handler.py`
(Mangum) — see infra/api.tf.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.data import get_alerts, get_series, list_regions_and_diseases

app = FastAPI(title="Outbreak Sentinel API", version="1.0")

# Public read-only demo API serving a dashboard that may run on a
# different origin (e.g. local Streamlit dev server, or App Runner) —
# there's no auth or write path here to protect.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/regions")
def regions() -> dict:
    return list_regions_and_diseases()


@app.get("/alerts")
def alerts(
    region: str | None = None,
    disease: str | None = None,
    min_severity: float = Query(0.0, ge=0.0),
) -> list[dict]:
    return get_alerts(region=region, disease=disease, min_severity=min_severity)


@app.get("/series")
def series(region: str, disease: str) -> dict:
    result = get_series(region=region, disease=disease)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for region={region!r}, disease={disease!r}")
    return result

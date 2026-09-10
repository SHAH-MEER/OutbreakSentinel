"""Outbreak Sentinel dashboard.

Run: streamlit run dashboard/app.py

Polls the API (api/main.py) for current alerts and per-series history —
never talks to DynamoDB/S3 directly, so it works the same whether the
API is running locally or deployed (set API_BASE_URL for the latter).
"""
from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from us_states import STATE_TO_CODE

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8010")
CODE_TO_STATE = {v: k for k, v in STATE_TO_CODE.items()}

st.set_page_config(page_title="Outbreak Sentinel", layout="wide")


@st.cache_data(ttl=60)
def fetch_alerts() -> list[dict]:
    resp = requests.get(f"{API_BASE_URL}/alerts", timeout=60)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=300)
def fetch_series(region: str, disease: str) -> dict | None:
    resp = requests.get(f"{API_BASE_URL}/series", params={"region": region, "disease": disease}, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


st.title("\U0001F9A0 Outbreak Sentinel")
st.caption(
    "Early-warning anomaly detection over CDC NNDSS weekly notifiable-disease data. "
    "Detects when *this week's* case counts look abnormal — not a forecast of what's next."
)

try:
    alerts = fetch_alerts()
except requests.RequestException as exc:
    st.error(f"Could not reach the API at {API_BASE_URL}: {exc}")
    st.stop()

if not alerts:
    st.info("No anomalies currently flagged.")
    st.stop()

alerts_df = pd.DataFrame(alerts)
alerts_df["state_code"] = alerts_df["region"].map(STATE_TO_CODE)

map_df = (
    alerts_df.dropna(subset=["state_code"])
    .groupby(["region", "state_code"], as_index=False)["severity"]
    .max()
)

col_map, col_detail = st.columns([3, 2])

clicked_region = None

with col_map:
    st.subheader("Flagged states, by peak severity this week")
    if map_df.empty:
        st.info("No state-level anomalies in the current sample (national/regional aggregates may still be flagged below).")
    else:
        fig_map = go.Figure(
            go.Choropleth(
                locations=map_df["state_code"],
                z=map_df["severity"],
                locationmode="USA-states",
                colorscale="OrRd",
                marker_line_color="white",
                marker_line_width=0.5,
                colorbar_title="Severity",
                text=map_df["region"],
                hovertemplate="%{text}<br>Peak severity: %{z:.1f}<extra></extra>",
            )
        )
        fig_map.update_layout(geo_scope="usa", margin=dict(l=0, r=0, t=10, b=0), height=450)
        map_event = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun", key="map")
        points = (map_event or {}).get("selection", {}).get("points", [])
        if points:
            clicked_region = CODE_TO_STATE.get(points[0].get("location"))

with col_detail:
    st.subheader("Inspect a flagged series")
    region_options = sorted(alerts_df["region"].unique())
    default_region_idx = region_options.index(clicked_region) if clicked_region in region_options else 0
    selected_region = st.selectbox("Region (click a state on the map, or pick one)", region_options, index=default_region_idx)

    disease_options = sorted(alerts_df.loc[alerts_df["region"] == selected_region, "disease"].unique())
    selected_disease = st.selectbox("Disease", disease_options)

    series = fetch_series(selected_region, selected_disease)
    if series is None:
        st.warning("No series data for this selection.")
    else:
        series_df = pd.DataFrame(
            {"week": series["weeks"], "cases": series["cases"], "anomaly": series["anomaly"]}
        )
        fig_series = go.Figure()
        fig_series.add_trace(
            go.Scatter(x=series_df["week"], y=series_df["cases"], mode="lines", name="Weekly cases", line=dict(color="#4C78A8"))
        )
        flagged = series_df[series_df["anomaly"]]
        fig_series.add_trace(
            go.Scatter(
                x=flagged["week"], y=flagged["cases"], mode="markers", name="Flagged anomaly",
                marker=dict(color="#E45756", size=9, symbol="circle"),
            )
        )
        fig_series.update_layout(
            margin=dict(l=0, r=0, t=10, b=0), height=350,
            xaxis=dict(tickangle=45, nticks=12), legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_series, use_container_width=True)

st.subheader("Alert feed")
feed_df = alerts_df[["region", "disease", "cases", "severity", "week_id", "detected_at"]].sort_values(
    "severity", ascending=False
)
feed_df.columns = ["Region", "Disease", "Cases", "Severity", "MMWR week", "Detected"]
feed_df["Severity"] = feed_df["Severity"].round(1)
st.dataframe(feed_df, use_container_width=True, hide_index=True)

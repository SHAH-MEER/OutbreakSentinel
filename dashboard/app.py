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


def _top_disease_for(region: str) -> str:
    subset = alerts_df.loc[alerts_df["region"] == region]
    return subset.loc[subset["severity"].idxmax(), "disease"]


# Selection lives in session_state, not a local variable, so it's the
# single source of truth for BOTH directions: a map click sets it (and
# reruns so the map's highlight updates immediately), and the dropdowns
# below are bound to the same keys, so picking a region/disease there
# updates it too — either one always drives the other, rather than the
# map only ever feeding the dropdowns one-way.
if "selected_region" not in st.session_state:
    top_alert = alerts_df.loc[alerts_df["severity"].idxmax()]
    st.session_state.selected_region = top_alert["region"]
    st.session_state.selected_disease = top_alert["disease"]

map_df = (
    alerts_df.dropna(subset=["state_code"])
    .sort_values("severity", ascending=False)
    .groupby(["region", "state_code"], as_index=False)
    .agg(severity=("severity", "max"), top_disease=("disease", "first"), disease_count=("disease", "count"))
)

col_map, col_detail = st.columns([3, 2])

with col_map:
    st.subheader("Flagged states, by peak severity this week")
    st.caption(
        "Color = the single worst-flagged disease per state (hover for what's driving it and how many "
        "others are flagged there too). Outlined state is the current selection — click another, or use "
        "the dropdowns, to change it."
    )
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
                # Map color is the WORST alert per state — a state with
                # several flagged diseases still shows one color, so the
                # tooltip spells out what's actually driving it and how
                # many other diseases are flagged there too.
                customdata=map_df[["top_disease", "disease_count"]],
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Peak severity: %{z:.1f} (%{customdata[0]})<br>"
                    "%{customdata[1]} disease(s) flagged this week"
                    "<extra></extra>"
                ),
                showlegend=False,
            )
        )
        selected_code = STATE_TO_CODE.get(st.session_state.selected_region)
        if selected_code:
            # A second, fully transparent choropleth trace containing
            # only the selected state, purely for its bold outline — a
            # single Choropleth trace can't style one location
            # differently from the rest.
            fig_map.add_trace(
                go.Choropleth(
                    locations=[selected_code],
                    z=[1],
                    locationmode="USA-states",
                    colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                    showscale=False,
                    marker_line_color="#1B1F3B",
                    marker_line_width=3.5,
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
        fig_map.update_layout(geo_scope="usa", margin=dict(l=0, r=0, t=10, b=0), height=450)
        map_event = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun", key="map")
        points = (map_event or {}).get("selection", {}).get("points", [])
        if points:
            clicked_region = CODE_TO_STATE.get(points[0].get("location"))
            if clicked_region and clicked_region != st.session_state.selected_region:
                st.session_state.selected_region = clicked_region
                st.session_state.selected_disease = _top_disease_for(clicked_region)
                st.rerun()  # redraw immediately so the outline moves with this same click

with col_detail:
    st.subheader("Inspect a flagged series")
    region_options = sorted(alerts_df["region"].unique())
    selected_region = st.selectbox("Region", region_options, key="selected_region")

    disease_options = sorted(alerts_df.loc[alerts_df["region"] == selected_region, "disease"].unique())
    if st.session_state.selected_disease not in disease_options:
        st.session_state.selected_disease = disease_options[0]
    selected_disease = st.selectbox("Disease", disease_options, key="selected_disease")

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

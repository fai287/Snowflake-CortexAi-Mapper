"""Ingestion health — real-time Snowpipe Streaming freshness per broker."""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))
from dashboard.utils import data  # noqa: E402

st.set_page_config(page_title="Ingestion Health", page_icon="📡", layout="wide")
st.title("📡 Ingestion Health")
st.caption("Freshness of the Kafka → Snowpipe Streaming → RAW pipeline, per broker and record type")

health = data.ingestion_health()

status_color = {"HEALTHY": "🟢", "LAGGING": "🟡", "STALE": "🔴"}
healthy = int((health["INGEST_STATUS"] == "HEALTHY").sum())
lagging = int((health["INGEST_STATUS"] == "LAGGING").sum())
stale = int((health["INGEST_STATUS"] == "STALE").sum())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total rows landed", f"{int(health['ROWS_LANDED'].sum()):,}")
c2.metric("🟢 Healthy streams", healthy)
c3.metric("🟡 Lagging streams", lagging)
c4.metric("🔴 Stale streams", stale)

st.divider()

left, right = st.columns([3, 2])
with left:
    st.subheader("Seconds since last message")
    fig = px.bar(
        health.sort_values("SECONDS_SINCE_LAST", ascending=False),
        x="SECONDS_SINCE_LAST", y="BROKER_CODE", color="INGEST_STATUS",
        facet_col="RECORD_TYPE", orientation="h",
        color_discrete_map={"HEALTHY": "#2ecc71", "LAGGING": "#f1c40f", "STALE": "#e74c3c"},
        labels={"SECONDS_SINCE_LAST": "Seconds since last", "BROKER_CODE": "Broker"},
    )
    fig.update_layout(height=420, legend_title="Status")
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Rows landed by broker")
    fig2 = px.bar(health.groupby("BROKER_CODE")["ROWS_LANDED"].sum().reset_index(),
                  x="BROKER_CODE", y="ROWS_LANDED", color="ROWS_LANDED",
                  color_continuous_scale="Tealgrn")
    fig2.update_layout(height=420, coloraxis_showscale=False)
    st.plotly_chart(fig2, use_container_width=True)

st.subheader("Stream status detail")
show = health.copy()
show["INGEST_STATUS"] = show["INGEST_STATUS"].map(lambda s: f"{status_color.get(s,'')} {s}")
st.dataframe(show, use_container_width=True, hide_index=True)

if stale:
    st.warning(f"{stale} stream(s) are STALE (>10 min without data). "
               "Check the producer (`make simulate`) and the ingest job (`make ingest`).")

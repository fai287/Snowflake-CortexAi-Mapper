"""AI-Powered Insurance Data Platform — Streamlit dashboard (home).

Real-time executive overview: policy volume, claim volume, premium revenue,
validation errors, plus headline broker and product breakdowns. Detail pages
live in streamlit/pages/.

Run:  streamlit run streamlit/app.py
Demo: DEMO_MODE=1 streamlit run streamlit/app.py   (synthetic data, no Snowflake)
"""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard.utils import data  # noqa: E402

st.set_page_config(page_title="Insurance Data Platform", page_icon="🛡️", layout="wide")


def _money(x: float) -> str:
    return f"${x:,.0f}"


st.title("🛡️ AI-Powered Insurance Data Platform")
st.caption("Real-time policy & claims analytics · Kafka → Snowpipe Streaming → Snowflake → Cortex")

if data.is_demo():
    st.info("Running in **demo mode** with synthetic data. "
            "Set Snowflake credentials in `.env` (and unset `DEMO_MODE`) to use live data.",
            icon="🧪")

policies = data.policies()
claims = data.claims()
brokers = data.broker_performance()
vsum = data.validation_summary()

# ── Headline KPIs ─────────────────────────────────────────────────────────
total_premium = float(policies["PREMIUM_AMOUNT"].sum())
total_claims = float(claims["CLAIM_AMOUNT"].sum())
loss_ratio = (total_claims / total_premium) if total_premium else 0.0
val_errors = int(vsum.loc[vsum["SEVERITY"] == "ERROR", "FAILURE_COUNT"].sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Policy Volume", f"{len(policies):,}")
c2.metric("Claim Volume", f"{len(claims):,}")
c3.metric("Premium Revenue", _money(total_premium))
c4.metric("Portfolio Loss Ratio", f"{loss_ratio:.1%}")
c5.metric("Validation Errors", f"{val_errors:,}",
          delta=f"{int(vsum.loc[vsum.SEVERITY=='WARN','FAILURE_COUNT'].sum())} warnings",
          delta_color="off")

st.divider()

# ── Premium by product line + claims by status ───────────────────────────
left, right = st.columns(2)
with left:
    st.subheader("Premium revenue by product line")
    by_line = (policies.groupby("PRODUCT_LINE")["PREMIUM_AMOUNT"].sum()
               .sort_values(ascending=False).reset_index())
    fig = px.bar(by_line, x="PRODUCT_LINE", y="PREMIUM_AMOUNT",
                 labels={"PREMIUM_AMOUNT": "Premium ($)", "PRODUCT_LINE": "Product line"},
                 color="PREMIUM_AMOUNT", color_continuous_scale="Blues")
    fig.update_layout(showlegend=False, height=360, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Claims by status")
    by_status = claims.groupby("CLAIM_STATUS")["CLAIM_AMOUNT"].agg(["count", "sum"]).reset_index()
    fig2 = px.pie(by_status, names="CLAIM_STATUS", values="count", hole=0.45)
    fig2.update_layout(height=360)
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Broker leaderboard ────────────────────────────────────────────────────
st.subheader("Broker performance")
bshow = brokers.sort_values("TOTAL_PREMIUM", ascending=False).copy()
bshow["TOTAL_PREMIUM"] = bshow["TOTAL_PREMIUM"].map(_money)
bshow["TOTAL_CLAIMS_AMOUNT"] = bshow["TOTAL_CLAIMS_AMOUNT"].map(_money)
bshow["LOSS_RATIO"] = (bshow["LOSS_RATIO"] * 100).round(1).astype(str) + "%"
st.dataframe(
    bshow[["BROKER_NAME", "POLICY_COUNT", "TOTAL_PREMIUM", "CLAIM_COUNT", "TOTAL_CLAIMS_AMOUNT", "LOSS_RATIO"]],
    use_container_width=True, hide_index=True,
)

st.caption("Use the pages in the sidebar for Ingestion Health, Broker drill-down, "
           "Data Quality, and the conversational AI Assistant.")

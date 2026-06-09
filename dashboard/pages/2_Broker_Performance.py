"""Broker performance — premium, claims, loss ratio drill-down."""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))
from dashboard.utils import data  # noqa: E402

st.set_page_config(page_title="Broker Performance", page_icon="🏢", layout="wide")
st.title("🏢 Broker Performance")
st.caption("Premium volume, claim volume and loss ratio by broker")

brokers = data.broker_performance()
policies = data.policies()
claims = data.claims()

broker_names = ["All brokers"] + sorted(brokers["BROKER_NAME"].unique().tolist())
selected = st.selectbox("Broker", broker_names)

if selected != "All brokers":
    policies = policies[policies["BROKER_NAME"] == selected]
    claims = claims[claims["BROKER_NAME"] == selected]
    brokers = brokers[brokers["BROKER_NAME"] == selected]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Policies", f"{int(brokers['POLICY_COUNT'].sum()):,}")
c2.metric("Premium", f"${brokers['TOTAL_PREMIUM'].sum():,.0f}")
c3.metric("Claims", f"{int(brokers['CLAIM_COUNT'].sum()):,}")
lr = brokers["TOTAL_CLAIMS_AMOUNT"].sum() / max(brokers["TOTAL_PREMIUM"].sum(), 1)
c4.metric("Loss ratio", f"{lr:.1%}")

st.divider()

left, right = st.columns(2)
with left:
    st.subheader("Premium vs claims by broker")
    melt = brokers.melt(id_vars="BROKER_NAME",
                        value_vars=["TOTAL_PREMIUM", "TOTAL_CLAIMS_AMOUNT"],
                        var_name="Measure", value_name="Amount")
    fig = px.bar(melt, x="BROKER_NAME", y="Amount", color="Measure", barmode="group")
    fig.update_layout(height=380)
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Loss ratio by broker")
    fig2 = px.bar(brokers.sort_values("LOSS_RATIO", ascending=False),
                  x="BROKER_NAME", y="LOSS_RATIO", color="LOSS_RATIO",
                  color_continuous_scale="RdYlGn_r")
    fig2.update_layout(height=380, coloraxis_showscale=False, yaxis_tickformat=".0%")
    st.plotly_chart(fig2, use_container_width=True)

st.subheader("Product mix")
mix = policies.groupby(["BROKER_NAME", "PRODUCT_LINE"])["PREMIUM_AMOUNT"].sum().reset_index()
fig3 = px.bar(mix, x="BROKER_NAME", y="PREMIUM_AMOUNT", color="PRODUCT_LINE", barmode="stack")
fig3.update_layout(height=400)
st.plotly_chart(fig3, use_container_width=True)

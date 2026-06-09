"""Offline demo agent for the hosted dashboard.

When no live Snowflake/Cortex connection is available (e.g. Streamlit Community
Cloud), the real NL→SQL agent (chatbot/agent.py) can't run. This lightweight
stand-in answers common questions by running pandas over the sample dataset and
shows an equivalent SQL string, so the AI Assistant page is still interactive.

It is intentionally simple keyword routing — NOT the production agent. The
production agent (Cortex NL→SQL + guardrails) is used automatically whenever a
live connection is configured.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from dashboard.utils import data


@dataclass
class DemoAnswer:
    answer: str
    sql: str = ""
    table: pd.DataFrame = field(default_factory=pd.DataFrame)


def answer(question: str) -> DemoAnswer:
    q = question.lower()
    pol = data.policies()
    clm = data.claims()
    bp = data.broker_performance()
    ing = data.ingestion_health()
    val = data.validation_summary()

    # premium revenue by product line
    if "premium" in q and ("product" in q or "line" in q or "by product" in q):
        t = (pol.groupby("PRODUCT_LINE")["PREMIUM_AMOUNT"].sum()
             .sort_values(ascending=False).reset_index())
        top = t.iloc[0]
        return DemoAnswer(
            f"Total premium revenue is **${t['PREMIUM_AMOUNT'].sum():,.0f}** across "
            f"{len(t)} product lines. The largest is **{top['PRODUCT_LINE']}** at "
            f"${top['PREMIUM_AMOUNT']:,.0f}.",
            "SELECT product_line, SUM(premium_amount) AS total_premium\nFROM SEMANTIC.POLICIES\nGROUP BY product_line\nORDER BY total_premium DESC;",
            t)

    # loss ratio by broker
    if "loss ratio" in q or ("broker" in q and "ratio" in q):
        t = bp.sort_values("LOSS_RATIO", ascending=False)[["BROKER_NAME", "LOSS_RATIO"]]
        worst = t.iloc[0]
        return DemoAnswer(
            f"**{worst['BROKER_NAME']}** has the highest loss ratio at "
            f"**{worst['LOSS_RATIO']:.1%}**.",
            "SELECT broker_name, loss_ratio\nFROM SEMANTIC.BROKER_PERFORMANCE\nORDER BY loss_ratio DESC;",
            t)

    # open claims
    if "open" in q and "claim" in q:
        n = int((clm["CLAIM_STATUS"] == "OPEN").sum())
        return DemoAnswer(
            f"There are **{n}** claims currently in OPEN status.",
            "SELECT COUNT(*) AS open_claims\nFROM SEMANTIC.CLAIMS\nWHERE claim_status = 'OPEN';",
            clm.loc[clm["CLAIM_STATUS"] == "OPEN"].head(20))

    # stale ingestion
    if "stale" in q or ("ingestion" in q and ("health" in q or "stale" in q)):
        t = ing[ing["INGEST_STATUS"] != "HEALTHY"][["BROKER_CODE", "RECORD_TYPE", "SECONDS_SINCE_LAST", "INGEST_STATUS"]]
        msg = ("All streams are healthy." if t.empty
               else f"**{len(t)}** stream(s) are lagging or stale.")
        return DemoAnswer(
            msg,
            "SELECT broker_code, record_type, seconds_since_last, ingest_status\nFROM SEMANTIC.INGESTION_HEALTH\nWHERE ingest_status <> 'HEALTHY';",
            t)

    # validation errors
    if "validation" in q or "error" in q or "data quality" in q:
        t = val.sort_values("FAILURE_COUNT", ascending=False)
        top = t.iloc[0]
        return DemoAnswer(
            f"The most common validation issue is **\"{top['RULE_DESCRIPTION']}\"** "
            f"({top['SEVERITY']}) with {int(top['FAILURE_COUNT'])} failures. "
            f"Total failures across all rules: {int(t['FAILURE_COUNT'].sum())}.",
            "SELECT rule_description, severity, failure_count\nFROM SEMANTIC.VALIDATION_SUMMARY\nORDER BY failure_count DESC;",
            t)

    # largest policies
    if "largest" in q or ("top" in q and ("polic" in q or "premium" in q)):
        m = re.search(r"\b(\d+)\b", q)
        k = int(m.group(1)) if m else 5
        t = pol.sort_values("PREMIUM_AMOUNT", ascending=False).head(k)[
            ["POLICY_NUMBER", "BROKER_NAME", "PRODUCT_LINE", "PREMIUM_AMOUNT"]]
        return DemoAnswer(
            f"The top {k} policies by premium range from "
            f"${t['PREMIUM_AMOUNT'].max():,.0f} down to ${t['PREMIUM_AMOUNT'].min():,.0f}.",
            f"SELECT policy_number, broker_name, product_line, premium_amount\nFROM SEMANTIC.POLICIES\nORDER BY premium_amount DESC\nLIMIT {k};",
            t)

    # claim volume / policy volume
    if "how many" in q and "polic" in q:
        return DemoAnswer(f"There are **{len(pol):,}** policies in the portfolio.",
                          "SELECT COUNT(*) FROM SEMANTIC.POLICIES;", pd.DataFrame())
    if "how many" in q and "claim" in q:
        return DemoAnswer(f"There are **{len(clm):,}** claims in total.",
                          "SELECT COUNT(*) FROM SEMANTIC.CLAIMS;", pd.DataFrame())

    return DemoAnswer(
        "I can answer questions about premium revenue, loss ratios, open claims, "
        "ingestion health, validation errors, and the largest policies. Try one of "
        "the examples in the sidebar. (This offline demo uses keyword routing; the "
        "full Cortex NL→SQL agent runs when a live Snowflake connection is set.)")

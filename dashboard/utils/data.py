"""Dashboard data-access layer.

Resolution order for every dataset:
  1. Live Snowflake SEMANTIC view  (when credentials are configured and reachable)
  2. data/sample/*.csv             (the generated dummy dataset — used on
                                     Streamlit Community Cloud / offline demos)
  3. Randomly generated frame      (last-resort fallback)

The Snowflake client is imported lazily so the dashboard runs on a minimal
dependency set (streamlit + plotly + pandas + numpy) with no Snowflake/Kafka
packages installed — which is what makes the hosted deployment cheap and fast.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = ROOT / "data" / "sample"
sys.path.append(str(ROOT))

DEMO = os.getenv("DEMO_MODE", "0") == "1"
_BROKERS = ["Alpha Insurance Brokers", "Beta Risk Partners", "Gamma Underwriting Co."]
_CODES = ["BRK_ALPHA", "BRK_BETA", "BRK_GAMMA"]
_LINES = ["AUTO", "HOME", "LIFE", "HEALTH", "TRAVEL", "COMMERCIAL", "MARINE"]


def _has_snowflake_creds() -> bool:
    return bool(os.getenv("SNOWFLAKE_ACCOUNT")) and (
        bool(os.getenv("SNOWFLAKE_PASSWORD")) or bool(os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH"))
    )


def _csv(name: str) -> pd.DataFrame | None:
    path = SAMPLE_DIR / f"{name}.csv"
    if path.exists():
        return pd.read_csv(path)
    return None


def _resolve(view: str, csv_name: str, demo_builder) -> pd.DataFrame:
    """Live view → sample CSV → random builder."""
    if not DEMO and _has_snowflake_creds():
        try:
            from src.common.snowflake_client import run_query  # lazy import
            return run_query(f"SELECT * FROM {view}")
        except Exception as exc:
            st.session_state["_db_error"] = str(exc)
    csv = _csv(csv_name)
    if csv is not None:
        return csv
    return demo_builder()


@st.cache_data(ttl=15)
def policies() -> pd.DataFrame:
    def demo():
        rng = np.random.default_rng(7)
        n = 600
        return pd.DataFrame({
            "POLICY_NUMBER": [f"POL-{100000+i}" for i in range(n)],
            "BROKER_NAME": rng.choice(_BROKERS, n),
            "BROKER_CODE": rng.choice(_CODES, n),
            "CUSTOMER_NAME": rng.choice(["Acme Corp", "J. Smith", "Globex", "M. Brown"], n),
            "PRODUCT_LINE": rng.choice(_LINES, n),
            "PREMIUM_AMOUNT": rng.gamma(2.0, 700, n).round(2),
            "SUM_INSURED": rng.gamma(2.0, 30000, n).round(2),
            "IS_ACTIVE": rng.choice([True, False], n, p=[0.8, 0.2]),
            "ANOMALY_SCORE": rng.beta(1.2, 12, n).round(3),
        })
    return _resolve("SEMANTIC.POLICIES", "policies", demo)


@st.cache_data(ttl=15)
def claims() -> pd.DataFrame:
    def demo():
        rng = np.random.default_rng(11)
        n = 280
        return pd.DataFrame({
            "CLAIM_NUMBER": [f"CLM-{500000+i}" for i in range(n)],
            "CLAIM_STATUS": rng.choice(["OPEN", "IN_REVIEW", "APPROVED", "PAID", "DENIED"], n),
            "BROKER_NAME": rng.choice(_BROKERS, n),
            "PRODUCT_LINE": rng.choice(_LINES, n),
            "CLAIM_AMOUNT": rng.gamma(2.0, 4000, n).round(2),
            "REPORTING_LAG_DAYS": rng.integers(0, 60, n),
            "SENTIMENT_SCORE": rng.uniform(-1, 0.5, n).round(3),
            "ANOMALY_SCORE": rng.beta(1.2, 10, n).round(3),
        })
    return _resolve("SEMANTIC.CLAIMS", "claims", demo)


@st.cache_data(ttl=15)
def broker_performance() -> pd.DataFrame:
    def demo():
        p, c = policies(), claims()
        prem = p.groupby("BROKER_NAME")["PREMIUM_AMOUNT"].agg(["count", "sum"])
        clm = c.groupby("BROKER_NAME")["CLAIM_AMOUNT"].agg(["count", "sum"])
        out = prem.join(clm, lsuffix="_pol", rsuffix="_clm").fillna(0).reset_index()
        out.columns = ["BROKER_NAME", "POLICY_COUNT", "TOTAL_PREMIUM", "CLAIM_COUNT", "TOTAL_CLAIMS_AMOUNT"]
        out["LOSS_RATIO"] = (out["TOTAL_CLAIMS_AMOUNT"] / out["TOTAL_PREMIUM"]).round(3)
        out["BROKER_CODE"] = out["BROKER_NAME"].map(dict(zip(_BROKERS, _CODES)))
        return out
    return _resolve("SEMANTIC.BROKER_PERFORMANCE", "broker_performance", demo)


@st.cache_data(ttl=10)
def ingestion_health() -> pd.DataFrame:
    def demo():
        rng = np.random.default_rng(3)
        rows = []
        for code in _CODES:
            for rt in ["policy", "claim"]:
                secs = int(rng.choice([5, 20, 90, 300, 800], p=[0.4, 0.3, 0.15, 0.1, 0.05]))
                status = "HEALTHY" if secs <= 120 else "LAGGING" if secs <= 600 else "STALE"
                rows.append([code, rt, int(rng.integers(200, 4000)), secs, status])
        return pd.DataFrame(rows, columns=[
            "BROKER_CODE", "RECORD_TYPE", "ROWS_LANDED", "SECONDS_SINCE_LAST", "INGEST_STATUS"])
    return _resolve("SEMANTIC.INGESTION_HEALTH", "ingestion_health", demo)


@st.cache_data(ttl=15)
def validation_summary() -> pd.DataFrame:
    def demo():
        data = [
            ("policy", "POL_002", "Premium must be a positive number", "ERROR", 14),
            ("policy", "POL_004", "Effective date must be <= expiry date", "ERROR", 9),
            ("policy", "POL_006", "Customer name present (KYC)", "ERROR", 6),
            ("policy", "POL_003", "Premium within plausible range", "WARN", 21),
            ("claim", "CLM_004", "Loss date cannot be in the future", "ERROR", 8),
            ("claim", "CLM_005", "Reported date >= loss date", "ERROR", 5),
            ("claim", "CLM_006", "Reporting lag <= 365 days", "WARN", 17),
        ]
        return pd.DataFrame(data, columns=[
            "ENTITY", "RULE_ID", "RULE_DESCRIPTION", "SEVERITY", "FAILURE_COUNT"])
    return _resolve("SEMANTIC.VALIDATION_SUMMARY", "validation_summary", demo)


def using_live_snowflake() -> bool:
    return (not DEMO) and _has_snowflake_creds() and "_db_error" not in st.session_state


def is_demo() -> bool:
    return not using_live_snowflake()

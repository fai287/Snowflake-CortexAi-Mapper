"""Generate a deterministic dummy dataset for testing and the hosted dashboard.

Writes CSVs to data/sample/ that mirror the SEMANTIC views:
  policies.csv, claims.csv, broker_performance.csv,
  ingestion_health.csv, validation_summary.csv

The Streamlit dashboard loads these automatically when a live Snowflake
connection isn't configured (e.g. on Streamlit Community Cloud), so the deployed
app is fully populated with consistent data — no warehouse required.

    python scripts/generate_sample_data.py            # default 800 policies
    python scripts/generate_sample_data.py --policies 2000 --seed 42
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "sample"

BROKERS = [
    ("BRK_ALPHA", "Alpha Insurance Brokers", "csv"),
    ("BRK_BETA", "Beta Risk Partners", "json"),
    ("BRK_GAMMA", "Gamma Underwriting Co.", "csv"),
]
LINES = ["AUTO", "HOME", "LIFE", "HEALTH", "TRAVEL", "COMMERCIAL", "MARINE"]
LINE_BASE = {"AUTO": 800, "HOME": 600, "LIFE": 1200, "HEALTH": 2000,
             "TRAVEL": 120, "COMMERCIAL": 5000, "MARINE": 8000}
SEGMENTS = ["RETAIL", "SME", "CORPORATE"]
TIERS = ["LOW", "MEDIUM", "HIGH", "SEVERE"]
STATUSES = ["OPEN", "IN_REVIEW", "APPROVED", "PAID", "DENIED", "CLOSED"]
CUSTOMERS = ["Acme Corp", "Globex", "Initech", "Umbrella Ltd", "Wayne Enterprises",
             "Stark Industries", "J. Smith", "M. Brown", "A. Patel", "L. Nguyen",
             "R. Okoro", "S. Haddad", "T. Müller", "K. Sato", "P. Ivanov"]
NARRATIVES = [
    "Vehicle rear-ended at traffic lights, moderate bumper damage.",
    "Water ingress from burst pipe damaged ground-floor flooring.",
    "Theft of insured contents following forced entry overnight.",
    "Windscreen cracked by road debris on the motorway.",
    "Storm damage to roof tiles after severe weather warning.",
    "Slip and fall on business premises, minor injury claim.",
    "Total loss after garage fire; vehicle beyond economic repair.",
]


def generate(n_policies: int, seed: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)

    # ── Policies ─────────────────────────────────────────────────────────
    codes = [b[0] for b in BROKERS]
    names = {b[0]: b[1] for b in BROKERS}
    lines = rng.choice(LINES, n_policies)
    bcodes = rng.choice(codes, n_policies, p=[0.45, 0.30, 0.25])
    base = np.array([LINE_BASE[l] for l in lines])
    premium = (base * rng.uniform(0.6, 1.7, n_policies)).round(2)
    # inject ~3% premium anomalies
    anom_idx = rng.choice(n_policies, size=max(1, n_policies // 33), replace=False)
    premium[anom_idx] = (premium[anom_idx] * rng.uniform(15, 40, len(anom_idx))).round(2)
    anomaly_score = rng.beta(1.2, 14, n_policies).round(3)
    anomaly_score[anom_idx] = rng.uniform(0.95, 1.0, len(anom_idx)).round(3)

    eff = [date(2025, 1, 1) + timedelta(days=int(d)) for d in rng.integers(0, 330, n_policies)]
    customers = rng.choice(CUSTOMERS, n_policies)
    policies = pd.DataFrame({
        "POLICY_NUMBER": [f"POL-{100000 + i}" for i in range(n_policies)],
        "BROKER_NAME": [names[c] for c in bcodes],
        "BROKER_CODE": bcodes,
        "CUSTOMER_NAME": customers,
        "CUSTOMER_SEGMENT": rng.choice(SEGMENTS, n_policies, p=[0.55, 0.30, 0.15]),
        "RISK_TIER": rng.choice(TIERS, n_policies, p=[0.4, 0.35, 0.2, 0.05]),
        "PRODUCT_LINE": lines,
        "PREMIUM_AMOUNT": premium,
        "SUM_INSURED": (premium * rng.uniform(20, 60, n_policies)).round(2),
        "EFFECTIVE_DATE": [d.isoformat() for d in eff],
        "EXPIRY_DATE": [(d + timedelta(days=365)).isoformat() for d in eff],
        "POLICY_TERM_DAYS": 365,
        "IS_ACTIVE": rng.choice([True, False], n_policies, p=[0.82, 0.18]),
        "ANOMALY_SCORE": anomaly_score,
        "ANOMALY_REASON": [
            "Premium materially exceeds the broker/product peer average." if s >= 0.95 else ""
            for s in anomaly_score
        ],
    })

    # ── Claims (≈40% of policies have a claim) ──────────────────────────
    n_claims = int(n_policies * 0.4)
    claim_pol = policies.sample(n_claims, random_state=seed).reset_index(drop=True)
    loss = [date.fromisoformat(d) + timedelta(days=int(x))
            for d, x in zip(claim_pol["EFFECTIVE_DATE"], rng.integers(5, 320, n_claims))]
    lag = rng.integers(0, 45, n_claims)
    camount = (claim_pol["PREMIUM_AMOUNT"].values * rng.uniform(0.5, 8.0, n_claims)).round(2)
    clm_anom = rng.beta(1.2, 12, n_claims).round(3)
    claims = pd.DataFrame({
        "CLAIM_NUMBER": [f"CLM-{500000 + i}" for i in range(n_claims)],
        "CLAIM_STATUS": rng.choice(STATUSES, n_claims, p=[0.25, 0.2, 0.15, 0.2, 0.1, 0.1]),
        "POLICY_NUMBER": claim_pol["POLICY_NUMBER"].values,
        "BROKER_NAME": claim_pol["BROKER_NAME"].values,
        "BROKER_CODE": claim_pol["BROKER_CODE"].values,
        "CUSTOMER_NAME": claim_pol["CUSTOMER_NAME"].values,
        "PRODUCT_LINE": claim_pol["PRODUCT_LINE"].values,
        "LOSS_DATE": [d.isoformat() for d in loss],
        "REPORTED_DATE": [(d + timedelta(days=int(x))).isoformat() for d, x in zip(loss, lag)],
        "REPORTING_LAG_DAYS": lag,
        "CLAIM_AMOUNT": camount,
        "SENTIMENT_SCORE": rng.uniform(-0.9, 0.4, n_claims).round(3),
        "ANOMALY_SCORE": clm_anom,
        "ANOMALY_REASON": ["" for _ in range(n_claims)],
        "LOSS_DESCRIPTION": rng.choice(NARRATIVES, n_claims),
    })

    # ── Broker performance (derived) ────────────────────────────────────
    prem = policies.groupby(["BROKER_CODE", "BROKER_NAME"]).agg(
        POLICY_COUNT=("POLICY_NUMBER", "count"),
        TOTAL_PREMIUM=("PREMIUM_AMOUNT", "sum"),
        AVG_POLICY_ANOMALY=("ANOMALY_SCORE", "mean"),
    ).reset_index()
    clm = claims.groupby("BROKER_CODE").agg(
        CLAIM_COUNT=("CLAIM_NUMBER", "count"),
        TOTAL_CLAIMS_AMOUNT=("CLAIM_AMOUNT", "sum"),
    ).reset_index()
    bp = prem.merge(clm, on="BROKER_CODE", how="left").fillna(0)
    bp["LOSS_RATIO"] = (bp["TOTAL_CLAIMS_AMOUNT"] / bp["TOTAL_PREMIUM"]).round(4)
    bp = bp[["BROKER_CODE", "BROKER_NAME", "POLICY_COUNT", "TOTAL_PREMIUM",
             "CLAIM_COUNT", "TOTAL_CLAIMS_AMOUNT", "LOSS_RATIO", "AVG_POLICY_ANOMALY"]]

    # ── Ingestion health ────────────────────────────────────────────────
    rows = []
    for code, name, _ in BROKERS:
        for rt in ["policy", "claim"]:
            secs = int(rng.choice([6, 18, 75, 240, 700], p=[0.45, 0.3, 0.13, 0.08, 0.04]))
            status = "HEALTHY" if secs <= 120 else "LAGGING" if secs <= 600 else "STALE"
            landed = int((bp.loc[bp.BROKER_CODE == code, "POLICY_COUNT"].iat[0]) *
                         (1.0 if rt == "policy" else 0.4))
            rows.append([code, rt, landed, secs, status])
    ingestion = pd.DataFrame(rows, columns=[
        "BROKER_CODE", "RECORD_TYPE", "ROWS_LANDED", "SECONDS_SINCE_LAST", "INGEST_STATUS"])

    # ── Validation summary ──────────────────────────────────────────────
    validation = pd.DataFrame([
        ("policy", "POL_002", "Premium must be a positive number", "ERROR", int(rng.integers(8, 20))),
        ("policy", "POL_004", "Effective date must be <= expiry date", "ERROR", int(rng.integers(4, 12))),
        ("policy", "POL_006", "Customer name present (KYC)", "ERROR", int(rng.integers(3, 9))),
        ("policy", "POL_003", "Premium within plausible range", "WARN", int(rng.integers(15, 30))),
        ("policy", "POL_008", "Product line resolved to known class", "WARN", int(rng.integers(2, 8))),
        ("claim", "CLM_004", "Loss date cannot be in the future", "ERROR", int(rng.integers(5, 12))),
        ("claim", "CLM_005", "Reported date >= loss date", "ERROR", int(rng.integers(3, 9))),
        ("claim", "CLM_002", "Claim must reference a policy", "ERROR", int(rng.integers(2, 7))),
        ("claim", "CLM_006", "Reporting lag <= 365 days", "WARN", int(rng.integers(10, 22))),
    ], columns=["ENTITY", "RULE_ID", "RULE_DESCRIPTION", "SEVERITY", "FAILURE_COUNT"])

    return {
        "policies": policies,
        "claims": claims,
        "broker_performance": bp,
        "ingestion_health": ingestion,
        "validation_summary": validation,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies", type=int, default=800)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    frames = generate(args.policies, args.seed)
    for name, df in frames.items():
        path = OUT / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"wrote {path.relative_to(OUT.parents[1])}  ({len(df)} rows)")
    print("\nDone. The dashboard will load these automatically when no live "
          "Snowflake connection is configured.")


if __name__ == "__main__":
    main()

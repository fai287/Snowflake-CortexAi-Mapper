"""Synthetic broker data generator.

Produces policy and claim records in each broker's NATIVE format/headers
(see config/broker_mappings.yaml). This is what makes the Cortex header-mapping
and semantic-standardization story real: every broker looks different on the
wire, and the platform has to reconcile them.

Records are intentionally seeded with a small fraction of data-quality defects
(negative premiums, future loss dates, missing keys, anomalous amounts) so the
validation framework and anomaly detection have something to catch.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

FIRST = ["James", "Mary", "Robert", "Patricia", "Acme", "Globex", "Initech", "Umbrella", "Wayne", "Stark"]
LAST = ["Smith", "Johnson", "Industries", "Corp", "Holdings", "Williams", "Brown", "Group", "Ltd", "LLC"]

# product text varies by broker to exercise CLASSIFY_TEXT
PRODUCT_TEXT = {
    "AUTO": ["Motor Vehicle", "Auto Comprehensive", "Car Insurance", "Private Motor"],
    "HOME": ["Homeowners", "Buildings & Contents", "Household", "Property Owners"],
    "LIFE": ["Term Life", "Whole of Life", "Life Assurance", "Life Cover"],
    "HEALTH": ["Private Medical", "Health Plan", "Medical Expenses", "PMI"],
    "TRAVEL": ["Travel Insurance", "Trip Cover", "Worldwide Travel"],
    "COMMERCIAL": ["Commercial Combined", "Business Pack", "SME Liability"],
    "MARINE": ["Marine Cargo", "Hull & Machinery", "Goods in Transit"],
}
STATUSES = ["OPEN", "IN_REVIEW", "APPROVED", "PAID", "DENIED", "CLOSED"]
LOSS_NARRATIVES = [
    "Vehicle rear-ended at traffic lights, moderate bumper damage.",
    "Water ingress from burst pipe damaged ground-floor flooring.",
    "Theft of insured contents following forced entry overnight.",
    "Windscreen cracked by road debris on the motorway.",
    "Storm damage to roof tiles after severe weather warning.",
    "Slip and fall on business premises, minor injury claim.",
]


def _name() -> str:
    return f"{random.choice(FIRST)} {random.choice(LAST)}"


def _rand_date(start_days_ago: int, span: int) -> date:
    return date.today() - timedelta(days=random.randint(start_days_ago, start_days_ago + span))


def _premium(product_line: str, inject_anomaly: bool) -> float:
    base = {"AUTO": 800, "HOME": 600, "LIFE": 1200, "HEALTH": 2000,
            "TRAVEL": 120, "COMMERCIAL": 5000, "MARINE": 8000}[product_line]
    val = round(base * random.uniform(0.6, 1.6), 2)
    if inject_anomaly:
        val = round(val * random.uniform(15, 40), 2)  # wild outlier
    return val


def generate_policy(seq: int, defect_rate: float = 0.08, anomaly_rate: float = 0.03) -> dict:
    """Return a canonical-ish policy dict (pre-broker-formatting)."""
    product_line = random.choice(list(PRODUCT_TEXT))
    eff = _rand_date(0, 365)
    exp = eff + timedelta(days=365)
    inject_defect = random.random() < defect_rate
    rec = {
        "policy_number": f"POL-{100000 + seq}",
        "customer_name": _name(),
        "product_name": random.choice(PRODUCT_TEXT[product_line]),
        "premium_amount": _premium(product_line, random.random() < anomaly_rate),
        "sum_insured": round(_premium(product_line, False) * random.uniform(20, 60), 2),
        "effective_date": eff.isoformat(),
        "expiry_date": exp.isoformat(),
        "broker_agent": f"AG{random.randint(100, 999)}",
        "_product_line": product_line,  # ground-truth, dropped before send
    }
    if inject_defect:
        _inject_policy_defect(rec)
    return rec


def _inject_policy_defect(rec: dict) -> None:
    defect = random.choice(["neg_premium", "no_number", "bad_dates", "no_name"])
    if defect == "neg_premium":
        rec["premium_amount"] = -abs(rec["premium_amount"])
    elif defect == "no_number":
        rec["policy_number"] = ""
    elif defect == "bad_dates":  # expiry before effective
        rec["effective_date"], rec["expiry_date"] = rec["expiry_date"], rec["effective_date"]
    elif defect == "no_name":
        rec["customer_name"] = ""


def generate_claim(seq: int, policy_number: str, defect_rate: float = 0.10) -> dict:
    loss = _rand_date(0, 200)
    reported = loss + timedelta(days=random.randint(0, 30))
    inject_defect = random.random() < defect_rate
    rec = {
        "claim_number": f"CLM-{500000 + seq}",
        "policy_number": policy_number,
        "loss_date": loss.isoformat(),
        "reported_date": reported.isoformat(),
        "claim_amount": round(random.uniform(200, 25000), 2),
        "claim_status": random.choice(STATUSES),
        "loss_description": random.choice(LOSS_NARRATIVES),
    }
    if inject_defect:
        _inject_claim_defect(rec)
    return rec


def _inject_claim_defect(rec: dict) -> None:
    defect = random.choice(["future_loss", "reported_before_loss", "neg_amount", "no_policy"])
    if defect == "future_loss":
        rec["loss_date"] = (date.today() + timedelta(days=10)).isoformat()
    elif defect == "reported_before_loss":
        rec["reported_date"] = (date.fromisoformat(rec["loss_date"]) - timedelta(days=5)).isoformat()
    elif defect == "neg_amount":
        rec["claim_amount"] = -abs(rec["claim_amount"])
    elif defect == "no_policy":
        rec["policy_number"] = ""


# ── Re-shape a canonical record into a specific broker's native headers ───
def to_broker_format(canonical: dict, broker_code: str, header_map: dict) -> dict:
    """Invert the canonical->broker mapping to emit broker-native keys."""
    # header_map is {broker_header: canonical_field}; invert it.
    inverse = {v: k for k, v in header_map.items()}
    out: dict = {}
    for canonical_field, value in canonical.items():
        if canonical_field.startswith("_"):
            continue
        broker_key = inverse.get(canonical_field)
        if broker_key:
            out[broker_key] = value
    return out

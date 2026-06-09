"""Tests for the synthetic broker data generator + broker reformatting."""
from config.settings import broker_mappings
from kafka.producers import data_generator as gen


def test_generate_policy_has_canonical_fields():
    p = gen.generate_policy(1, defect_rate=0.0, anomaly_rate=0.0)
    for field in ["policy_number", "customer_name", "product_name",
                  "premium_amount", "effective_date", "expiry_date"]:
        assert field in p


def test_to_broker_format_uses_native_headers():
    brokers = broker_mappings()["brokers"]
    cfg = brokers["BRK_ALPHA"]
    p = gen.generate_policy(2, defect_rate=0.0)
    native = gen.to_broker_format(p, "BRK_ALPHA", cfg["header_map"]["policy"])
    # Alpha calls policy_number "Policy No"
    assert "Policy No" in native
    assert native["Policy No"] == p["policy_number"]
    # internal ground-truth keys are dropped
    assert not any(k.startswith("_") for k in native)


def test_each_broker_has_distinct_headers():
    brokers = broker_mappings()["brokers"]
    p = gen.generate_policy(3, defect_rate=0.0)
    alpha = set(gen.to_broker_format(p, "BRK_ALPHA", brokers["BRK_ALPHA"]["header_map"]["policy"]))
    beta = set(gen.to_broker_format(p, "BRK_BETA", brokers["BRK_BETA"]["header_map"]["policy"]))
    # The whole point of the platform: brokers look different on the wire.
    assert alpha != beta


def test_defects_can_be_injected():
    # With defect_rate=1.0 every record is defective in some way.
    defects = [gen.generate_policy(i, defect_rate=1.0, anomaly_rate=0.0) for i in range(20)]
    bad = [d for d in defects
           if d["policy_number"] == "" or d["premium_amount"] < 0
           or d["customer_name"] == "" or d["effective_date"] > d["expiry_date"]]
    assert len(bad) == len(defects)

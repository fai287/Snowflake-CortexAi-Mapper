"""Sanity tests for config files and their cross-consistency."""
from config.settings import broker_mappings, canonical_schema, dq_rules


def test_broker_mappings_target_canonical_fields():
    canon = canonical_schema()["entities"]
    canon_policy = {f["name"] for f in canon["policy"]["fields"]}
    canon_claim = {f["name"] for f in canon["claim"]["fields"]}

    for code, cfg in broker_mappings()["brokers"].items():
        for ct, hmap in cfg["header_map"].items():
            targets = set(hmap.values())
            allowed = canon_policy if ct == "policy" else canon_claim
            unknown = targets - allowed
            assert not unknown, f"{code}/{ct} maps to unknown canonical fields: {unknown}"


def test_dq_rules_have_required_keys():
    for entity, rules in dq_rules()["rulesets"].items():
        for r in rules:
            assert {"id", "description", "severity", "expression"} <= set(r)
            assert r["severity"] in {"ERROR", "WARN", "INFO"}


def test_dq_rule_ids_unique():
    ids = []
    for rules in dq_rules()["rulesets"].values():
        ids += [r["id"] for r in rules]
    assert len(ids) == len(set(ids)), "duplicate DQ rule ids"

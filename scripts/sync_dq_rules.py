"""Sync config/data_quality_rules.yaml -> GOVERNANCE.DQ_RULE_CATALOG.

Keeps the database rule catalog in lock-step with the YAML source of truth by
calling SP_LOAD_DQ_RULE for every rule. Idempotent (MERGE on rule_id).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config.settings import dq_rules  # noqa: E402
from src.common.logging_utils import get_logger  # noqa: E402
from src.common.snowflake_client import get_connection  # noqa: E402

log = get_logger("sync-dq-rules")


def main() -> None:
    cfg = dq_rules()
    default_explain = cfg.get("defaults", {}).get("explain", True)
    n = 0
    with get_connection() as conn:
        cur = conn.cursor()
        for entity, rules in cfg.get("rulesets", {}).items():
            for r in rules:
                cur.execute(
                    "CALL GOVERNANCE.SP_LOAD_DQ_RULE(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        r["id"], entity, r["description"], r["severity"],
                        r.get("type", "expression"), r["expression"],
                        r.get("explain", default_explain),
                    ),
                )
                n += 1
        cur.close()
    log.info(f"synced {n} data-quality rules to GOVERNANCE.DQ_RULE_CATALOG")


if __name__ == "__main__":
    main()

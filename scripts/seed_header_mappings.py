"""Seed deterministic broker header mappings into RAW.RAW_HEADER_REGISTRY.

Loads config/broker_mappings.yaml and registers each broker/record-type's
known header layout as a 'seed' mapping. These act as ground truth and a
safety net so the pipeline never blocks on a Cortex call for a known broker;
unseen/drifting layouts are still resolved at runtime by sp_cortex_header_mapping.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config.settings import broker_mappings  # noqa: E402
from src.common.logging_utils import get_logger  # noqa: E402
from src.common.snowflake_client import get_connection  # noqa: E402

log = get_logger("seed-header-mappings")


def main() -> None:
    brokers = broker_mappings()["brokers"]
    n = 0
    with get_connection() as conn:
        cur = conn.cursor()
        for code, cfg in brokers.items():
            for record_type, hmap in cfg.get("header_map", {}).items():
                source_headers = list(hmap.keys())            # broker-native names
                mapping = dict(hmap)                           # {source_header: canonical}
                cur.execute(
                    "CALL RAW.SP_SEED_HEADER_MAPPING(%s,%s,PARSE_JSON(%s),PARSE_JSON(%s))",
                    (code, record_type, json.dumps(source_headers), json.dumps(mapping)),
                )
                n += 1
        cur.close()
    log.info(f"seeded {n} broker/record-type header mappings")


if __name__ == "__main__":
    main()

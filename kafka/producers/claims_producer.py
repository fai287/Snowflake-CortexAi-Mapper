"""Standalone one-shot CLAIM producer (useful for demos / smoke tests).

    python kafka/producers/claims_producer.py --broker BRK_BETA --count 50 \
        --policy-prefix POL-1000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from confluent_kafka import Producer

sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import broker_mappings, settings  # noqa: E402
from kafka.producers import data_generator as gen  # noqa: E402
from kafka.producers.broker_simulator import build_envelope  # noqa: E402
from src.common.logging_utils import get_logger  # noqa: E402

log = get_logger("claims-producer")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="BRK_BETA")
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--policy-prefix", default="POL-1000",
                    help="claims reference policies <prefix><n> for linkage")
    args = ap.parse_args()

    bcfg = broker_mappings()["brokers"][args.broker]
    producer = Producer({"bootstrap.servers": settings.kafka.bootstrap_servers})

    for i in range(1, args.count + 1):
        policy_number = f"{args.policy_prefix}{i % 50}"
        claim = gen.generate_claim(i, policy_number)
        native = gen.to_broker_format(claim, args.broker, bcfg["header_map"]["claim"])
        env = build_envelope(args.broker, bcfg["format"], "claim", native)
        producer.produce(settings.kafka.topic_claims,
                         key=claim["claim_number"], value=json.dumps(env))
        producer.poll(0)

    producer.flush(10)
    log.info(f"sent {args.count} claim messages as {args.broker}")


if __name__ == "__main__":
    main()

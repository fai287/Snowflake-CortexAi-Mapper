"""Standalone one-shot POLICY producer (useful for demos / smoke tests).

Emits a fixed number of policy messages from one broker, then exits.
For continuous multi-broker traffic use broker_simulator.py instead.

    python kafka/producers/policy_producer.py --broker BRK_ALPHA --count 100
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

log = get_logger("policy-producer")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="BRK_ALPHA")
    ap.add_argument("--count", type=int, default=100)
    args = ap.parse_args()

    bcfg = broker_mappings()["brokers"][args.broker]
    producer = Producer({"bootstrap.servers": settings.kafka.bootstrap_servers})

    for i in range(1, args.count + 1):
        policy = gen.generate_policy(i)
        native = gen.to_broker_format(policy, args.broker, bcfg["header_map"]["policy"])
        env = build_envelope(args.broker, bcfg["format"], "policy", native)
        producer.produce(settings.kafka.topic_policies,
                         key=policy["policy_number"], value=json.dumps(env))
        producer.poll(0)

    producer.flush(10)
    log.info(f"sent {args.count} policy messages as {args.broker}")


if __name__ == "__main__":
    main()

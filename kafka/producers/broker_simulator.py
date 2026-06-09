"""Multi-broker Kafka producer / simulator.

Simulates several insurance brokers continuously delivering policy and claim
records to Kafka, each in its OWN native format (broker-specific headers).
Policies go to KAFKA_TOPIC_POLICIES, claims to KAFKA_TOPIC_CLAIMS. The Kafka
message envelope carries broker_code + source_format so the Snowpipe Streaming
client can route and tag rows in RAW.

Run:
    python kafka/producers/broker_simulator.py --rate 5 --duration 0
    # --rate     messages/sec per stream (policies + claims)
    # --duration seconds to run; 0 = forever
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from confluent_kafka import Producer

sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import broker_mappings, settings  # noqa: E402
from kafka.producers import data_generator as gen  # noqa: E402
from src.common.logging_utils import get_logger  # noqa: E402

log = get_logger("broker-simulator")


def build_envelope(broker_code: str, source_format: str, record_type: str, payload: dict) -> dict:
    """Wrap a broker-native payload with routing/lineage metadata."""
    return {
        "broker_code": broker_code,
        "source_format": source_format,
        "record_type": record_type,
        "payload": payload,
    }


def _delivery(err, msg):
    if err is not None:
        log.error(f"delivery failed: {err}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Insurance broker Kafka simulator")
    ap.add_argument("--rate", type=float, default=5.0, help="messages/sec per stream")
    ap.add_argument("--duration", type=int, default=0, help="seconds to run (0 = forever)")
    ap.add_argument("--claim-ratio", type=float, default=0.4, help="fraction of messages that are claims")
    args = ap.parse_args()

    brokers = broker_mappings()["brokers"]
    broker_codes = list(brokers.keys())

    producer = Producer({
        "bootstrap.servers": settings.kafka.bootstrap_servers,
        "client.id": "insurance-broker-simulator",
        "linger.ms": 50,
        "compression.type": "lz4",
    })

    log.info(f"Producing as brokers {broker_codes} -> "
             f"{settings.kafka.topic_policies} / {settings.kafka.topic_claims} "
             f"at {args.rate} msg/s/stream")

    seq = 0
    recent_policies: list[tuple[str, str]] = []  # (broker_code, policy_number) for claim linkage
    start = time.monotonic()
    interval = 1.0 / max(args.rate, 0.001)

    try:
        while True:
            seq += 1
            broker_code = broker_codes[seq % len(broker_codes)]
            bcfg = brokers[broker_code]
            fmt = bcfg["format"]

            is_claim = random.random() < args.claim_ratio
            if is_claim and recent_policies:
                bc, pol_no = random.choice(recent_policies)
                claim = gen.generate_claim(seq, pol_no)
                native = gen.to_broker_format(claim, bc, brokers[bc]["header_map"]["claim"])
                env = build_envelope(bc, brokers[bc]["format"], "claim", native)
                producer.produce(settings.kafka.topic_claims, key=claim["claim_number"],
                                 value=json.dumps(env), on_delivery=_delivery)
            else:
                policy = gen.generate_policy(seq)
                native = gen.to_broker_format(policy, broker_code, bcfg["header_map"]["policy"])
                env = build_envelope(broker_code, fmt, "policy", native)
                producer.produce(settings.kafka.topic_policies, key=policy["policy_number"],
                                 value=json.dumps(env), on_delivery=_delivery)
                if policy["policy_number"]:
                    recent_policies.append((broker_code, policy["policy_number"]))
                    recent_policies = recent_policies[-500:]  # bound memory

            producer.poll(0)
            if seq % 50 == 0:
                log.info(f"produced {seq} messages "
                         f"({len(recent_policies)} policies available for claims)")

            if args.duration and (time.monotonic() - start) >= args.duration:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("interrupted, flushing…")
    finally:
        producer.flush(10)
        log.info(f"done — {seq} messages produced")


if __name__ == "__main__":
    main()

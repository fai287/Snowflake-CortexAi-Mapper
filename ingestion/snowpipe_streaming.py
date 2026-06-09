"""Snowpipe Streaming ingestion client.

Consumes broker messages from Kafka and streams them into the RAW schema with
low latency. Two backends are supported behind one interface:

  1. STREAMING  – the Snowflake Ingest **Streaming** SDK
     (snowflake.ingest.streaming). This is the production path: rows are pushed
     through an open channel and committed continuously (no files, no COPY).

  2. CONNECTOR  – a fallback that performs frequent micro-batch INSERTs via the
     standard Python connector with key-pair auth. Functionally equivalent for
     a local demo when the Streaming SDK/JVM is unavailable. Selected
     automatically if the Streaming SDK cannot be imported, or with --backend.

In a real deployment the recommended option is the **Snowflake Kafka Connector
in Snowpipe Streaming mode** (see ingestion/kafka_connect_snowpipe.json), which
is operationally identical to backend (1) but managed by Kafka Connect.

Run:
    python ingestion/snowpipe_streaming.py                 # auto backend
    python ingestion/snowpipe_streaming.py --backend connector --batch 200
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from confluent_kafka import Consumer

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config.settings import settings  # noqa: E402
from src.common.logging_utils import get_logger  # noqa: E402
from src.common.snowflake_client import get_connection  # noqa: E402

log = get_logger("snowpipe-streaming")

POLICY_TABLE = "RAW.RAW_POLICY_STREAM"
CLAIM_TABLE = "RAW.RAW_CLAIM_STREAM"


# ──────────────────────────────────────────────────────────────────────────
#  Backend: CONNECTOR (micro-batch INSERT … SELECT FROM VALUES PARSE_JSON)
# ──────────────────────────────────────────────────────────────────────────
class ConnectorBackend:
    """Emulates streaming with frequent small inserts via key-pair auth."""

    def __init__(self) -> None:
        self.conn = get_connection(prefer_keypair=True)
        self.cur = self.conn.cursor()

    def insert(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        # Each row carries broker_code, source_format, record_type, payload(json),
        # and kafka metadata. payload is parsed server-side with PARSE_JSON.
        values_sql = ", ".join(["(%s, %s, %s, PARSE_JSON(%s), %s, %s, %s, %s, %s)"] * len(rows))
        params: list = []
        for r in rows:
            params += [
                r["broker_code"], r["source_format"], r["record_type"],
                json.dumps(r["payload"]), r["kafka_topic"], r["kafka_partition"],
                r["kafka_offset"], r["message_key"], r["ingest_channel"],
            ]
        self.cur.execute(
            f"INSERT INTO {table} "
            f"(broker_code, source_format, record_type, payload, kafka_topic, "
            f" kafka_partition, kafka_offset, message_key, ingest_channel) "
            f"SELECT * FROM VALUES {values_sql}",
            params,
        )
        return len(rows)

    def close(self) -> None:
        self.cur.close()
        self.conn.close()


# ──────────────────────────────────────────────────────────────────────────
#  Backend: STREAMING (Snowflake Ingest Streaming SDK)
# ──────────────────────────────────────────────────────────────────────────
class StreamingBackend:
    """Pushes rows through open Snowpipe Streaming channels (no files)."""

    def __init__(self) -> None:
        # Imported lazily so the connector fallback works without the SDK.
        from snowflake.ingest.streaming import (  # type: ignore
            StreamingIngestClient,
        )

        sf = settings.snowflake
        pk_path = sf.private_key_path
        with open(pk_path) as fh:
            private_key = fh.read()

        self.client = StreamingIngestClient(
            "insurance-streaming-client",
            account=sf.account,
            user=sf.user,
            role=sf.role,
            private_key=private_key,
        )
        prefix = settings.snowpipe.channel_prefix
        self._channels = {
            POLICY_TABLE: self._open(prefix + "-policy", "RAW", "RAW_POLICY_STREAM"),
            CLAIM_TABLE: self._open(prefix + "-claim", "RAW", "RAW_CLAIM_STREAM"),
        }

    def _open(self, channel: str, schema: str, table: str):
        return self.client.open_channel(
            channel_name=channel,
            database=settings.snowflake.database,
            schema=schema,
            table=table,
        )

    def insert(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        ch = self._channels[table]
        for r in rows:
            ch.insert_row({
                "broker_code": r["broker_code"],
                "source_format": r["source_format"],
                "record_type": r["record_type"],
                "payload": r["payload"],            # VARIANT accepts dict
                "kafka_topic": r["kafka_topic"],
                "kafka_partition": r["kafka_partition"],
                "kafka_offset": r["kafka_offset"],
                "message_key": r["message_key"],
                "ingest_channel": r["ingest_channel"],
            })
        return len(rows)

    def close(self) -> None:
        for ch in self._channels.values():
            ch.close()
        self.client.close()


def make_backend(name: str):
    if name == "connector":
        log.info("using CONNECTOR backend (micro-batch inserts via key-pair auth)")
        return ConnectorBackend()
    try:
        backend = StreamingBackend()
        log.info("using STREAMING backend (Snowflake Ingest Streaming SDK)")
        return backend
    except Exception as exc:  # SDK missing or channel open failed
        log.warning(f"Streaming SDK unavailable ({exc}); falling back to CONNECTOR backend")
        return ConnectorBackend()


def _envelope_to_row(env: dict, msg) -> dict:
    return {
        "broker_code": env.get("broker_code", "UNKNOWN"),
        "source_format": env.get("source_format"),
        "record_type": env.get("record_type"),
        "payload": env.get("payload", {}),
        "kafka_topic": msg.topic(),
        "kafka_partition": msg.partition(),
        "kafka_offset": msg.offset(),
        "message_key": msg.key().decode() if msg.key() else None,
        "ingest_channel": f"{settings.snowpipe.channel_prefix}-{env.get('record_type','x')}",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Kafka -> Snowpipe Streaming -> RAW")
    ap.add_argument("--backend", choices=["auto", "streaming", "connector"], default="auto")
    ap.add_argument("--batch", type=int, default=100, help="rows per flush")
    ap.add_argument("--flush-secs", type=float, default=2.0, help="max seconds between flushes")
    args = ap.parse_args()

    backend = make_backend("connector" if args.backend == "connector"
                           else "streaming" if args.backend == "streaming" else "auto")

    consumer = Consumer({
        "bootstrap.servers": settings.kafka.bootstrap_servers,
        "group.id": settings.kafka.consumer_group,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([settings.kafka.topic_policies, settings.kafka.topic_claims])
    log.info(f"subscribed to {settings.kafka.topic_policies}, {settings.kafka.topic_claims}")

    pol_buf: list[dict] = []
    clm_buf: list[dict] = []
    last_flush = time.monotonic()
    total = 0

    def flush() -> None:
        nonlocal total, last_flush
        n = backend.insert(POLICY_TABLE, pol_buf) + backend.insert(CLAIM_TABLE, clm_buf)
        if n:
            consumer.commit(asynchronous=False)
            total += n
            log.info(f"flushed {n} rows (total {total})")
        pol_buf.clear()
        clm_buf.clear()
        last_flush = time.monotonic()

    try:
        while True:
            msg = consumer.poll(0.5)
            if msg is not None and not msg.error():
                try:
                    env = json.loads(msg.value())
                    row = _envelope_to_row(env, msg)
                    (clm_buf if row["record_type"] == "claim" else pol_buf).append(row)
                except Exception as exc:
                    log.error(f"bad message skipped: {exc}")

            due = (len(pol_buf) + len(clm_buf)) >= args.batch
            timed = (time.monotonic() - last_flush) >= args.flush_secs
            if (due or timed) and (pol_buf or clm_buf):
                flush()
    except KeyboardInterrupt:
        log.info("interrupted, final flush…")
    finally:
        flush()
        consumer.close()
        backend.close()
        log.info(f"done — {total} rows ingested")


if __name__ == "__main__":
    main()

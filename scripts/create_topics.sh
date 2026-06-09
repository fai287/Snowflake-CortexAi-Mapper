#!/usr/bin/env bash
# Create the Kafka topics used by the platform.
# Works against the local docker-compose broker (default) or any cluster
# reachable via $KAFKA_BOOTSTRAP_SERVERS.
set -euo pipefail

BOOTSTRAP="${KAFKA_BOOTSTRAP_SERVERS:-localhost:9092}"
POLICIES="${KAFKA_TOPIC_POLICIES:-insurance.policies.raw}"
CLAIMS="${KAFKA_TOPIC_CLAIMS:-insurance.claims.raw}"
DLQ="insurance.dlq"
PARTITIONS="${KAFKA_NUM_PARTITIONS:-3}"

# Use the kafka container's CLI if present, else a local kafka-topics binary.
if docker ps --format '{{.Names}}' | grep -q '^insurance-kafka$'; then
  KCMD="docker exec insurance-kafka kafka-topics --bootstrap-server kafka:29092"
else
  KCMD="kafka-topics --bootstrap-server ${BOOTSTRAP}"
fi

for topic in "$POLICIES" "$CLAIMS" "$DLQ"; do
  echo "Creating topic: $topic"
  $KCMD --create --if-not-exists --topic "$topic" \
        --partitions "$PARTITIONS" --replication-factor 1
done

echo "Topics:"
$KCMD --list

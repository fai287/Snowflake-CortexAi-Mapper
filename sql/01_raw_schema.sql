/* ════════════════════════════════════════════════════════════════════════
   01 · RAW schema — landing zone for Snowpipe Streaming
   --------------------------------------------------------------------------
   Snowpipe Streaming appends one row per Kafka message. The original broker
   payload is kept verbatim in a VARIANT column so nothing is ever lost; all
   parsing/typing happens downstream in STAGING. Ingestion metadata columns
   are populated by the streaming client (ingestion/snowpipe_streaming.py).
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA RAW;

-- ── Raw policy stream ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS RAW_POLICY_STREAM (
    raw_id            STRING        DEFAULT UUID_STRING(),   -- surrogate
    broker_code       STRING        NOT NULL,                -- e.g. BRK_ALPHA
    source_format     STRING,                                -- csv | json | xml
    record_type       STRING        DEFAULT 'policy',
    payload           VARIANT       NOT NULL,                -- original message, untyped
    kafka_topic       STRING,
    kafka_partition   INTEGER,
    kafka_offset      BIGINT,
    message_key       STRING,
    ingest_channel    STRING,                                -- Snowpipe Streaming channel
    ingested_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    processed_flag    BOOLEAN       DEFAULT FALSE            -- set TRUE by sp_raw_to_staging
)
COMMENT = 'Verbatim broker policy messages from Kafka via Snowpipe Streaming';

-- ── Raw claim stream ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS RAW_CLAIM_STREAM (
    raw_id            STRING        DEFAULT UUID_STRING(),
    broker_code       STRING        NOT NULL,
    source_format     STRING,
    record_type       STRING        DEFAULT 'claim',
    payload           VARIANT       NOT NULL,
    kafka_topic       STRING,
    kafka_partition   INTEGER,
    kafka_offset      BIGINT,
    message_key       STRING,
    ingest_channel    STRING,
    ingested_at       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    processed_flag    BOOLEAN       DEFAULT FALSE
)
COMMENT = 'Verbatim broker claim messages from Kafka via Snowpipe Streaming';

-- ── Header registry: distinct header sets seen per broker/record type ───
-- Populated by sp_raw_to_staging; consumed by sp_cortex_header_mapping so
-- the LLM is only invoked once per NEW header signature, not per row.
CREATE TABLE IF NOT EXISTS RAW_HEADER_REGISTRY (
    header_signature  STRING        PRIMARY KEY,   -- md5 of sorted source keys
    broker_code       STRING,
    record_type       STRING,
    source_headers    ARRAY,                       -- raw header names
    mapping           VARIANT,                     -- {source_header: canonical_field}
    mapping_source    STRING,                      -- 'cortex' | 'seed' | 'manual'
    confidence        FLOAT,
    first_seen_at     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    last_seen_at      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Distinct broker header signatures and their Cortex-resolved canonical mapping';

-- Helpful for monitoring ingest freshness from the dashboard
CREATE OR REPLACE VIEW V_RAW_INGEST_FRESHNESS AS
SELECT broker_code,
       record_type,
       COUNT(*)                                   AS rows_landed,
       MAX(ingested_at)                           AS last_ingested_at,
       DATEDIFF('second', MAX(ingested_at), CURRENT_TIMESTAMP()) AS seconds_since_last
FROM (
    SELECT broker_code, record_type, ingested_at FROM RAW_POLICY_STREAM
    UNION ALL
    SELECT broker_code, record_type, ingested_at FROM RAW_CLAIM_STREAM
)
GROUP BY 1, 2;

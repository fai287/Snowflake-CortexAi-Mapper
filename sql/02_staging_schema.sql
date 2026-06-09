/* ════════════════════════════════════════════════════════════════════════
   02 · STAGING schema — canonical, typed, broker-agnostic
   --------------------------------------------------------------------------
   sp_raw_to_staging flattens RAW VARIANT payloads, applies the Cortex-resolved
   header mapping, casts to canonical types, and standardizes values. Records
   here share ONE shape regardless of which broker sent them. Data-quality
   checks run against these tables before promotion to ANALYTICS.
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA STAGING;

-- ── Standardized policies ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS STG_POLICY (
    stg_id            STRING        DEFAULT UUID_STRING(),
    raw_id            STRING,                       -- lineage to RAW.RAW_POLICY_STREAM
    broker_code       STRING,
    policy_number     STRING,
    customer_name     STRING,
    product_name      STRING,                       -- raw product text from broker
    product_line      STRING,                       -- Cortex-classified (AUTO/HOME/…)
    premium_amount    NUMBER(18,2),
    sum_insured       NUMBER(18,2),
    effective_date    DATE,
    expiry_date       DATE,
    broker_agent      STRING,
    -- standardization / lineage metadata
    mapping_source    STRING,                       -- cortex | seed | manual
    mapping_confidence FLOAT,
    dq_status         STRING        DEFAULT 'PENDING', -- PENDING | PASS | WARN | FAIL
    loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Canonical, typed policy records (one shape for all brokers)';

-- ── Standardized claims ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS STG_CLAIM (
    stg_id            STRING        DEFAULT UUID_STRING(),
    raw_id            STRING,
    broker_code       STRING,
    claim_number      STRING,
    policy_number     STRING,
    loss_date         DATE,
    reported_date     DATE,
    claim_amount      NUMBER(18,2),
    claim_status      STRING,
    loss_description  STRING,
    reporting_lag_days INTEGER,                     -- derived: reported - loss
    dq_status         STRING        DEFAULT 'PENDING',
    loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Canonical, typed claim records (one shape for all brokers)';

-- ── Quarantine: records that failed ERROR-severity DQ rules ─────────────
CREATE TABLE IF NOT EXISTS STG_QUARANTINE (
    quarantine_id     STRING        DEFAULT UUID_STRING(),
    entity            STRING,                       -- policy | claim
    stg_id            STRING,
    broker_code       STRING,
    failed_rules      ARRAY,                        -- list of rule ids
    record_snapshot   VARIANT,                      -- full record at time of failure
    cortex_explanation STRING,                      -- NL reason from Cortex
    quarantined_at    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    resolved          BOOLEAN       DEFAULT FALSE
)
COMMENT = 'Records blocked from ANALYTICS due to ERROR-severity validation failures';

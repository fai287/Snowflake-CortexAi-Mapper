/* ════════════════════════════════════════════════════════════════════════
   03 · ANALYTICS schema — conformed dimensional model
   --------------------------------------------------------------------------
   sp_staging_to_analytics promotes DQ-passing records into conformed
   dimensions and facts (star schema), applying Cortex enrichment
   (risk tier, customer segment) and anomaly scores. This is the
   query-optimized layer the SEMANTIC views and dashboard read from.
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA ANALYTICS;

-- ── Dimension: Broker ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS DIM_BROKER (
    broker_key        INTEGER       IDENTITY START 1 INCREMENT 1,
    broker_code       STRING        UNIQUE,
    broker_name       STRING,
    source_format     STRING,
    created_at        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ── Dimension: Customer (deduplicated across brokers) ──────────────────
CREATE TABLE IF NOT EXISTS DIM_CUSTOMER (
    customer_key      INTEGER       IDENTITY START 1 INCREMENT 1,
    customer_id       STRING        UNIQUE,         -- hash(normalized name)
    customer_name     STRING,
    customer_segment  STRING,                       -- Cortex enrichment (e.g. RETAIL/SME/CORP)
    risk_tier         STRING,                       -- Cortex enrichment
    first_seen_at     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ── Dimension: Product ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS DIM_PRODUCT (
    product_key       INTEGER       IDENTITY START 1 INCREMENT 1,
    product_line      STRING        UNIQUE,         -- AUTO/HOME/LIFE/…
    description       STRING
);

-- ── Dimension: Policy (conformed business key = policy_number) ─────────
CREATE TABLE IF NOT EXISTS DIM_POLICY (
    policy_key        INTEGER       IDENTITY START 1 INCREMENT 1,
    policy_number     STRING        UNIQUE,
    broker_key        INTEGER,
    customer_key      INTEGER,
    product_key       INTEGER,
    product_line      STRING,
    premium_amount    NUMBER(18,2),
    sum_insured       NUMBER(18,2),
    effective_date    DATE,
    expiry_date       DATE,
    policy_term_days  INTEGER,
    is_active         BOOLEAN,
    anomaly_score     FLOAT,                        -- premium anomaly (0-1)
    anomaly_reason    STRING,                       -- Cortex explanation if flagged
    loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ── Fact: Premium (one row per policy, additive premium measures) ──────
CREATE TABLE IF NOT EXISTS FACT_PREMIUM (
    premium_key       INTEGER       IDENTITY START 1 INCREMENT 1,
    policy_key        INTEGER,
    broker_key        INTEGER,
    customer_key      INTEGER,
    product_key       INTEGER,
    effective_date    DATE,
    premium_amount    NUMBER(18,2),
    sum_insured       NUMBER(18,2),
    loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ── Fact: Claim (one row per claim, additive claim measures) ───────────
CREATE TABLE IF NOT EXISTS FACT_CLAIM (
    claim_key         INTEGER       IDENTITY START 1 INCREMENT 1,
    claim_number      STRING        UNIQUE,
    policy_key        INTEGER,
    broker_key        INTEGER,
    customer_key      INTEGER,
    product_key       INTEGER,
    loss_date         DATE,
    reported_date     DATE,
    reporting_lag_days INTEGER,
    claim_amount      NUMBER(18,2),
    claim_status      STRING,
    loss_description  STRING,
    sentiment_score   FLOAT,                        -- Cortex SENTIMENT on narrative
    anomaly_score     FLOAT,
    anomaly_reason    STRING,
    loaded_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Seed the product dimension with the controlled vocabulary
MERGE INTO DIM_PRODUCT t
USING (
    SELECT column1 AS product_line FROM VALUES
      ('AUTO'),('HOME'),('LIFE'),('HEALTH'),('TRAVEL'),
      ('COMMERCIAL'),('MARINE'),('OTHER')
) s
ON t.product_line = s.product_line
WHEN NOT MATCHED THEN INSERT (product_line, description) VALUES (s.product_line, s.product_line || ' insurance');

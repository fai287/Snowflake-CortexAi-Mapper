/* ════════════════════════════════════════════════════════════════════════
   04 · SEMANTIC schema — business-facing views
   --------------------------------------------------------------------------
   Friendly, denormalized views with business names and pre-joined context.
   These are the ONLY objects the dashboard and the conversational AI agent
   are allowed to query, which keeps NL→SQL safe and stable. The Cortex
   Analyst semantic model (sql/semantic/insurance_semantic_model.yaml) maps
   directly onto these views.
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA SEMANTIC;

-- ── Policies (business view) ────────────────────────────────────────────
CREATE OR REPLACE VIEW POLICIES AS
SELECT
    p.policy_number,
    b.broker_name,
    b.broker_code,
    c.customer_name,
    c.customer_segment,
    c.risk_tier,
    p.product_line,
    p.premium_amount,
    p.sum_insured,
    p.effective_date,
    p.expiry_date,
    p.policy_term_days,
    p.is_active,
    p.anomaly_score,
    p.anomaly_reason
FROM ANALYTICS.DIM_POLICY  p
LEFT JOIN ANALYTICS.DIM_BROKER   b ON p.broker_key   = b.broker_key
LEFT JOIN ANALYTICS.DIM_CUSTOMER c ON p.customer_key = c.customer_key;

COMMENT ON VIEW POLICIES IS 'One row per policy with broker, customer and product context';

-- ── Claims (business view) ──────────────────────────────────────────────
CREATE OR REPLACE VIEW CLAIMS AS
SELECT
    f.claim_number,
    f.claim_status,
    pol.policy_number,
    b.broker_name,
    b.broker_code,
    c.customer_name,
    pol.product_line,
    f.loss_date,
    f.reported_date,
    f.reporting_lag_days,
    f.claim_amount,
    f.sentiment_score,
    f.anomaly_score,
    f.anomaly_reason,
    f.loss_description
FROM ANALYTICS.FACT_CLAIM f
LEFT JOIN ANALYTICS.DIM_POLICY   pol ON f.policy_key   = pol.policy_key
LEFT JOIN ANALYTICS.DIM_BROKER   b   ON f.broker_key   = b.broker_key
LEFT JOIN ANALYTICS.DIM_CUSTOMER c   ON f.customer_key = c.customer_key;

COMMENT ON VIEW CLAIMS IS 'One row per claim with policy, broker and customer context';

-- ── Broker performance (aggregate) ──────────────────────────────────────
CREATE OR REPLACE VIEW BROKER_PERFORMANCE AS
SELECT
    b.broker_code,
    b.broker_name,
    COUNT(DISTINCT pol.policy_number)                      AS policy_count,
    COALESCE(SUM(pol.premium_amount), 0)                   AS total_premium,
    COUNT(DISTINCT cl.claim_number)                        AS claim_count,
    COALESCE(SUM(cl.claim_amount), 0)                      AS total_claims_amount,
    CASE WHEN SUM(pol.premium_amount) > 0
         THEN ROUND(SUM(cl.claim_amount) / SUM(pol.premium_amount), 4)
         ELSE NULL END                                     AS loss_ratio,
    AVG(pol.anomaly_score)                                 AS avg_policy_anomaly
FROM ANALYTICS.DIM_BROKER b
LEFT JOIN ANALYTICS.DIM_POLICY pol ON pol.broker_key = b.broker_key
LEFT JOIN ANALYTICS.FACT_CLAIM cl  ON cl.broker_key  = b.broker_key
GROUP BY 1, 2;

COMMENT ON VIEW BROKER_PERFORMANCE IS 'Per-broker policy/premium/claim volumes and loss ratio';

-- ── Ingestion health (operational) ──────────────────────────────────────
CREATE OR REPLACE VIEW INGESTION_HEALTH AS
SELECT
    src.broker_code,
    src.record_type,
    src.rows_landed,
    src.last_ingested_at,
    src.seconds_since_last,
    CASE WHEN src.seconds_since_last <= 120 THEN 'HEALTHY'
         WHEN src.seconds_since_last <= 600 THEN 'LAGGING'
         ELSE 'STALE' END                                  AS ingest_status
FROM RAW.V_RAW_INGEST_FRESHNESS src;

COMMENT ON VIEW INGESTION_HEALTH IS 'Real-time ingest freshness per broker and record type';

-- ── Validation summary (governance roll-up for the dashboard) ──────────
CREATE OR REPLACE VIEW VALIDATION_SUMMARY AS
SELECT
    r.entity,
    r.rule_id,
    rc.description           AS rule_description,
    rc.severity,
    COUNT(*)                 AS failure_count,
    MAX(r.evaluated_at)      AS last_failure_at
FROM GOVERNANCE.DQ_RESULT r
LEFT JOIN GOVERNANCE.DQ_RULE_CATALOG rc ON r.rule_id = rc.rule_id
WHERE r.passed = FALSE
GROUP BY 1, 2, 3, 4;

COMMENT ON VIEW VALIDATION_SUMMARY IS 'Validation failures grouped by rule and severity';

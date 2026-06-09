/* ════════════════════════════════════════════════════════════════════════
   sp_staging_to_analytics
   --------------------------------------------------------------------------
   Promotes DQ-passing STAGING records (dq_status IN PASS/WARN) into the
   conformed ANALYTICS star schema: upserts brokers/customers/policies, then
   appends premium and claim facts. FAIL records stay quarantined. Idempotent
   via MERGE on business keys. Run sp_cortex_enrichment BEFORE this so segment
   / risk_tier / product_line are available, and sp_anomaly_detection AFTER.
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA ANALYTICS;

CREATE OR REPLACE PROCEDURE SP_STAGING_TO_ANALYTICS()
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    n_pol INTEGER DEFAULT 0;
    n_clm INTEGER DEFAULT 0;
BEGIN
    -- 1. Brokers (from config-known codes seen in staging)
    MERGE INTO ANALYTICS.DIM_BROKER d
    USING (SELECT DISTINCT broker_code FROM STAGING.STG_POLICY
           UNION SELECT DISTINCT broker_code FROM STAGING.STG_CLAIM) s
    ON d.broker_code = s.broker_code
    WHEN NOT MATCHED THEN INSERT (broker_code, broker_name)
        VALUES (s.broker_code, s.broker_code);

    -- 2. Customers (segment/risk filled by enrichment; ensure existence)
    MERGE INTO ANALYTICS.DIM_CUSTOMER d
    USING (SELECT DISTINCT MD5(UPPER(TRIM(customer_name))) AS customer_id, customer_name
           FROM STAGING.STG_POLICY WHERE dq_status IN ('PASS','WARN')) s
    ON d.customer_id = s.customer_id
    WHEN NOT MATCHED THEN INSERT (customer_id, customer_name) VALUES (s.customer_id, s.customer_name);

    -- 3. Policies dimension
    MERGE INTO ANALYTICS.DIM_POLICY d
    USING (
        SELECT
            p.policy_number,
            b.broker_key,
            c.customer_key,
            pr.product_key,
            p.product_line,
            p.premium_amount,
            p.sum_insured,
            p.effective_date,
            p.expiry_date,
            DATEDIFF('day', p.effective_date, p.expiry_date)        AS policy_term_days,
            (CURRENT_DATE() BETWEEN p.effective_date AND p.expiry_date) AS is_active
        FROM STAGING.STG_POLICY p
        LEFT JOIN ANALYTICS.DIM_BROKER   b  ON b.broker_code = p.broker_code
        LEFT JOIN ANALYTICS.DIM_CUSTOMER c  ON c.customer_id = MD5(UPPER(TRIM(p.customer_name)))
        LEFT JOIN ANALYTICS.DIM_PRODUCT  pr ON pr.product_line = p.product_line
        WHERE p.dq_status IN ('PASS','WARN')
    ) s
    ON d.policy_number = s.policy_number
    WHEN MATCHED THEN UPDATE SET
        premium_amount = s.premium_amount, sum_insured = s.sum_insured,
        effective_date = s.effective_date, expiry_date = s.expiry_date,
        product_line = s.product_line, policy_term_days = s.policy_term_days,
        is_active = s.is_active, customer_key = s.customer_key, broker_key = s.broker_key,
        product_key = s.product_key
    WHEN NOT MATCHED THEN INSERT
        (policy_number, broker_key, customer_key, product_key, product_line,
         premium_amount, sum_insured, effective_date, expiry_date, policy_term_days, is_active)
        VALUES (s.policy_number, s.broker_key, s.customer_key, s.product_key, s.product_line,
                s.premium_amount, s.sum_insured, s.effective_date, s.expiry_date,
                s.policy_term_days, s.is_active);
    n_pol := SQLROWCOUNT;

    -- 4. Premium facts (append once per policy)
    INSERT INTO ANALYTICS.FACT_PREMIUM
        (policy_key, broker_key, customer_key, product_key, effective_date, premium_amount, sum_insured)
    SELECT dp.policy_key, dp.broker_key, dp.customer_key, dp.product_key,
           dp.effective_date, dp.premium_amount, dp.sum_insured
    FROM ANALYTICS.DIM_POLICY dp
    WHERE dp.policy_key NOT IN (SELECT policy_key FROM ANALYTICS.FACT_PREMIUM WHERE policy_key IS NOT NULL);

    -- 5. Claim facts
    MERGE INTO ANALYTICS.FACT_CLAIM f
    USING (
        SELECT
            cl.claim_number,
            dp.policy_key,
            dp.broker_key,
            dp.customer_key,
            dp.product_key,
            cl.loss_date,
            cl.reported_date,
            cl.reporting_lag_days,
            cl.claim_amount,
            cl.claim_status,
            cl.loss_description,
            cl.sentiment_score
        FROM STAGING.STG_CLAIM cl
        LEFT JOIN ANALYTICS.DIM_POLICY dp ON dp.policy_number = cl.policy_number
        WHERE cl.dq_status IN ('PASS','WARN')
    ) s
    ON f.claim_number = s.claim_number
    WHEN MATCHED THEN UPDATE SET
        claim_status = s.claim_status, claim_amount = s.claim_amount,
        reported_date = s.reported_date, reporting_lag_days = s.reporting_lag_days,
        sentiment_score = s.sentiment_score
    WHEN NOT MATCHED THEN INSERT
        (claim_number, policy_key, broker_key, customer_key, product_key, loss_date,
         reported_date, reporting_lag_days, claim_amount, claim_status, loss_description, sentiment_score)
        VALUES (s.claim_number, s.policy_key, s.broker_key, s.customer_key, s.product_key, s.loss_date,
                s.reported_date, s.reporting_lag_days, s.claim_amount, s.claim_status,
                s.loss_description, s.sentiment_score);
    n_clm := SQLROWCOUNT;

    INSERT INTO GOVERNANCE.PIPELINE_LOG (stage, rows_out, message, status)
    VALUES ('staging_to_analytics', :n_pol + :n_clm,
            'policies=' || :n_pol || ', claims=' || :n_clm, 'SUCCESS');

    RETURN 'Promoted ' || n_pol || ' policies and ' || n_clm || ' claims to ANALYTICS.';
END;
$$;

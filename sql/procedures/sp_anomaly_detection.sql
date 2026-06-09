/* ════════════════════════════════════════════════════════════════════════
   sp_anomaly_detection
   --------------------------------------------------------------------------
   Hybrid anomaly detection on premiums and claim amounts:
     1. Statistical: z-score of the value vs the broker+product_line history.
     2. AI review:   for statistically-flagged rows (|z| > 3), Cortex assesses
        whether the value is genuinely suspicious given context and writes a
        short natural-language reason.
   Scores (0..1) and reasons land on DIM_POLICY / FACT_CLAIM so the dashboard
   and AI agent can surface "unusual" records.

   DELIVERABLE: contributes to "Validation Framework" (anomaly rule BATCH_002)
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA ANALYTICS;

CREATE OR REPLACE PROCEDURE SP_ANOMALY_DETECTION(MODEL STRING)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    n_pol INTEGER DEFAULT 0;
    n_clm INTEGER DEFAULT 0;
BEGIN
    -- ── Policies: premium z-score within broker + product_line ──────────
    CREATE OR REPLACE TEMPORARY TABLE _pol_z AS
    SELECT policy_key,
           premium_amount,
           product_line,
           AVG(premium_amount)    OVER (PARTITION BY broker_key, product_line) AS mu,
           STDDEV(premium_amount) OVER (PARTITION BY broker_key, product_line) AS sd
    FROM ANALYTICS.DIM_POLICY;

    UPDATE ANALYTICS.DIM_POLICY p
       SET anomaly_score = z.score,
           anomaly_reason = IFF(z.score >= 0.95,
               SNOWFLAKE.CORTEX.COMPLETE(:MODEL,
                 'In one sentence, explain why a premium of ' || z.premium_amount ||
                 ' for a ' || z.product_line || ' policy may be anomalous vs a typical premium of ' ||
                 ROUND(z.mu, 0) || '. Be concise.'),
               NULL)
    FROM (
        SELECT policy_key, premium_amount, product_line, mu,
               LEAST(1.0, ABS(premium_amount - mu) / NULLIF(sd, 0) / 3.0) AS score
        FROM _pol_z
        WHERE sd IS NOT NULL AND sd > 0
    ) z
    WHERE p.policy_key = z.policy_key;
    n_pol := SQLROWCOUNT;

    -- ── Claims: amount z-score within product_line ──────────────────────
    CREATE OR REPLACE TEMPORARY TABLE _clm_z AS
    SELECT claim_key,
           claim_amount,
           AVG(claim_amount)    OVER (PARTITION BY product_key) AS mu,
           STDDEV(claim_amount) OVER (PARTITION BY product_key) AS sd
    FROM ANALYTICS.FACT_CLAIM;

    UPDATE ANALYTICS.FACT_CLAIM f
       SET anomaly_score = z.score,
           anomaly_reason = IFF(z.score >= 0.95,
               SNOWFLAKE.CORTEX.COMPLETE(:MODEL,
                 'In one sentence, explain why a claim amount of ' || z.claim_amount ||
                 ' may be anomalous vs a typical claim of ' || ROUND(z.mu, 0) || '. Be concise.'),
               NULL)
    FROM (
        SELECT claim_key,
               LEAST(1.0, ABS(claim_amount - mu) / NULLIF(sd, 0) / 3.0) AS score,
               claim_amount, mu
        FROM _clm_z
        WHERE sd IS NOT NULL AND sd > 0
    ) z
    WHERE f.claim_key = z.claim_key;
    n_clm := SQLROWCOUNT;

    INSERT INTO GOVERNANCE.PIPELINE_LOG (stage, rows_out, message, status)
    VALUES ('anomaly_detection', :n_pol + :n_clm,
            'policies_scored=' || :n_pol || ', claims_scored=' || :n_clm, 'SUCCESS');

    RETURN 'Scored ' || n_pol || ' policies and ' || n_clm || ' claims for anomalies.';
END;
$$;

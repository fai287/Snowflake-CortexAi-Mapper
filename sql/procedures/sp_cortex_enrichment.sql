/* ════════════════════════════════════════════════════════════════════════
   sp_cortex_enrichment
   --------------------------------------------------------------------------
   Applies Cortex AI to DQ-passing STAGING records before they are promoted:
     • product_line   – CLASSIFY_TEXT on the raw product text
     • customer_segment / risk_tier – COMPLETE (JSON) on customer + policy context
     • claim sentiment – SENTIMENT on the loss narrative
   Results are written back to STAGING so sp_staging_to_analytics can carry
   them into the dimensional model.

   DELIVERABLE: contributes to "Semantic Layer" (classification + enrichment)
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA STAGING;

-- Add enrichment columns if a fresh deploy created the base table only.
ALTER TABLE STAGING.STG_CLAIM ADD COLUMN IF NOT EXISTS sentiment_score FLOAT;

CREATE OR REPLACE PROCEDURE SP_CORTEX_ENRICHMENT(MODEL STRING)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    n_prod INTEGER DEFAULT 0;
    n_sent INTEGER DEFAULT 0;
BEGIN
    -- 1. Classify product line for policies not yet classified
    UPDATE STAGING.STG_POLICY
       SET product_line = SEMANTIC.FN_CLASSIFY_PRODUCT(product_name)
     WHERE product_line IS NULL
       AND dq_status IN ('PASS', 'WARN');
    n_prod := SQLROWCOUNT;

    -- 2. Sentiment on claim narratives
    UPDATE STAGING.STG_CLAIM
       SET sentiment_score = SEMANTIC.FN_CLAIM_SENTIMENT(loss_description)
     WHERE sentiment_score IS NULL
       AND dq_status IN ('PASS', 'WARN')
       AND loss_description IS NOT NULL;
    n_sent := SQLROWCOUNT;

    -- 3. Customer segment + risk tier (batched COMPLETE in JSON mode).
    --    One call per distinct customer to control cost; result cached in DIM.
    MERGE INTO ANALYTICS.DIM_CUSTOMER d
    USING (
        SELECT DISTINCT
            MD5(UPPER(TRIM(customer_name)))                       AS customer_id,
            customer_name,
            -- Ask Cortex for {"segment": ..., "risk_tier": ...} as strict JSON
            TRY_PARSE_JSON(REGEXP_SUBSTR(
                SNOWFLAKE.CORTEX.COMPLETE(:MODEL,
                  'Classify this insurance customer. Return ONLY JSON ' ||
                  '{"segment":"RETAIL|SME|CORPORATE","risk_tier":"LOW|MEDIUM|HIGH|SEVERE"}. ' ||
                  'Customer="' || customer_name || '", product=' || COALESCE(product_line,'?') ||
                  ', premium=' || COALESCE(premium_amount::STRING,'?') ||
                  ', sum_insured=' || COALESCE(sum_insured::STRING,'?') || '.'),
                '\\{[\\s\\S]*\\}')) AS enrich
        FROM STAGING.STG_POLICY
        WHERE dq_status IN ('PASS','WARN')
          AND MD5(UPPER(TRIM(customer_name))) NOT IN (SELECT customer_id FROM ANALYTICS.DIM_CUSTOMER)
    ) s
    ON d.customer_id = s.customer_id
    WHEN NOT MATCHED THEN INSERT (customer_id, customer_name, customer_segment, risk_tier)
        VALUES (s.customer_id, s.customer_name,
                s.enrich:segment::STRING, s.enrich:risk_tier::STRING);

    INSERT INTO GOVERNANCE.CORTEX_CALL_LOG (task, model, success)
    VALUES ('enrich', :MODEL, TRUE);

    RETURN 'Enriched ' || n_prod || ' product lines, ' || n_sent || ' sentiments, plus customer segments.';
END;
$$;

/* ════════════════════════════════════════════════════════════════════════
   sp_run_pipeline  +  scheduled TASK
   --------------------------------------------------------------------------
   End-to-end micro-batch orchestration. Chains every stage in order so the
   platform can run on a schedule (Snowflake Task) or be called on demand by
   the dashboard "Refresh" button. Each stage is independently logged.
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA GOVERNANCE;

CREATE OR REPLACE PROCEDURE SP_RUN_PIPELINE(MODEL STRING)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    summary STRING DEFAULT '';
BEGIN
    -- 1. RAW -> STAGING (incl. Cortex header mapping)
    CALL STAGING.SP_RAW_TO_STAGING(:MODEL);
    summary := summary || 'raw_to_staging: ' || SQLRESULT || ' | ';

    -- 2. Validation framework (policies then claims)
    CALL GOVERNANCE.SP_RUN_DATA_QUALITY('policy', :MODEL);
    summary := summary || 'dq_policy: ' || SQLRESULT || ' | ';
    CALL GOVERNANCE.SP_RUN_DATA_QUALITY('claim', :MODEL);
    summary := summary || 'dq_claim: ' || SQLRESULT || ' | ';

    -- 3. Cortex enrichment (classification + segment + sentiment)
    CALL STAGING.SP_CORTEX_ENRICHMENT(:MODEL);
    summary := summary || 'enrich: ' || SQLRESULT || ' | ';

    -- 4. Promote to ANALYTICS star schema
    CALL ANALYTICS.SP_STAGING_TO_ANALYTICS();
    summary := summary || 'promote: ' || SQLRESULT || ' | ';

    -- 5. Anomaly scoring
    CALL ANALYTICS.SP_ANOMALY_DETECTION(:MODEL);
    summary := summary || 'anomaly: ' || SQLRESULT;

    RETURN summary;
END;
$$;

-- ── Scheduled micro-batch every 2 minutes ───────────────────────────────
-- Uses the session-default Cortex model. ALTER TASK … RESUME to enable.
CREATE OR REPLACE TASK GOVERNANCE.TASK_RUN_PIPELINE
    WAREHOUSE = INSURANCE_WH
    SCHEDULE  = '2 MINUTE'
    COMMENT   = 'Micro-batch: RAW -> STAGING -> DQ -> enrich -> ANALYTICS -> anomaly'
AS
    CALL GOVERNANCE.SP_RUN_PIPELINE('claude-3-5-sonnet');

-- Enable with:  ALTER TASK GOVERNANCE.TASK_RUN_PIPELINE RESUME;

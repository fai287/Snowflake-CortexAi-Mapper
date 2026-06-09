/* ════════════════════════════════════════════════════════════════════════
   sp_raw_to_staging
   --------------------------------------------------------------------------
   Flattens RAW VARIANT payloads into the canonical STAGING tables using the
   Cortex-resolved header mapping in RAW_HEADER_REGISTRY. Steps:
     1. Register any unseen header signatures (so mapping can be resolved).
     2. Resolve mappings via Cortex (sp_cortex_header_mapping).
     3. For each unprocessed RAW row, look up its mapping and project the
        payload onto canonical columns, casting types and standardizing.
     4. Mark RAW rows processed; log to GOVERNANCE.PIPELINE_LOG.

   Implemented with a Snowpark-friendly SQL body. The dynamic projection uses
   OBJECT_GET on the VARIANT payload keyed by the source header for each
   canonical field, derived from the registry mapping.
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA STAGING;

CREATE OR REPLACE PROCEDURE SP_RAW_TO_STAGING(MODEL STRING)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    pol_rows INTEGER DEFAULT 0;
    clm_rows INTEGER DEFAULT 0;
BEGIN
    -- 1. Register unseen header signatures for policies + claims
    INSERT INTO RAW.RAW_HEADER_REGISTRY (header_signature, broker_code, record_type, source_headers)
    WITH sig AS (
        SELECT broker_code, record_type,
               ARRAY_AGG(DISTINCT k) AS keys
        FROM (
            SELECT broker_code, record_type, f.key AS k
            FROM RAW.RAW_POLICY_STREAM, LATERAL FLATTEN(input => payload) f
            WHERE processed_flag = FALSE
        )
        GROUP BY broker_code, record_type
    )
    SELECT MD5(ARRAY_TO_STRING(ARRAY_SORT(keys), '|')), broker_code, record_type, keys
    FROM sig
    WHERE MD5(ARRAY_TO_STRING(ARRAY_SORT(keys), '|')) NOT IN
          (SELECT header_signature FROM RAW.RAW_HEADER_REGISTRY);

    -- (claims signatures)
    INSERT INTO RAW.RAW_HEADER_REGISTRY (header_signature, broker_code, record_type, source_headers)
    WITH sig AS (
        SELECT broker_code, record_type, ARRAY_AGG(DISTINCT k) AS keys
        FROM (
            SELECT broker_code, record_type, f.key AS k
            FROM RAW.RAW_CLAIM_STREAM, LATERAL FLATTEN(input => payload) f
            WHERE processed_flag = FALSE
        )
        GROUP BY broker_code, record_type
    )
    SELECT MD5(ARRAY_TO_STRING(ARRAY_SORT(keys), '|')), broker_code, record_type, keys
    FROM sig
    WHERE MD5(ARRAY_TO_STRING(ARRAY_SORT(keys), '|')) NOT IN
          (SELECT header_signature FROM RAW.RAW_HEADER_REGISTRY);

    -- 2. Resolve any new signatures via Cortex
    CALL RAW.SP_CORTEX_HEADER_MAPPING(:MODEL);

    -- 3a. Project policies onto canonical columns.
    --     For each canonical field, find its source header from the registry
    --     mapping (value->key inversion) and OBJECT_GET it from the payload.
    INSERT INTO STAGING.STG_POLICY
        (raw_id, broker_code, policy_number, customer_name, product_name,
         premium_amount, sum_insured, effective_date, expiry_date, broker_agent,
         mapping_source, mapping_confidence)
    SELECT
        r.raw_id,
        r.broker_code,
        TRIM(OBJECT_GET(r.payload, m.policy_number)::STRING),
        TRIM(OBJECT_GET(r.payload, m.customer_name)::STRING),
        TRIM(OBJECT_GET(r.payload, m.product_name)::STRING),
        TRY_TO_DECIMAL(REGEXP_REPLACE(OBJECT_GET(r.payload, m.premium_amount)::STRING, '[^0-9.\\-]', ''), 18, 2),
        TRY_TO_DECIMAL(REGEXP_REPLACE(OBJECT_GET(r.payload, m.sum_insured)::STRING,    '[^0-9.\\-]', ''), 18, 2),
        COALESCE(TRY_TO_DATE(OBJECT_GET(r.payload, m.effective_date)::STRING),
                 TRY_TO_DATE(OBJECT_GET(r.payload, m.effective_date)::STRING, 'DD/MM/YYYY'),
                 TRY_TO_DATE(OBJECT_GET(r.payload, m.effective_date)::STRING, 'MM/DD/YYYY')),
        COALESCE(TRY_TO_DATE(OBJECT_GET(r.payload, m.expiry_date)::STRING),
                 TRY_TO_DATE(OBJECT_GET(r.payload, m.expiry_date)::STRING, 'DD/MM/YYYY'),
                 TRY_TO_DATE(OBJECT_GET(r.payload, m.expiry_date)::STRING, 'MM/DD/YYYY')),
        TRIM(OBJECT_GET(r.payload, m.broker_agent)::STRING),
        reg.mapping_source,
        reg.confidence
    FROM RAW.RAW_POLICY_STREAM r
    JOIN RAW.RAW_HEADER_REGISTRY reg
      ON reg.header_signature = MD5(ARRAY_TO_STRING(ARRAY_SORT(OBJECT_KEYS(r.payload)), '|'))
    -- invert the registry mapping: canonical_field -> source_header
    JOIN LATERAL (
        SELECT
            MAX(IFF(value::STRING = 'policy_number',  key, NULL)) AS policy_number,
            MAX(IFF(value::STRING = 'customer_name',  key, NULL)) AS customer_name,
            MAX(IFF(value::STRING = 'product_name',   key, NULL)) AS product_name,
            MAX(IFF(value::STRING = 'premium_amount', key, NULL)) AS premium_amount,
            MAX(IFF(value::STRING = 'sum_insured',    key, NULL)) AS sum_insured,
            MAX(IFF(value::STRING = 'effective_date', key, NULL)) AS effective_date,
            MAX(IFF(value::STRING = 'expiry_date',    key, NULL)) AS expiry_date,
            MAX(IFF(value::STRING = 'broker_agent',   key, NULL)) AS broker_agent
        FROM LATERAL FLATTEN(input => reg.mapping)
    ) m
    WHERE r.processed_flag = FALSE AND reg.mapping IS NOT NULL;

    pol_rows := SQLROWCOUNT;

    -- 3b. Project claims
    INSERT INTO STAGING.STG_CLAIM
        (raw_id, broker_code, claim_number, policy_number, loss_date, reported_date,
         claim_amount, claim_status, loss_description, reporting_lag_days)
    SELECT
        r.raw_id,
        r.broker_code,
        TRIM(OBJECT_GET(r.payload, m.claim_number)::STRING),
        TRIM(OBJECT_GET(r.payload, m.policy_number)::STRING),
        COALESCE(TRY_TO_DATE(OBJECT_GET(r.payload, m.loss_date)::STRING),
                 TRY_TO_DATE(OBJECT_GET(r.payload, m.loss_date)::STRING, 'DD/MM/YYYY')),
        COALESCE(TRY_TO_DATE(OBJECT_GET(r.payload, m.reported_date)::STRING),
                 TRY_TO_DATE(OBJECT_GET(r.payload, m.reported_date)::STRING, 'DD/MM/YYYY')),
        TRY_TO_DECIMAL(REGEXP_REPLACE(OBJECT_GET(r.payload, m.claim_amount)::STRING, '[^0-9.\\-]', ''), 18, 2),
        UPPER(TRIM(OBJECT_GET(r.payload, m.claim_status)::STRING)),
        OBJECT_GET(r.payload, m.loss_description)::STRING,
        DATEDIFF('day',
            TRY_TO_DATE(OBJECT_GET(r.payload, m.loss_date)::STRING),
            TRY_TO_DATE(OBJECT_GET(r.payload, m.reported_date)::STRING))
    FROM RAW.RAW_CLAIM_STREAM r
    JOIN RAW.RAW_HEADER_REGISTRY reg
      ON reg.header_signature = MD5(ARRAY_TO_STRING(ARRAY_SORT(OBJECT_KEYS(r.payload)), '|'))
    JOIN LATERAL (
        SELECT
            MAX(IFF(value::STRING = 'claim_number',     key, NULL)) AS claim_number,
            MAX(IFF(value::STRING = 'policy_number',    key, NULL)) AS policy_number,
            MAX(IFF(value::STRING = 'loss_date',        key, NULL)) AS loss_date,
            MAX(IFF(value::STRING = 'reported_date',    key, NULL)) AS reported_date,
            MAX(IFF(value::STRING = 'claim_amount',     key, NULL)) AS claim_amount,
            MAX(IFF(value::STRING = 'claim_status',     key, NULL)) AS claim_status,
            MAX(IFF(value::STRING = 'loss_description', key, NULL)) AS loss_description
        FROM LATERAL FLATTEN(input => reg.mapping)
    ) m
    WHERE r.processed_flag = FALSE AND reg.mapping IS NOT NULL;

    clm_rows := SQLROWCOUNT;

    -- 4. Mark processed + log
    UPDATE RAW.RAW_POLICY_STREAM SET processed_flag = TRUE WHERE processed_flag = FALSE;
    UPDATE RAW.RAW_CLAIM_STREAM  SET processed_flag = TRUE WHERE processed_flag = FALSE;

    INSERT INTO GOVERNANCE.PIPELINE_LOG (stage, rows_out, message, status)
    VALUES ('raw_to_staging', :pol_rows + :clm_rows,
            'policies=' || :pol_rows || ', claims=' || :clm_rows, 'SUCCESS');

    RETURN 'Staged ' || pol_rows || ' policies and ' || clm_rows || ' claims.';
END;
$$;

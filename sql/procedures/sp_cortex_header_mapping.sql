/* ════════════════════════════════════════════════════════════════════════
   sp_cortex_header_mapping
   --------------------------------------------------------------------------
   For each NEW header signature in RAW.RAW_HEADER_REGISTRY (mapping IS NULL),
   ask Cortex to map the broker's raw header names onto the canonical schema.
   The result is cached back into the registry so the LLM is invoked at most
   ONCE per distinct header layout — not once per row. Deterministic seed
   mappings from config/broker_mappings.yaml are loaded first (see
   sp_seed_header_mappings) and act as a safety net / few-shot ground truth.

   DELIVERABLE: "Cortex Header Mapping"
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA RAW;

CREATE OR REPLACE PROCEDURE SP_CORTEX_HEADER_MAPPING(MODEL STRING)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    resolved INTEGER DEFAULT 0;
    -- canonical targets the LLM is allowed to choose from
    canonical_policy STRING DEFAULT
        'policy_number, customer_name, product_name, premium_amount, sum_insured, effective_date, expiry_date, broker_agent';
    canonical_claim STRING DEFAULT
        'claim_number, policy_number, loss_date, reported_date, claim_amount, claim_status, loss_description';
BEGIN
    FOR rec IN (
        SELECT header_signature, broker_code, record_type, source_headers
        FROM RAW.RAW_HEADER_REGISTRY
        WHERE mapping IS NULL
    ) DO
        LET targets STRING := IFF(rec.record_type = 'claim', :canonical_claim, :canonical_policy);

        -- Ask Cortex for a strict JSON object: {source_header: canonical_field|null}
        LET prompt STRING :=
            'You standardize insurance broker files. Map each SOURCE HEADER to exactly one ' ||
            'CANONICAL FIELD, or null if none applies. Return ONLY a JSON object whose keys are ' ||
            'the source headers and whose values are the canonical field name or null.\n' ||
            'CANONICAL FIELDS: ' || :targets || '\n' ||
            'SOURCE HEADERS: ' || ARRAY_TO_STRING(rec.source_headers, ', ');

        LET raw_resp STRING := SNOWFLAKE.CORTEX.COMPLETE(:MODEL, :prompt);

        -- COMPLETE may wrap JSON in prose/fences; extract the first {...} block.
        LET json_txt STRING := REGEXP_SUBSTR(:raw_resp, '\\{[\\s\\S]*\\}');
        LET mapping_v VARIANT := TRY_PARSE_JSON(:json_txt);

        IF (mapping_v IS NOT NULL) THEN
            UPDATE RAW.RAW_HEADER_REGISTRY
               SET mapping        = :mapping_v,
                   mapping_source = 'cortex',
                   confidence     = 0.9,
                   last_seen_at   = CURRENT_TIMESTAMP()
             WHERE header_signature = rec.header_signature;
            resolved := resolved + 1;
        END IF;

        INSERT INTO GOVERNANCE.CORTEX_CALL_LOG (task, model, success)
        VALUES ('header_mapping', :MODEL, :mapping_v IS NOT NULL);
    END FOR;

    RETURN 'Resolved ' || resolved || ' new header signature(s) via Cortex.';
END;
$$;

/* ── Seed deterministic mappings (call before the Cortex pass) ──────────── */
CREATE OR REPLACE PROCEDURE SP_SEED_HEADER_MAPPING(
    BROKER_CODE STRING, RECORD_TYPE STRING, SOURCE_HEADERS ARRAY, MAPPING VARIANT
)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    MERGE INTO RAW.RAW_HEADER_REGISTRY t
    USING (SELECT MD5(ARRAY_TO_STRING(ARRAY_SORT(:SOURCE_HEADERS), '|')) AS sig) s
    ON t.header_signature = s.sig
    WHEN NOT MATCHED THEN INSERT
        (header_signature, broker_code, record_type, source_headers, mapping, mapping_source, confidence)
        VALUES (s.sig, :BROKER_CODE, :RECORD_TYPE, :SOURCE_HEADERS, :MAPPING, 'seed', 1.0);
    RETURN 'Seeded mapping for ' || :BROKER_CODE || '/' || :RECORD_TYPE;
END;
$$;

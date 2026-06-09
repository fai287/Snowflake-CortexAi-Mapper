/* ════════════════════════════════════════════════════════════════════════
   06 · Cortex helper UDFs
   --------------------------------------------------------------------------
   Thin, reusable wrappers around SNOWFLAKE.CORTEX.* so the rest of the
   codebase calls stable, intention-revealing functions instead of repeating
   prompt strings. Model names are parameterized via session variable
   $CORTEX_MODEL where useful.
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA SEMANTIC;

-- ── Generic completion (returns text) ───────────────────────────────────
CREATE OR REPLACE FUNCTION FN_CORTEX_COMPLETE(model STRING, prompt STRING)
RETURNS STRING
LANGUAGE SQL
AS
$$
    SNOWFLAKE.CORTEX.COMPLETE(model, prompt)
$$;

-- ── Completion forced to return strict JSON (header mapping, enrichment) ─
-- Uses COMPLETE's structured-output form with a response_format JSON schema.
CREATE OR REPLACE FUNCTION FN_CORTEX_COMPLETE_JSON(
    model STRING, prompt STRING, response_schema VARIANT
)
RETURNS VARIANT
LANGUAGE SQL
AS
$$
    SNOWFLAKE.CORTEX.COMPLETE(
        model,
        [ {'role': 'user', 'content': prompt} ],
        { 'temperature': 0,
          'response_format': { 'type': 'json', 'schema': response_schema } }
    ):choices[0]:messages
$$;

-- ── Product-line classification (zero-shot) ─────────────────────────────
CREATE OR REPLACE FUNCTION FN_CLASSIFY_PRODUCT(product_text STRING)
RETURNS STRING
LANGUAGE SQL
AS
$$
    SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
        COALESCE(product_text, 'unknown'),
        ['AUTO','HOME','LIFE','HEALTH','TRAVEL','COMMERCIAL','MARINE','OTHER']
    ):label::STRING
$$;

-- ── Narrative sentiment for claim descriptions (-1..1) ──────────────────
CREATE OR REPLACE FUNCTION FN_CLAIM_SENTIMENT(narrative STRING)
RETURNS FLOAT
LANGUAGE SQL
AS
$$
    CASE WHEN narrative IS NULL OR TRIM(narrative) = '' THEN NULL
         ELSE SNOWFLAKE.CORTEX.SENTIMENT(narrative) END
$$;

-- ── Plain-English explanation of a validation failure ───────────────────
CREATE OR REPLACE FUNCTION FN_EXPLAIN_FAILURE(
    model STRING, entity STRING, rule_desc STRING, record_json STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
    SNOWFLAKE.CORTEX.COMPLETE(
        model,
        'You are a data-quality analyst for an insurance company. In 1-2 plain ' ||
        'sentences, explain to a business user why this ' || entity ||
        ' record failed the validation rule: "' || rule_desc || '". ' ||
        'Be specific about the offending value. Record: ' || record_json ||
        '. Do not suggest code. Respond with the explanation only.'
    )
$$;

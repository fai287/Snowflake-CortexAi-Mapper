/* ════════════════════════════════════════════════════════════════════════
   05 · GOVERNANCE schema — data quality, audit, ingestion log
   --------------------------------------------------------------------------
   Dedicated audit tables for the configurable validation framework. Every
   rule evaluation is recorded (pass and fail) so the dashboard and the AI
   agent can report on data quality over time. The rule catalog mirrors
   config/data_quality_rules.yaml and is loaded by sp_load_dq_rules.
   ════════════════════════════════════════════════════════════════════════ */

USE DATABASE INSURANCE_PLATFORM;
USE SCHEMA GOVERNANCE;

-- ── Rule catalog (declarative; synced from YAML) ────────────────────────
CREATE TABLE IF NOT EXISTS DQ_RULE_CATALOG (
    rule_id           STRING        PRIMARY KEY,
    entity            STRING,                       -- policy | claim
    description       STRING,
    severity          STRING,                       -- ERROR | WARN | INFO
    rule_type         STRING        DEFAULT 'expression', -- expression|referential|anomaly
    expression        STRING,
    explain           BOOLEAN       DEFAULT TRUE,
    active            BOOLEAN       DEFAULT TRUE,
    updated_at        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Configurable validation rules (source of truth: data_quality_rules.yaml)';

-- ── Rule evaluation results (the audit trail) ───────────────────────────
CREATE TABLE IF NOT EXISTS DQ_RESULT (
    result_id         STRING        DEFAULT UUID_STRING(),
    batch_id          STRING,                       -- one per sp_run_data_quality run
    entity            STRING,
    stg_id            STRING,                       -- record evaluated
    broker_code       STRING,
    rule_id           STRING,
    severity          STRING,
    passed            BOOLEAN,
    observed_value    STRING,                       -- value(s) that triggered failure
    cortex_explanation STRING,                      -- NL reason (failures only, sampled)
    evaluated_at      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Per-record, per-rule validation outcomes (audit table)';

-- ── DQ batch run log ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS DQ_BATCH_LOG (
    batch_id          STRING        PRIMARY KEY,
    entity            STRING,
    records_evaluated INTEGER,
    rules_evaluated   INTEGER,
    error_failures    INTEGER,
    warn_failures     INTEGER,
    quarantined       INTEGER,
    started_at        TIMESTAMP_NTZ,
    finished_at       TIMESTAMP_NTZ,
    status            STRING                        -- RUNNING | SUCCESS | FAILED
)
COMMENT = 'High-level log of each data-quality batch run';

-- ── Pipeline / ingestion event log ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS PIPELINE_LOG (
    log_id            STRING        DEFAULT UUID_STRING(),
    stage             STRING,                       -- raw_to_staging | staging_to_analytics | dq | enrichment
    broker_code       STRING,
    rows_in           INTEGER,
    rows_out          INTEGER,
    rows_rejected     INTEGER,
    message           STRING,
    status            STRING,                       -- SUCCESS | WARN | ERROR
    logged_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Operational log for every pipeline stage execution';

-- ── Cortex call audit (cost + observability) ───────────────────────────
CREATE TABLE IF NOT EXISTS CORTEX_CALL_LOG (
    call_id           STRING        DEFAULT UUID_STRING(),
    task              STRING,                       -- header_mapping|classify|enrich|anomaly|explain|nl2sql
    model             STRING,
    input_tokens_est  INTEGER,
    output_tokens_est INTEGER,
    latency_ms        INTEGER,
    success           BOOLEAN,
    called_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Audit of Cortex LLM invocations for cost and observability';

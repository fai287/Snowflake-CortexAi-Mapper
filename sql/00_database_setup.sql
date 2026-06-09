/* ════════════════════════════════════════════════════════════════════════
   00 · Platform bootstrap
   Database, warehouse, role, schemas, and Cortex grants.
   Run as a role that can CREATE DATABASE / ROLE (e.g. SYSADMIN + SECURITYADMIN).
   ════════════════════════════════════════════════════════════════════════ */

-- ── Role ────────────────────────────────────────────────────────────────
USE ROLE SECURITYADMIN;
CREATE ROLE IF NOT EXISTS INSURANCE_ENGINEER;
GRANT ROLE INSURANCE_ENGINEER TO ROLE SYSADMIN;

USE ROLE SYSADMIN;

-- ── Warehouse ───────────────────────────────────────────────────────────
CREATE WAREHOUSE IF NOT EXISTS INSURANCE_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND   = 60
  AUTO_RESUME    = TRUE
  INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Compute for the AI-powered insurance data platform';

-- ── Database & schemas (medallion + governance) ─────────────────────────
CREATE DATABASE IF NOT EXISTS INSURANCE_PLATFORM
  COMMENT = 'AI-powered insurance data platform';

USE DATABASE INSURANCE_PLATFORM;

CREATE SCHEMA IF NOT EXISTS RAW        COMMENT = 'Landing zone: untyped broker payloads from Snowpipe Streaming';
CREATE SCHEMA IF NOT EXISTS STAGING    COMMENT = 'Standardized + Cortex-mapped records (canonical schema)';
CREATE SCHEMA IF NOT EXISTS ANALYTICS  COMMENT = 'Conformed dimensions and facts, enriched + scored';
CREATE SCHEMA IF NOT EXISTS SEMANTIC   COMMENT = 'Business-facing views and the Cortex Analyst semantic model';
CREATE SCHEMA IF NOT EXISTS GOVERNANCE COMMENT = 'Data-quality audit, ingestion log, rule catalog';

-- ── File formats (used by Kafka Connect / batch fallback loads) ─────────
CREATE FILE FORMAT IF NOT EXISTS RAW.FF_JSON
  TYPE = JSON STRIP_OUTER_ARRAY = TRUE COMMENT = 'Broker JSON payloads';

CREATE FILE FORMAT IF NOT EXISTS RAW.FF_CSV
  TYPE = CSV PARSE_HEADER = TRUE FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE COMMENT = 'Broker CSV payloads';

-- ── Grants ──────────────────────────────────────────────────────────────
GRANT USAGE ON WAREHOUSE INSURANCE_WH TO ROLE INSURANCE_ENGINEER;
GRANT OPERATE ON WAREHOUSE INSURANCE_WH TO ROLE INSURANCE_ENGINEER;
GRANT USAGE ON DATABASE INSURANCE_PLATFORM TO ROLE INSURANCE_ENGINEER;

GRANT ALL ON SCHEMA RAW        TO ROLE INSURANCE_ENGINEER;
GRANT ALL ON SCHEMA STAGING    TO ROLE INSURANCE_ENGINEER;
GRANT ALL ON SCHEMA ANALYTICS  TO ROLE INSURANCE_ENGINEER;
GRANT ALL ON SCHEMA SEMANTIC   TO ROLE INSURANCE_ENGINEER;
GRANT ALL ON SCHEMA GOVERNANCE TO ROLE INSURANCE_ENGINEER;

GRANT ALL ON FUTURE TABLES     IN DATABASE INSURANCE_PLATFORM TO ROLE INSURANCE_ENGINEER;
GRANT ALL ON FUTURE VIEWS      IN DATABASE INSURANCE_PLATFORM TO ROLE INSURANCE_ENGINEER;
GRANT ALL ON FUTURE PROCEDURES IN DATABASE INSURANCE_PLATFORM TO ROLE INSURANCE_ENGINEER;
GRANT ALL ON FUTURE FUNCTIONS  IN DATABASE INSURANCE_PLATFORM TO ROLE INSURANCE_ENGINEER;

-- Cortex access (account-level DB role). Required for COMPLETE / CLASSIFY_TEXT.
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE INSURANCE_ENGINEER;

-- A dedicated service user for Snowpipe Streaming uses key-pair auth:
--   ALTER USER INSURANCE_SVC SET RSA_PUBLIC_KEY='<base64 pubkey>';
--   GRANT ROLE INSURANCE_ENGINEER TO USER INSURANCE_SVC;

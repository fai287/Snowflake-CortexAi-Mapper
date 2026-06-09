# Snowflake Database Design

The **Snowflake Database Design** deliverable. Database `INSURANCE_PLATFORM`,
five schemas, and a conformed star schema in `ANALYTICS`.

## Schemas

| Schema | Objects | DDL |
|---|---|---|
| `RAW` | `RAW_POLICY_STREAM`, `RAW_CLAIM_STREAM`, `RAW_HEADER_REGISTRY`, `V_RAW_INGEST_FRESHNESS` | `sql/01_raw_schema.sql` |
| `STAGING` | `STG_POLICY`, `STG_CLAIM`, `STG_QUARANTINE` | `sql/02_staging_schema.sql` |
| `ANALYTICS` | `DIM_BROKER/CUSTOMER/PRODUCT/POLICY`, `FACT_PREMIUM`, `FACT_CLAIM` | `sql/03_analytics_schema.sql` |
| `SEMANTIC` | `POLICIES`, `CLAIMS`, `BROKER_PERFORMANCE`, `INGESTION_HEALTH`, `VALIDATION_SUMMARY` + Cortex UDFs | `sql/04_semantic_schema.sql`, `sql/06_cortex_functions.sql` |
| `GOVERNANCE` | `DQ_RULE_CATALOG`, `DQ_RESULT`, `DQ_BATCH_LOG`, `PIPELINE_LOG`, `CORTEX_CALL_LOG` | `sql/05_governance_schema.sql` |

## Canonical (semantic) entities

All broker formats are standardized into three entities — see
`config/canonical_schema.yaml`.

### Customer
`customer_id` (hash of normalized name) · `customer_name` · `customer_segment`
(Cortex) · `risk_tier` (Cortex).

### Policy
`policy_number` · `customer` · `product_line` (Cortex `CLASSIFY_TEXT`) ·
`premium_amount` · `sum_insured` · `effective_date` · `expiry_date` ·
`broker` · `anomaly_score` / `anomaly_reason`.

### Claim
`claim_number` · `policy_number` · `loss_date` · `reported_date` ·
`reporting_lag_days` · `claim_amount` · `claim_status` · `loss_description` ·
`sentiment_score` (Cortex `SENTIMENT`) · `anomaly_score` / `anomaly_reason`.

## Star schema

See `docs/diagrams/star_schema.mmd`. `FACT_PREMIUM` and `FACT_CLAIM` join to the
conformed dimensions `DIM_BROKER`, `DIM_CUSTOMER`, `DIM_PRODUCT`, `DIM_POLICY`.

## Lineage

```
Kafka msg → RAW.raw_id → STAGING.stg_id (raw_id FK) → ANALYTICS.*_key → SEMANTIC view
```

Every promotion is idempotent (`MERGE` on business keys) and logged to
`GOVERNANCE.PIPELINE_LOG`, so the pipeline can be re-run safely.

## Data types & standardization

- Amounts: `NUMBER(18,2)`, stripped of currency symbols/commas via
  `REGEXP_REPLACE` + `TRY_TO_DECIMAL`.
- Dates: `TRY_TO_DATE` across the formats in `config/broker_mappings.yaml`
  (`%Y-%m-%d`, `%d/%m/%Y`, …).
- Codes: `claim_status`, `product_line` upper-cased and constrained to the
  controlled vocabularies in `config/canonical_schema.yaml`.
- Original payloads are preserved verbatim in `RAW.*.payload` (`VARIANT`).

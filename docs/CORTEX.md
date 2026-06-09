# Snowflake Cortex usage

How the platform applies LLM/AI functions, the prompts, and the cost controls.

## Functions used

| Cortex function | Used for | Location |
|---|---|---|
| `COMPLETE` | header mapping, customer enrichment, anomaly review, failure explanation, NL→SQL, answer summarization | `sp_cortex_header_mapping`, `sp_cortex_enrichment`, `sp_anomaly_detection`, `sp_run_data_quality`, `chatbot/agent.py` |
| `CLASSIFY_TEXT` | product-line classification | `FN_CLASSIFY_PRODUCT` |
| `SENTIMENT` | claim-narrative sentiment | `FN_CLAIM_SENTIMENT` |

## Prompt templates

`cortex/prompts/` holds the canonical prompt text (the in-DB procedures inline a
compact form of these):

- `header_mapping.txt` — strict-JSON header → canonical mapping
- `product_classification.txt` — zero-shot product line
- `anomaly_review.txt` — underwriter-facing outlier assessment
- `validation_explanation.txt` — plain-English DQ failure reason
- `nl2sql_system.txt` — NL→SQL system prompt bound to the semantic layer

## Design choices

**In-database first.** Row-level Cortex runs inside Snowflake (`SNOWFLAKE.CORTEX.*`)
— no data leaves the account and there's no per-row Python round-trip. The
Python client (`cortex/cortex_client.py`) is used only for the interactive
agent.

**Map once, not per row.** Header mapping is keyed by a *header signature*
(`MD5` of the sorted source keys). Cortex is invoked once per *distinct layout*
and the result is cached in `RAW.RAW_HEADER_REGISTRY`. A new broker or a drifted
file triggers exactly one LLM call.

**Deterministic safety nets.** Known brokers are seeded with exact mappings
(`scripts/seed_header_mappings.py`); structured outputs are parsed with
`TRY_PARSE_JSON` + `REGEXP_SUBSTR('\\{...\\}')` so malformed LLM output never
breaks the pipeline. Generated SQL passes hard guardrails before it runs.

**Cost control.** DQ failure explanations are sampled (`defaults.sample_explanations`,
default 50/batch). Customer enrichment is one call per *distinct* customer.
Every call is logged to `GOVERNANCE.CORTEX_CALL_LOG`.

## Swapping models

`CORTEX_MODEL` (default `claude-3-5-sonnet`) drives `COMPLETE`; `CORTEX_CLASSIFY_MODEL`
can point high-volume classification at a cheaper model. Procedures take the
model as a parameter, so you can A/B different models per stage.

## Example: header mapping call (conceptual)

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE(
  'claude-3-5-sonnet',
  'You standardize insurance broker files. Map each SOURCE HEADER to exactly '
  || 'one CANONICAL FIELD or null. Return ONLY JSON. '
  || 'CANONICAL FIELDS: policy_number, customer_name, premium_amount, ... '
  || 'SOURCE HEADERS: POL_ID, CLIENT, LOB, PREM_AMT, EFF_DT, EXP_DT, TSI, BRKR'
);
-- → {"POL_ID":"policy_number","CLIENT":"customer_name","LOB":"product_name",
--    "PREM_AMT":"premium_amount","EFF_DT":"effective_date", ...}
```

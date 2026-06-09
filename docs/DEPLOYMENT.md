# Deployment Guide

End-to-end setup: Snowflake objects, Kafka, ingestion, pipeline, and the
dashboard. Two modes:

- **Demo mode** — dashboard only, synthetic data, no Snowflake (fastest look).
- **Full mode** — live Kafka → Snowpipe Streaming → Snowflake → Cortex.

---

## 0. Prerequisites

| Requirement | Notes |
|---|---|
| Snowflake account | Region with **Cortex** (`COMPLETE`, `CLASSIFY_TEXT`, `SENTIMENT`) |
| Role privileges | `SYSADMIN` + `SECURITYADMIN` for the one-time `00_database_setup.sql` |
| Python 3.10+ | `pip install -r requirements.txt` |
| Docker | For local Kafka (`docker-compose.yml`) |
| SnowSQL | For `scripts/deploy_snowflake.sh` (or run the SQL via the web UI) |
| Key pair | Snowpipe Streaming requires key-pair auth |

---

## 1. Demo mode (60 seconds)

```bash
python -m venv .venv && source .venv/bin/activate
pip install streamlit plotly pandas numpy
DEMO_MODE=1 streamlit run dashboard/app.py
```

Open http://localhost:8501 — every page renders on synthetic data. The AI
Assistant explains that it needs a live connection (the rest is fully usable).

---

## 2. Full mode

### 2.1 Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill Snowflake + Kafka values
```

### 2.2 Generate a key pair (Snowpipe Streaming)
```bash
mkdir -p secrets
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -nocrypt -out secrets/rsa_key.p8
openssl rsa -in secrets/rsa_key.p8 -pubout -out secrets/rsa_key.pub
# register the public key (strip header/footer + newlines):
#   ALTER USER INSURANCE_SVC SET RSA_PUBLIC_KEY='MIIBIjANBgkq...';
```
Point `SNOWFLAKE_PRIVATE_KEY_PATH=./secrets/rsa_key.p8` in `.env`.

### 2.3 Provision Snowflake
```bash
SNOWSQL_CONN=my_conn ./scripts/deploy_snowflake.sh
```
This runs all DDL, creates the stored procedures, then syncs the DQ rules and
seeds the broker header mappings. Finally, enable the scheduled micro-batch:
```sql
ALTER TASK INSURANCE_PLATFORM.GOVERNANCE.TASK_RUN_PIPELINE RESUME;
```

> Prefer manual control? Skip the task and call
> `CALL GOVERNANCE.SP_RUN_PIPELINE('claude-3-5-sonnet');` on demand (the
> dashboard can trigger this too).

### 2.4 Start Kafka + topics
```bash
docker compose up -d            # broker + Zookeeper + UI on :8080
make topics                     # create insurance.policies.raw / claims.raw / dlq
```

### 2.5 Produce broker traffic
```bash
python kafka/producers/broker_simulator.py --rate 5    # 5 msg/s/stream, all brokers
```

### 2.6 Stream into Snowflake
```bash
python ingestion/snowpipe_streaming.py                 # auto-selects backend
# or the managed path: deploy ingestion/kafka_connect_snowpipe.json to Kafka Connect
```
Within ~2 minutes the scheduled task standardizes, validates, enriches, and
promotes the data.

### 2.7 Dashboard + AI agent
```bash
streamlit run dashboard/app.py
# CLI agent:  python chatbot/agent.py
```

---

## 3. Verify

```sql
-- rows landing in RAW
SELECT * FROM SEMANTIC.INGESTION_HEALTH ORDER BY seconds_since_last;

-- pipeline activity
SELECT * FROM GOVERNANCE.PIPELINE_LOG ORDER BY logged_at DESC LIMIT 20;

-- validation outcomes (with Cortex explanations)
SELECT rule_id, severity, cortex_explanation
FROM   GOVERNANCE.DQ_RESULT
WHERE  passed = FALSE AND cortex_explanation IS NOT NULL
LIMIT  20;

-- business data
SELECT product_line, SUM(premium_amount) FROM SEMANTIC.POLICIES GROUP BY 1;
```

---

## 4. Operations

| Task | How |
|---|---|
| Pause/resume pipeline | `ALTER TASK …TASK_RUN_PIPELINE SUSPEND|RESUME;` |
| Change a DQ rule | edit `config/data_quality_rules.yaml` → `python scripts/sync_dq_rules.py` |
| Add a broker | add to `config/broker_mappings.yaml` → `python scripts/seed_header_mappings.py` (unknown layouts are auto-mapped by Cortex anyway) |
| Swap Cortex model | set `CORTEX_MODEL` in `.env` / pass to `SP_RUN_PIPELINE` |
| Inspect Cortex cost | `SELECT * FROM GOVERNANCE.CORTEX_CALL_LOG` |
| Run tests | `pytest -q` |

---

## 5. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Dashboard shows "demo mode" banner unexpectedly | `.env` missing/incorrect, or Snowflake unreachable — check `st.session_state['_db_error']` |
| `Streaming SDK unavailable … falling back to CONNECTOR` | expected if the Streaming SDK/JVM isn't installed; connector backend is fine for dev |
| No rows in STAGING | header signature not yet mapped — confirm `RAW.RAW_HEADER_REGISTRY.mapping` is populated (seed + Cortex) |
| Cortex errors | account/region lacks Cortex, or role missing `SNOWFLAKE.CORTEX_USER` |
| Claims not joining to policies | claim references a `policy_number` not yet in `DIM_POLICY` (rule `CLM_008`) — produce policies first |

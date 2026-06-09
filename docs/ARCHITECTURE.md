# Architecture

This document is the **Architecture Diagram** deliverable: the end-to-end data
flow, the layered Snowflake design, and the responsibilities of each component.

---

## 1. System overview

```mermaid
flowchart LR
    subgraph Brokers
      A[Broker Alpha\nCSV] 
      B[Broker Beta\nJSON]
      C[Broker Gamma\nPipe-delimited]
    end

    A & B & C -->|native formats| K{{Apache Kafka}}
    K -->|policies.raw| SS[Snowpipe Streaming\ningest client]
    K -->|claims.raw| SS

    SS -->|append rows| RAW[(RAW schema\nVARIANT payloads)]

    RAW -->|sp_raw_to_staging\n+ Cortex header mapping| STG[(STAGING\ncanonical + typed)]
    STG -->|sp_run_data_quality| GOV[(GOVERNANCE\nDQ audit / logs)]
    STG -->|sp_cortex_enrichment\nclassify + segment + sentiment| STG
    STG -->|sp_staging_to_analytics| AN[(ANALYTICS\nstar schema)]
    AN -->|sp_anomaly_detection\nz-score + Cortex review| AN
    AN --> SEM[(SEMANTIC\nbusiness views)]

    SEM --> DASH[Streamlit Dashboard]
    SEM --> AGENT[Conversational AI Agent\nNL → SQL]
    GOV --> DASH

    classDef store fill:#1f6feb,color:#fff,stroke:#0d419d;
    class RAW,STG,AN,SEM,GOV store;
```

---

## 2. Layered (medallion) design

| Schema | Grain / shape | Populated by | Purpose |
|---|---|---|---|
| **RAW** | 1 row per Kafka message, original payload in `VARIANT` | Snowpipe Streaming | Lossless landing zone; nothing is parsed or rejected here |
| **STAGING** | Canonical, typed, broker-agnostic rows | `sp_raw_to_staging` (+ Cortex header mapping) | One shape for all brokers; the layer DQ runs against |
| **ANALYTICS** | Conformed star schema (dims + facts) | `sp_staging_to_analytics` | Query-optimized, enriched, anomaly-scored |
| **SEMANTIC** | Business-named views | DDL views over ANALYTICS + GOVERNANCE | The only surface the dashboard + AI agent touch |
| **GOVERNANCE** | Audit / log tables | DQ engine, pipeline procs | Validation outcomes, ingestion + Cortex audit |

Why a `GOVERNANCE` schema in addition to the four medallion schemas? The brief
calls for **dedicated audit tables**. Keeping DQ results, pipeline logs, and the
rule catalog in their own schema cleanly separates *governance* metadata from
*business* data while leaving `RAW/STAGING/ANALYTICS/SEMANTIC` as the data path.

---

## 3. Real-time ingestion path

```mermaid
sequenceDiagram
    participant Brk as Broker (producer)
    participant K as Kafka topic
    participant SS as Snowpipe Streaming client
    participant RAW as RAW.RAW_*_STREAM
    participant T as Task: sp_run_pipeline

    Brk->>K: produce(envelope{broker_code, format, payload})
    SS->>K: poll(batch)
    SS->>RAW: open channel + insert_row(...)  (sub-second)
    Note over SS,RAW: commit offset only after Snowflake ack
    loop every 2 min
        T->>RAW: read unprocessed rows
        T->>T: map → validate → enrich → promote → score
    end
```

Two ingestion backends share one interface (`ingestion/snowpipe_streaming.py`):

1. **Streaming SDK** — production; rows pushed through an open channel.
2. **Connector micro-batch** — local-dev fallback; frequent `INSERT … PARSE_JSON`.

In production the **Snowflake Kafka Connector in Snowpipe Streaming mode**
(`ingestion/kafka_connect_snowpipe.json`) is the recommended managed option.

---

## 4. AI / Cortex touchpoints

```mermaid
flowchart TD
    H[New broker header layout] -->|COMPLETE JSON| M[Canonical mapping cached\nin RAW_HEADER_REGISTRY]
    P[Raw product text] -->|CLASSIFY_TEXT| PL[product_line]
    Cu[Customer + policy context] -->|COMPLETE JSON| Seg[segment + risk_tier]
    N[Claim narrative] -->|SENTIMENT| Se[sentiment_score]
    V[Failed DQ record] -->|COMPLETE| Ex[Plain-English explanation]
    Z[z-score outliers] -->|COMPLETE| Ar[anomaly_reason]
    Q[User question] -->|COMPLETE + semantic model| SQL[Safe SELECT → answer]
```

Cortex runs **in-database** for row-level work (cheaper, no egress) and from
**Python** only for the interactive agent. Every call is audited in
`GOVERNANCE.CORTEX_CALL_LOG`.

---

## 5. Component map

| Deliverable | Primary artifact(s) |
|---|---|
| Architecture Diagram | this file + `docs/diagrams/*.mmd` |
| Snowflake Database Design | `sql/00`–`sql/06`, `docs/DATA_MODEL.md` |
| Kafka Setup | `docker-compose.yml`, `kafka/producers/*`, `scripts/create_topics.sh` |
| Snowpipe Streaming Integration | `ingestion/snowpipe_streaming.py`, `ingestion/kafka_connect_snowpipe.json` |
| Cortex Header Mapping | `sql/procedures/sp_cortex_header_mapping.sql`, `cortex/prompts/header_mapping.txt` |
| Validation Framework | `config/data_quality_rules.yaml`, `sql/procedures/sp_run_data_quality.sql`, `sql/05_governance_schema.sql` |
| Semantic Layer | `sql/04_semantic_schema.sql`, `sql/semantic/insurance_semantic_model.yaml` |
| AI Agent | `chatbot/agent.py`, `chatbot/guardrails.py` |
| Streamlit Dashboard | `dashboard/app.py`, `dashboard/pages/*` |
| Deployment Guide | `docs/DEPLOYMENT.md`, `scripts/deploy_snowflake.sh` |

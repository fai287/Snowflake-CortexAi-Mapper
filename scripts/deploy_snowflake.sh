#!/usr/bin/env bash
# Provision every Snowflake object in dependency order using SnowSQL.
#
# Prereqs:
#   • SnowSQL installed and a named connection OR env vars set.
#   • Run sql files as a role that can create DB/role/warehouse for 00_*,
#     then INSURANCE_ENGINEER for the rest.
#
# Usage:
#   SNOWSQL_CONN=my_conn ./scripts/deploy_snowflake.sh
#   # or rely on ~/.snowsql/config default connection
set -euo pipefail

CONN_ARG=""
if [[ -n "${SNOWSQL_CONN:-}" ]]; then
  CONN_ARG="-c ${SNOWSQL_CONN}"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run() {
  echo "──▶ $1"
  snowsql ${CONN_ARG} -f "$1"
}

echo "== Schemas & infrastructure =="
run "$ROOT/sql/00_database_setup.sql"
run "$ROOT/sql/01_raw_schema.sql"
run "$ROOT/sql/02_staging_schema.sql"
run "$ROOT/sql/03_analytics_schema.sql"
run "$ROOT/sql/05_governance_schema.sql"
run "$ROOT/sql/06_cortex_functions.sql"
run "$ROOT/sql/04_semantic_schema.sql"        # views depend on analytics + governance

echo "== Stored procedures =="
run "$ROOT/sql/procedures/sp_cortex_header_mapping.sql"
run "$ROOT/sql/procedures/sp_raw_to_staging.sql"
run "$ROOT/sql/procedures/sp_run_data_quality.sql"
run "$ROOT/sql/procedures/sp_cortex_enrichment.sql"
run "$ROOT/sql/procedures/sp_staging_to_analytics.sql"
run "$ROOT/sql/procedures/sp_anomaly_detection.sql"
run "$ROOT/sql/procedures/sp_run_pipeline.sql"

echo "== Sync config-driven artifacts =="
python "$ROOT/scripts/sync_dq_rules.py"
python "$ROOT/scripts/seed_header_mappings.py"

echo "✅ Snowflake deployment complete."
echo "   Enable the scheduled pipeline with:"
echo "     ALTER TASK INSURANCE_PLATFORM.GOVERNANCE.TASK_RUN_PIPELINE RESUME;"

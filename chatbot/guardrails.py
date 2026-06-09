"""SQL safety guardrails for the conversational agent.

The NL→SQL model is constrained by prompt, but we never trust generated SQL.
This module enforces hard, deterministic rules before execution:
  • single statement only
  • SELECT (or WITH … SELECT) only — no DML/DDL/CALL
  • references only the SEMANTIC schema's whitelisted views
  • forces a LIMIT on non-aggregate queries
"""
from __future__ import annotations

import re

ALLOWED_OBJECTS = {
    "SEMANTIC.POLICIES",
    "SEMANTIC.CLAIMS",
    "SEMANTIC.BROKER_PERFORMANCE",
    "SEMANTIC.INGESTION_HEALTH",
    "SEMANTIC.VALIDATION_SUMMARY",
}

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|"
    r"CALL|COPY|PUT|GET|EXECUTE|USE)\b",
    re.IGNORECASE,
)
# any schema-qualified identifier
QUALIFIED = re.compile(r"\b([A-Z_][A-Z0-9_]*)\.([A-Z_][A-Z0-9_]*)\b", re.IGNORECASE)


class GuardrailError(Exception):
    pass


def sanitize(sql: str) -> str:
    """Validate generated SQL; return a safe, executable statement or raise."""
    sql = sql.strip().rstrip(";").strip()

    if sql.upper().startswith("-- CANNOT_ANSWER"):
        raise GuardrailError(sql)

    if ";" in sql:
        raise GuardrailError("Multiple statements are not allowed.")

    head = sql.lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise GuardrailError("Only SELECT/WITH queries are permitted.")

    if FORBIDDEN.search(sql):
        raise GuardrailError("Query contains a forbidden keyword.")

    # Every schema-qualified object must be in the whitelist.
    for schema, obj in QUALIFIED.findall(sql):
        ref = f"{schema.upper()}.{obj.upper()}"
        # allow function namespaces like SNOWFLAKE.CORTEX? Not needed for reads.
        if schema.upper() in {"SEMANTIC"} and ref not in ALLOWED_OBJECTS:
            raise GuardrailError(f"Object {ref} is not allowed.")
        if schema.upper() in {"RAW", "STAGING", "ANALYTICS", "GOVERNANCE", "INFORMATION_SCHEMA"}:
            raise GuardrailError(f"Schema {schema} is not queryable by the agent.")

    # Force a LIMIT on non-aggregate row queries to protect the warehouse.
    if not re.search(r"\b(GROUP\s+BY|COUNT|SUM|AVG|MIN|MAX)\b", sql, re.IGNORECASE):
        if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
            sql += "\nLIMIT 100"

    return sql

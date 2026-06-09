"""Python-side Cortex client.

Most Cortex usage in this platform happens IN-DATABASE (the stored procedures
call SNOWFLAKE.CORTEX.* directly, which is cheaper and avoids data egress).
This module is the thin Python wrapper used by the chatbot and any ad-hoc
tooling: it runs `SELECT SNOWFLAKE.CORTEX.COMPLETE(...)` over a connection and
loads prompt templates from cortex/prompts/.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config.settings import settings  # noqa: E402
from src.common.snowflake_client import run_query  # noqa: E402

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(name: str, **kwargs) -> str:
    """Load a prompt template and fill {placeholders}."""
    text = (PROMPT_DIR / name).read_text(encoding="utf-8")
    return text.format(**kwargs) if kwargs else text


def _escape(s: str) -> str:
    return s.replace("'", "''")


def complete(prompt: str, model: str | None = None) -> str:
    """Run Cortex COMPLETE and return the text response."""
    model = model or settings.cortex.model
    sql = "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response"
    t0 = time.monotonic()
    df = run_query(sql, {"1": model, "2": prompt}) if False else _complete_positional(sql, model, prompt)
    _ = time.monotonic() - t0
    return df


def _complete_positional(sql: str, model: str, prompt: str) -> str:
    # snowflake-connector binds positional params via qmark/format; use literals
    # safely escaped to keep this dependency-light.
    literal_sql = (
        "SELECT SNOWFLAKE.CORTEX.COMPLETE('"
        + _escape(model) + "', '" + _escape(prompt) + "') AS response"
    )
    df = run_query(literal_sql)
    return str(df.iloc[0]["RESPONSE"]) if not df.empty else ""


def classify(text: str, labels: list[str]) -> str:
    """Run Cortex CLASSIFY_TEXT and return the chosen label."""
    labels_sql = "[" + ", ".join("'" + _escape(l) + "'" for l in labels) + "]"
    sql = (
        "SELECT SNOWFLAKE.CORTEX.CLASSIFY_TEXT('"
        + _escape(text) + "', " + labels_sql + "):label::STRING AS label"
    )
    df = run_query(sql)
    return str(df.iloc[0]["LABEL"]) if not df.empty else "OTHER"


def sentiment(text: str) -> float:
    sql = "SELECT SNOWFLAKE.CORTEX.SENTIMENT('" + _escape(text) + "') AS s"
    df = run_query(sql)
    return float(df.iloc[0]["S"]) if not df.empty else 0.0

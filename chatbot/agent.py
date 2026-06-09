"""Conversational AI agent for the insurance platform.

Pipeline for each user question:
  1. NL → SQL     – Cortex COMPLETE with the semantic-layer system prompt.
  2. Guardrails   – deterministic validation (chatbot/guardrails.py).
  3. Execute      – run the safe SELECT against the SEMANTIC views.
  4. Summarize    – Cortex turns the result rows into a business-friendly answer.

Returns an AgentResponse with the generated SQL, the raw rows, and the prose
answer so the Streamlit UI can show all three (transparency builds trust).

DELIVERABLE: "AI Agent"
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from chatbot.guardrails import GuardrailError, sanitize  # noqa: E402
from config.settings import settings  # noqa: E402
from cortex.cortex_client import complete, load_prompt  # noqa: E402
from src.common.snowflake_client import run_query  # noqa: E402


@dataclass
class AgentResponse:
    question: str
    sql: str | None = None
    answer: str = ""
    data: pd.DataFrame = field(default_factory=pd.DataFrame)
    error: str | None = None


SUMMARY_PROMPT = (
    "You are an insurance analytics assistant. Answer the user's question in "
    "2-4 sentences using ONLY the query result below. Use plain business "
    "language, include the key numbers, and never invent data. If the result "
    "is empty, say no matching records were found.\n\n"
    "QUESTION: {question}\n\nRESULT (CSV):\n{result_csv}\n\nANSWER:"
)


def generate_sql(question: str, model: str | None = None) -> str:
    prompt = load_prompt("nl2sql_system.txt", question=question)
    raw = complete(prompt, model=model or settings.cortex.model)
    # strip accidental markdown fences
    return raw.replace("```sql", "").replace("```", "").strip()


def summarize(question: str, df: pd.DataFrame, model: str | None = None) -> str:
    csv = df.head(50).to_csv(index=False) if not df.empty else "(no rows)"
    prompt = SUMMARY_PROMPT.format(question=question, result_csv=csv)
    return complete(prompt, model=model or settings.cortex.model).strip()


def ask(question: str, model: str | None = None) -> AgentResponse:
    """Full NL → SQL → answer round trip with guardrails."""
    resp = AgentResponse(question=question)
    try:
        candidate = generate_sql(question, model)
        resp.sql = candidate
        safe_sql = sanitize(candidate)
        resp.sql = safe_sql
        resp.data = run_query(safe_sql)
        resp.answer = summarize(question, resp.data, model)
    except GuardrailError as ge:
        msg = str(ge)
        if msg.upper().startswith("-- CANNOT_ANSWER"):
            resp.answer = (
                "I can only answer questions about policies, claims, brokers, "
                "ingestion health and validation results. "
                + msg.split(":", 1)[-1].strip()
            )
        else:
            resp.error = f"Query blocked by guardrails: {msg}"
            resp.answer = "I couldn't run that safely. Try rephrasing your question."
    except Exception as exc:  # network / SQL error
        resp.error = str(exc)
        resp.answer = "Something went wrong running that question."
    return resp


def _repl() -> None:
    print("Insurance AI agent — ask a question (Ctrl-C to quit)\n")
    try:
        while True:
            q = input("you> ").strip()
            if not q:
                continue
            r = ask(q)
            if r.sql:
                print(f"\n[sql] {r.sql}\n")
            print(f"bot> {r.answer}\n")
    except (KeyboardInterrupt, EOFError):
        print("\nbye")


if __name__ == "__main__":
    _repl()

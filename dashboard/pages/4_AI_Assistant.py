"""Conversational AI assistant — natural language over the semantic layer.

Wraps chatbot.agent.ask() in a chat UI. Shows the generated SQL and the result
table alongside the business-friendly answer for full transparency. In demo
mode (no Snowflake), it explains that live Cortex calls require a connection.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))
from dashboard.utils import data  # noqa: E402

st.set_page_config(page_title="AI Assistant", page_icon="💬", layout="wide")
st.title("💬 Insurance AI Assistant")
st.caption("Ask about policies, claims, brokers, ingestion health, or validation results")

EXAMPLES = [
    "What is the total premium revenue by product line?",
    "Which brokers have the highest loss ratio?",
    "How many claims are still open?",
    "Which brokers have stale ingestion?",
    "What are the most common validation errors?",
    "Show the 5 largest policies by premium.",
]

with st.sidebar:
    st.subheader("Try an example")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True):
            st.session_state["pending_q"] = ex

if "history" not in st.session_state:
    st.session_state["history"] = []

# Replay history
for turn in st.session_state["history"]:
    with st.chat_message("user"):
        st.write(turn["q"])
    with st.chat_message("assistant"):
        st.write(turn["answer"])
        if turn.get("sql"):
            with st.expander("View generated SQL"):
                st.code(turn["sql"], language="sql")
        if turn.get("rows") is not None and not turn["rows"].empty:
            st.dataframe(turn["rows"], use_container_width=True, hide_index=True)

prompt = st.chat_input("Ask a question…") or st.session_state.pop("pending_q", None)

if prompt:
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        if data.is_demo():
            from dashboard.utils.demo_agent import answer as demo_answer
            st.caption("🧪 Offline demo agent (keyword routing over the sample dataset). "
                       "The full Cortex NL→SQL agent runs automatically when a live "
                       "Snowflake connection is configured.")
            res = demo_answer(prompt)
            st.markdown(res.answer)
            if res.sql:
                with st.expander("View equivalent SQL"):
                    st.code(res.sql, language="sql")
            if not res.table.empty:
                st.dataframe(res.table, use_container_width=True, hide_index=True)
            st.session_state["history"].append(
                {"q": prompt, "answer": res.answer, "sql": res.sql or None,
                 "rows": res.table if not res.table.empty else None})
        else:
            from chatbot.agent import ask  # imported lazily to avoid connection at load
            with st.spinner("Thinking…"):
                resp = ask(prompt)
            st.write(resp.answer)
            if resp.sql:
                with st.expander("View generated SQL"):
                    st.code(resp.sql, language="sql")
            if not resp.data.empty:
                st.dataframe(resp.data, use_container_width=True, hide_index=True)
            if resp.error:
                st.caption(f"⚠️ {resp.error}")
            st.session_state["history"].append(
                {"q": prompt, "answer": resp.answer, "sql": resp.sql, "rows": resp.data})

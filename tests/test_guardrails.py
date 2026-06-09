"""Guardrail tests — the agent must never run unsafe or off-limits SQL."""
import pytest

from chatbot.guardrails import GuardrailError, sanitize


def test_allows_simple_select():
    sql = "SELECT product_line, SUM(premium_amount) FROM SEMANTIC.POLICIES GROUP BY product_line"
    assert "SEMANTIC.POLICIES" in sanitize(sql)


def test_adds_limit_to_row_query():
    out = sanitize("SELECT policy_number FROM SEMANTIC.POLICIES")
    assert "LIMIT 100" in out.upper()


def test_no_limit_forced_on_aggregate():
    out = sanitize("SELECT COUNT(*) FROM SEMANTIC.CLAIMS")
    assert "LIMIT" not in out.upper()


@pytest.mark.parametrize("bad", [
    "DELETE FROM SEMANTIC.POLICIES",
    "UPDATE SEMANTIC.POLICIES SET premium_amount = 0",
    "DROP TABLE SEMANTIC.POLICIES",
    "CALL GOVERNANCE.SP_RUN_PIPELINE('x')",
    "SELECT * FROM RAW.RAW_POLICY_STREAM",
    "SELECT * FROM ANALYTICS.DIM_POLICY",
    "SELECT * FROM GOVERNANCE.DQ_RESULT",
])
def test_blocks_unsafe_or_offlimits(bad):
    with pytest.raises(GuardrailError):
        sanitize(bad)


def test_blocks_multiple_statements():
    with pytest.raises(GuardrailError):
        sanitize("SELECT 1 FROM SEMANTIC.POLICIES; SELECT 2 FROM SEMANTIC.CLAIMS")


def test_passes_through_cannot_answer():
    with pytest.raises(GuardrailError):
        sanitize("-- CANNOT_ANSWER: outside scope")

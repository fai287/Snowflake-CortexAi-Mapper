"""Snowflake connection helpers.

Provides two auth paths:
  • password / connector  – read paths (dashboard, chatbot)
  • key-pair / private key – required by Snowpipe Streaming + service jobs

Usage:
    from src.common.snowflake_client import get_connection, run_query
    df = run_query("SELECT * FROM SEMANTIC.POLICIES LIMIT 10")
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

sys.path.append(str(Path(__file__).resolve().parents[2]))
from config.settings import settings  # noqa: E402


def _load_private_key() -> bytes | None:
    """Load and DER-encode the PKCS#8 private key for key-pair auth."""
    path = settings.snowflake.private_key_path
    if not path or not Path(path).exists():
        return None
    passphrase = settings.snowflake.private_key_passphrase
    with open(path, "rb") as fh:
        p_key = serialization.load_pem_private_key(
            fh.read(),
            password=passphrase.encode() if passphrase else None,
            backend=default_backend(),
        )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_connection(prefer_keypair: bool = False) -> snowflake.connector.SnowflakeConnection:
    """Open a Snowflake connection. Falls back from key-pair to password."""
    sf = settings.snowflake
    kwargs = dict(
        account=sf.account,
        user=sf.user,
        role=sf.role,
        warehouse=sf.warehouse,
        database=sf.database,
        client_session_keep_alive=True,
    )

    pk = _load_private_key() if (prefer_keypair or not sf.password) else None
    if pk is not None:
        kwargs["private_key"] = pk
    elif sf.password:
        kwargs["password"] = sf.password
    else:
        raise RuntimeError(
            "No Snowflake credentials available. Set SNOWFLAKE_PASSWORD or "
            "SNOWFLAKE_PRIVATE_KEY_PATH in your .env."
        )
    return snowflake.connector.connect(**kwargs)


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a query and return a DataFrame (read path)."""
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params or {})
            return cur.fetch_pandas_all()
        finally:
            cur.close()


def execute(sql: str, params: dict | None = None) -> None:
    """Execute a statement that returns no rows (DDL/DML, CALL)."""
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params or {})
        finally:
            cur.close()

"""Central, typed configuration for the platform.

Loads from environment variables (.env) and exposes a single `settings`
object plus helpers to read the YAML config files. Imported by the Kafka
producers, the Snowpipe Streaming client, the chatbot, and Streamlit.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

CONFIG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CONFIG_DIR.parent


class SnowflakeSettings(BaseModel):
    account: str = Field(default_factory=lambda: os.getenv("SNOWFLAKE_ACCOUNT", ""))
    user: str = Field(default_factory=lambda: os.getenv("SNOWFLAKE_USER", ""))
    role: str = Field(default_factory=lambda: os.getenv("SNOWFLAKE_ROLE", "INSURANCE_ENGINEER"))
    warehouse: str = Field(default_factory=lambda: os.getenv("SNOWFLAKE_WAREHOUSE", "INSURANCE_WH"))
    database: str = Field(default_factory=lambda: os.getenv("SNOWFLAKE_DATABASE", "INSURANCE_PLATFORM"))
    password: str | None = Field(default_factory=lambda: os.getenv("SNOWFLAKE_PASSWORD"))
    private_key_path: str | None = Field(default_factory=lambda: os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH"))
    private_key_passphrase: str | None = Field(
        default_factory=lambda: os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    )


class KafkaSettings(BaseModel):
    bootstrap_servers: str = Field(default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    topic_policies: str = Field(default_factory=lambda: os.getenv("KAFKA_TOPIC_POLICIES", "insurance.policies.raw"))
    topic_claims: str = Field(default_factory=lambda: os.getenv("KAFKA_TOPIC_CLAIMS", "insurance.claims.raw"))
    consumer_group: str = Field(default_factory=lambda: os.getenv("KAFKA_CONSUMER_GROUP", "snowpipe-streaming-ingest"))


class CortexSettings(BaseModel):
    model: str = Field(default_factory=lambda: os.getenv("CORTEX_MODEL", "claude-3-5-sonnet"))
    classify_model: str = Field(default_factory=lambda: os.getenv("CORTEX_CLASSIFY_MODEL", "mistral-large2"))


class SnowpipeSettings(BaseModel):
    channel_prefix: str = Field(default_factory=lambda: os.getenv("SNOWPIPE_CHANNEL_PREFIX", "broker-ingest"))
    raw_schema: str = Field(default_factory=lambda: os.getenv("SNOWPIPE_RAW_SCHEMA", "RAW"))


class Settings(BaseModel):
    snowflake: SnowflakeSettings = Field(default_factory=SnowflakeSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    cortex: CortexSettings = Field(default_factory=CortexSettings)
    snowpipe: SnowpipeSettings = Field(default_factory=SnowpipeSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def load_yaml(name: str) -> dict:
    """Load a YAML config file from the config/ directory by base name."""
    path = CONFIG_DIR / name
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def broker_mappings() -> dict:
    return load_yaml("broker_mappings.yaml")


def canonical_schema() -> dict:
    return load_yaml("canonical_schema.yaml")


def dq_rules() -> dict:
    return load_yaml("data_quality_rules.yaml")


settings = get_settings()

"""Application settings.

Provider and model names come from configuration only — never hardcoded at
call sites. The dev profile uses the hosted LLM provider; embeddings are
always local. See AGENTS.md and docs/SPEC.md Section 8.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration.

    The settings object deliberately does not read any .env file (AGENTS.md:
    never read secrets). Values come from process environment, Compose
    environment, or the defaults below (dev/demo defaults, not secrets).
    `env_ignore_empty` keeps a set-but-empty variable (compose interpolation
    with no value) from shadowing a later alias or the default.
    """

    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", populate_by_name=True, env_ignore_empty=True
    )

    app_name: str = "Defence Gateway AI"
    app_version: str = "0.1.0"

    # Database. OWNER URL runs migrations (table owner, bypasses RLS);
    # APP URL is the runtime role to which row-level security applies.
    owner_database_url: str = (
        "postgresql+psycopg://gateway_owner:dev-owner-password@localhost:5434/gateway"
    )
    app_database_url: str = (
        "postgresql+psycopg://gateway_app:dev-app-password@localhost:5434/gateway"
    )
    test_owner_database_url: str = (
        "postgresql+psycopg://gateway_owner:dev-owner-password@localhost:5434/gateway_test"
    )
    test_app_database_url: str = (
        "postgresql+psycopg://gateway_app:dev-app-password@localhost:5434/gateway_test"
    )

    # Stubbed identity (Keycloak is stubbed for the demo — docs/STUBS.md).
    # Dev-only signing secret (>= 32 bytes per RFC 7518); the real deployment
    # uses Keycloak's keys.
    dev_jwt_secret: str = "dev-only-secret-change-me-0123456789abcdef"
    dev_jwt_ttl_seconds: int = 7200

    # AI gateway — provider/model from config, never hardcoded (AGENTS.md).
    # The hosted API key is accepted under either name so the Compose env and
    # the developer's .env (Gemini) both work; the value is never logged.
    llm_provider: str = "hosted"
    llm_model: str = "gemini-3.5-flash"
    hosted_api_key: str = Field(
        default="", validation_alias=AliasChoices("HOSTED_API_KEY", "GEMINI_API_KEY")
    )
    hosted_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    hosted_timeout_seconds: float = 25.0
    hosted_max_retries: int = 2
    local_vllm_base_url: str = "http://localhost:8000/v1"
    embedding_provider: str = "local"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_cache_dir: str = "data/models"
    llm_response_cache_path: str = "data/demo_llm_cache.json"

    # Audit tamper evidence (SPEC 14.2): checkpoint file (layer 1) and the
    # external git ledger repo (layer 2). A checkpoint line is written when
    # the event count crosses a multiple of this interval.
    audit_checkpoint_path: str = "data/audit_checkpoints.log"
    audit_ledger_path: str = "~/projects/gateway-audit-ledger"
    audit_checkpoint_interval: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()

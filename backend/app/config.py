"""Application settings.

Provider and model names come from configuration only — never hardcoded at
call sites. The dev profile uses the hosted LLM provider; embeddings are
always local. See AGENTS.md and docs/SPEC.md Section 8.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration.

    The settings object deliberately does not read any .env file (AGENTS.md:
    never read secrets). Values come from process environment, Compose
    environment, or the defaults below (dev/demo defaults, not secrets).
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

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
    llm_provider: str = "hosted"
    llm_model: str = ""
    hosted_api_key: str = ""
    embedding_provider: str = "local"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()

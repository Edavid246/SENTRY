from app.config import Settings


def test_dev_defaults() -> None:
    settings = Settings()
    assert settings.embedding_dim == 1024
    assert settings.embedding_provider == "local"
    assert settings.llm_provider == "hosted"
    assert settings.owner_database_url.endswith("/gateway")
    assert settings.test_owner_database_url.endswith("/gateway_test")
    assert "@localhost:5434/" in settings.app_database_url


def test_provider_and_model_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "local-vllm")
    monkeypatch.setenv("LLM_MODEL", "some-open-weight-model")
    monkeypatch.setenv("EMBEDDING_DIM", "768")
    settings = Settings()
    assert settings.llm_provider == "local-vllm"
    assert settings.llm_model == "some-open-weight-model"
    assert settings.embedding_dim == 768


def test_api_key_accepts_compose_and_gemini_env_names(monkeypatch) -> None:
    monkeypatch.delenv("HOSTED_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert Settings().hosted_api_key == ""
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    assert Settings().hosted_api_key == "gemini-key"
    monkeypatch.setenv("HOSTED_API_KEY", "compose-key")
    settings = Settings()
    assert settings.hosted_api_key == "compose-key"
    assert settings.llm_model == "gemini-3.5-flash"
    assert settings.hosted_base_url.startswith("https://")


def test_empty_env_value_does_not_shadow_key_or_default(monkeypatch) -> None:
    monkeypatch.setenv("HOSTED_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    assert Settings().hosted_api_key == "gemini-key"
    monkeypatch.setenv("LLM_MODEL", "")
    assert Settings().llm_model == "gemini-3.5-flash"


def test_cache_record_is_refused_outside_the_dev_profile(monkeypatch) -> None:
    import pytest
    from pydantic import ValidationError

    monkeypatch.setenv("LLM_CACHE_RECORD", "1")
    assert Settings().llm_cache_record is True  # dev profile is the default
    monkeypatch.setenv("APP_PROFILE", "onprem")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("APP_PROFILE", "dev")
    monkeypatch.setenv("LLM_CACHE_ONLY", "1")
    with pytest.raises(ValidationError):
        Settings()


def test_seed_anchor_can_be_pinned(monkeypatch) -> None:
    from datetime import date

    from app import seed

    monkeypatch.setenv("SEED_DATE_ANCHOR", "2026-10-07")
    assert seed._days_from_today(0) == "2026-10-07"
    assert seed._days_from_today(-5) == "2026-10-02"
    monkeypatch.delenv("SEED_DATE_ANCHOR")
    assert seed._days_from_today(0) == date.today().isoformat()

from app.config import Settings


def test_dev_defaults() -> None:
    settings = Settings()
    assert settings.embedding_dim == 1024
    assert settings.embedding_provider == "local"
    assert settings.llm_provider == "hosted"
    assert settings.owner_database_url.endswith("/gateway")
    assert settings.test_owner_database_url.endswith("/gateway_test")
    assert "@localhost:5432/" in settings.app_database_url


def test_provider_and_model_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "local-vllm")
    monkeypatch.setenv("LLM_MODEL", "some-open-weight-model")
    monkeypatch.setenv("EMBEDDING_DIM", "768")
    settings = Settings()
    assert settings.llm_provider == "local-vllm"
    assert settings.llm_model == "some-open-weight-model"
    assert settings.embedding_dim == 768

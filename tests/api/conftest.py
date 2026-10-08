"""API test fixture: an in-process TestClient wired to the seeded gateway_test DB.

The application reads its database URL from Settings at request time, so the
session fixture points APP_DATABASE_URL at the test database, clears the
settings/engine caches, and restores both afterwards.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client(settings, seeded, audit_test_env):
    from app.config import get_settings
    from app.db import reset_engine

    previous = os.environ.get("APP_DATABASE_URL")
    os.environ["APP_DATABASE_URL"] = settings.test_app_database_url
    get_settings.cache_clear()
    reset_engine()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    if previous is None:
        os.environ.pop("APP_DATABASE_URL", None)
    else:
        os.environ["APP_DATABASE_URL"] = previous
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture
def models(client):
    """Install a model at the seam: `models(llm=None, embed=None) -> ModelPort`.

    Defaults: a FakeLLM (tests/api/fakes.py) and no embedder, so retrieval runs
    keyword-only (no model weights, no network, no keys). Removed after the test.
    """
    from app.ai_gateway.port import ModelPort
    from app.api.deps import get_models
    from app.main import app
    from fakes import FakeLLM

    def install(llm=None, embed=None) -> ModelPort:
        port = ModelPort(
            llm=llm if llm is not None else FakeLLM(),
            embed=embed if embed is not None else (lambda question: None),
        )
        app.dependency_overrides[get_models] = lambda: port
        return port

    yield install
    app.dependency_overrides.pop(get_models, None)

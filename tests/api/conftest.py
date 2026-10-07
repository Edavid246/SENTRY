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
def client(settings, seeded):
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

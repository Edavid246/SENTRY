"""Shared fixtures for all integration-style tests (unit tests don't need them).

Engines are session-scoped with pool_size=1 so connection reuse (and any RLS
context left on a pooled connection) is deterministic across tests. Every
fixture skips with a visible message when the infra stack is not running.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from app.config import Settings
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

REPO_ROOT = Path(__file__).resolve().parents[1]


def _engine(url: str) -> Engine:
    return create_engine(url, connect_args={"connect_timeout": 3}, pool_size=1, max_overflow=0)


def _connect_or_skip(engine: Engine) -> Engine:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — skip only when the stack is down
        engine.dispose()
        pytest.skip(f"database not running — start infra compose first ({type(exc).__name__})")
    return engine


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def app_engine(settings: Settings) -> Iterator[Engine]:
    engine = _connect_or_skip(_engine(settings.test_app_database_url))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def owner_engine(settings: Settings) -> Iterator[Engine]:
    engine = _connect_or_skip(_engine(settings.test_owner_database_url))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrated(settings: Settings) -> Iterator[None]:
    """Bring gateway_test to head via the real alembic pipeline (idempotent)."""
    engine = _connect_or_skip(_engine(settings.test_owner_database_url))
    engine.dispose()
    cfg = AlembicConfig(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.test_owner_database_url)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session")
def seeded(migrated: None, settings: Settings) -> Iterator[None]:
    from app.seed import run as run_seed

    run_seed(settings.test_owner_database_url)
    yield

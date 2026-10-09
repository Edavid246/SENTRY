"""Shared fixtures for all integration-style tests (unit tests don't need them).

Engines are session-scoped with pool_size=1 so connection reuse (and any RLS
context left on a pooled connection) is deterministic across tests. Every
fixture skips with a visible message when the infra stack is not running.
"""

from __future__ import annotations

import os
import subprocess
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


@pytest.fixture(scope="session", autouse=True)
def audit_test_env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Point the audit checkpoint file and git ledger at per-session temp paths.

    The dev checkpoint/ledger must never be touched by tests (gateway_test is
    a separate database), and the layer-2 ledger needs a real `git init`-ed
    repository so commit paths are exercised for real. Runs before anything
    calls get_settings(), because the settings cache is cleared here.
    """
    from app.config import get_settings

    tmp = tmp_path_factory.mktemp("audit-env")
    ledger = tmp / "ledger"
    ledger.mkdir()
    for args in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "audit-tests"],
        ["git", "config", "user.email", "audit-tests@localhost"],
    ):
        subprocess.run(args, cwd=ledger, check=True, capture_output=True)
    previous = {
        name: os.environ.get(name) for name in ("AUDIT_CHECKPOINT_PATH", "AUDIT_LEDGER_PATH")
    }
    os.environ["AUDIT_CHECKPOINT_PATH"] = str(tmp / "checkpoints.log")
    os.environ["AUDIT_LEDGER_PATH"] = str(ledger)
    get_settings.cache_clear()
    yield
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def settings(audit_test_env: None) -> Settings:
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

    run_seed(settings.test_owner_database_url, include_archived=True)
    yield


DOCS_DIR = REPO_ROOT / "data" / "documents"


@pytest.fixture
def ingested(
    migrated: None, seeded: None, owner_engine: Engine, monkeypatch
) -> Iterator[dict[str, int]]:
    """Ingest the demo document corpus (DOC-201..204) into the test DB.

    Embeddings are stubbed to NULL so the fixture is fast and needs no model
    weights: retrieval then exercises the full-text path, which is the honest
    fallback the worker also documents. Vector behaviour is covered by a
    dedicated test that seeds controlled vectors directly.

    The corpus is removed again afterwards: the gold-set oracles
    (tests/authz, tests/api/test_data_endpoints) assert exact document sets
    against the seed corpus only, and they share this session-scoped database.
    """
    monkeypatch.setattr("app.knowledge.ingest._embed", lambda texts: [None] * len(texts))
    from app.knowledge.ingest import ingest_documents

    summary = ingest_documents(owner_engine, DOCS_DIR)
    yield summary
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM chunks WHERE document_id IN"
                " (SELECT id FROM documents WHERE source_ref LIKE 'DOC-2%')"
            )
        )
        conn.execute(text("DELETE FROM documents WHERE source_ref LIKE 'DOC-2%'"))

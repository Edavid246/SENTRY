"""Alembic environment: diffs Base.metadata against the live schema.

The connection URL is resolved in this order:
  1. a sqlalchemy.url already set on the Config (tests do this);
  2. the ALEMBIC_DATABASE_URL environment variable (targeted generation);
  3. Settings.owner_database_url (migrations run as the table owner —
     gateway_owner bypasses RLS because it owns the tables).
"""

from __future__ import annotations

import os

import app.audit.models  # noqa: F401
import app.authz.models  # noqa: F401
import app.connectors.models  # noqa: F401
import app.knowledge.models  # noqa: F401
from alembic import context
from app.config import get_settings
from app.db import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option(
        "sqlalchemy.url",
        os.environ.get("ALEMBIC_DATABASE_URL") or get_settings().owner_database_url,
    )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

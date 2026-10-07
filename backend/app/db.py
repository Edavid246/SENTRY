"""Database engine/session management and row-level-security context.

Every application session that touches classified tables must call
``set_rls_context`` before its first query, in the same transaction. The
context is set transaction-locally (``set_config(..., true)``) so pooled
connections never leak one user's context into another user's transaction.

The RLS policies in the migrations read these variables via
``NULLIF(current_setting(..., true), '')`` so that a pooled connection with a
missing or cleared context returns zero rows — never an error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

if TYPE_CHECKING:
    from app.authz.context import AccessContext


class Base(DeclarativeBase):
    """Declarative base for all gateway ORM models (migrations diff against it)."""


RLS_KEYS: tuple[str, ...] = (
    "user_id",
    "clearance_rank",
    "compartments",
    "unit_path",
    "data_scope",
    "session_id",
)


def format_array(values: list[str] | tuple[str, ...] | set[str] | frozenset[str]) -> str:
    """Format a compartment list as a PostgreSQL text[] literal string.

    Compartment codes are configuration data ([A-Za-z0-9_-]); assert that so
    no quoting/injection path exists.
    """
    items = sorted(str(v) for v in values)
    for item in items:
        if not all(c.isalnum() or c in "-_" for c in item):
            raise ValueError(f"invalid compartment code: {item!r}")
    return "{" + ",".join(items) + "}"


def rls_context_statements(
    *,
    user_id: UUID | str,
    clearance_rank: int,
    compartments: list[str] | tuple[str, ...] | set[str] | frozenset[str],
    unit_path: str,
    data_scope: str,
    session_id: str,
) -> list[tuple[str, dict[str, Any]]]:
    """Build the transaction-local set_config statements for one access context."""
    values: dict[str, str] = {
        "user_id": str(user_id),
        "clearance_rank": str(int(clearance_rank)),
        "compartments": format_array(compartments),
        "unit_path": str(unit_path),
        "data_scope": str(data_scope),
        "session_id": str(session_id),
    }
    return [
        (f"SELECT set_config('app.{key}', :value, true)", {"value": value})
        for key, value in values.items()
    ]


def rls_clear_statements() -> list[str]:
    """Session-level clear of every RLS variable (simulates a stale pooled connection)."""
    return [f"SELECT set_config('app.{key}', '', false)" for key in RLS_KEYS]


def set_rls_context(
    conn: Any,
    *,
    user_id: UUID | str,
    clearance_rank: int,
    compartments: list[str] | tuple[str, ...] | set[str] | frozenset[str],
    unit_path: str,
    data_scope: str,
    session_id: str,
) -> None:
    """Apply the access context to the connection's current transaction."""
    for stmt, params in rls_context_statements(
        user_id=user_id,
        clearance_rank=clearance_rank,
        compartments=compartments,
        unit_path=unit_path,
        data_scope=data_scope,
        session_id=session_id,
    ):
        conn.execute(text(stmt), params)


def set_rls_context_for(conn: Any, ctx: AccessContext) -> None:
    """Apply an AccessContext to the connection's current transaction."""
    set_rls_context(
        conn,
        user_id=ctx.user_id,
        clearance_rank=ctx.clearance_rank,
        compartments=ctx.compartments,
        unit_path=ctx.unit_path,
        data_scope=ctx.data_scope,
        session_id=ctx.session_id,
    )


def clear_rls_context(conn: Any) -> None:
    """Clear the context at session level (used by tests to simulate pooled reuse)."""
    for stmt in rls_clear_statements():
        conn.execute(text(stmt))


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings().app_database_url)
    return _engine


def reset_engine() -> None:
    """Dispose and drop the cached engine (tests that change configuration)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None

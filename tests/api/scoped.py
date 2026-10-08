"""Test helpers: run data-access code on an authorized Scope outside a route."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from app.authz.context import AccessContext
from app.authz.scope import Scope, open_scope
from app.data_queries.registry import ToolOutcome, execute_tool
from sqlalchemy.engine import Engine


@contextmanager
def scoped(engine: Engine, ctx: AccessContext) -> Iterator[Scope]:
    """A fresh connection scoped to `ctx`; what it records is audited on exit."""
    with engine.connect() as conn, open_scope(ctx, conn) as scope:
        yield scope


def run_tool(
    engine: Engine, ctx: AccessContext, name: str, params: Mapping[str, Any]
) -> tuple[ToolOutcome, dict[str, Any]]:
    """Run one tool call; returns its outcome and the audit payload it wrote."""
    with scoped(engine, ctx) as scope:
        outcome = execute_tool(scope, name, params)
    (written,) = scope.written
    return outcome, written["payload"]

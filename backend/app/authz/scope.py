"""Authorized scope: the one authorization and audit sequence for every read (SPEC 7.3, 14).

    decided = authorize(ctx, [("read", "document")])     # Forbidden if denied
    with open_scope(ctx, conn, decided) as scope:
        documents = list_documents(scope)                # row filter + RLS inside
        scope.read("document", len(documents))

AGENTS.md Principle Zero, in order:

  1. `authorize` asks the policy about each (action, resource) the request
     needs. A deny is audited at once (its decide events) and raised as
     Forbidden; nothing has been read.
  2. `open_scope` sets the caller's RLS context on the connection exactly once.
     Every data-access function takes the Scope rather than (conn, ctx), so it
     cannot run on a connection without one, and takes its row filter from
     `scope.filter`, so the policy filter and RLS always apply together.
  3. Everything the request does is recorded on the scope (`read`, `record`):
     typed-tool calls, retrievals, answers. When the block ends, normally or by
     an exception, the decide events and every recorded event are written as
     one batch, in the order they happened.
  4. Writes are committed only after that batch is in the log (`commit()`
     asks for it): stored data never exists without its audit record. If the
     body raises, nothing is committed, but what ran is still audited.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from sqlalchemy.engine import Connection

from app.audit.events import audit_events, decide_event, query_event
from app.authz.context import AccessContext
from app.authz.policy import RowFilter, get_policy
from app.db import set_rls_context_for

Requirement = tuple[str, str]  # (action, resource)


class Forbidden(Exception):
    """A policy decision denied the request (already audited)."""


class Scope:
    """A connection scoped to one caller: RLS set, row filters at hand, events recorded."""

    def __init__(self, ctx: AccessContext, conn: Connection) -> None:
        set_rls_context_for(conn, ctx)
        self.ctx = ctx
        self.conn = conn
        self.events: list[dict[str, Any]] = []
        self.written: list[dict[str, Any]] = []  # the stored audit rows, once the scope closes
        self._commit = False

    def filter(self, resource: str) -> RowFilter:
        """The policy row filter for `resource`, to put inside the SQL."""
        return get_policy().row_filter(self.ctx, resource)

    def read(self, resource: str, rows: int, **ids: Any) -> None:
        """Record that `rows` rows of `resource` were read (ids: record_ids, item_ids...)."""
        self.events.append(query_event(self.ctx, resource, rows, **ids))

    def record(self, payload: dict[str, Any]) -> None:
        """Record any other audit event that belongs to this request."""
        self.events.append(payload)

    def commit(self) -> None:
        """Commit this scope's writes once its audit batch has been written."""
        self._commit = True


def authorize(
    ctx: AccessContext, requirements: Sequence[Requirement], *, audit_resource: str | None = None
) -> list[dict[str, Any]]:
    """Decide each requirement in order; return the allow events, or audit and raise Forbidden.

    The first deny stops the sequence. `audit_resource` names the decide events'
    resource when it differs from the policy resource (e.g. "connected_map").
    """
    policy = get_policy()
    decided: list[dict[str, Any]] = []
    for action, resource in requirements:
        decision = policy.decide(ctx, action, resource)
        decided.append(
            decide_event(ctx, decision, resource=audit_resource or resource, requested=action)
        )
        if not decision.allowed:
            audit_events(decided)
            raise Forbidden
    return decided


@contextmanager
def open_scope(
    ctx: AccessContext, conn: Connection, decided: Sequence[dict[str, Any]] = ()
) -> Iterator[Scope]:
    """Scope `conn` to `ctx`; audit `decided` plus everything recorded on the way out."""
    scope = Scope(ctx, conn)
    try:
        yield scope
    finally:
        scope.written = audit_events([*decided, *scope.events])
    if scope._commit:
        conn.commit()


@contextmanager
def authorized(
    ctx: AccessContext,
    conn: Connection,
    requirements: Sequence[Requirement],
    *,
    audit_resource: str | None = None,
) -> Iterator[Scope]:
    """`authorize` then `open_scope`: the whole sequence for one request."""
    decided = authorize(ctx, requirements, audit_resource=audit_resource)
    with open_scope(ctx, conn, decided) as scope:
        yield scope

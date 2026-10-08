"""Guarded reads: the authorization and audit sequence every data route follows.

    with guarded(ctx, conn, "read", "document") as scope:
        rows = conn.execute(text(f"... WHERE {scope.filter('document').where_sql}"), ...)
        scope.read("documents", len(rows))

`guarded` owns the order (AGENTS.md Principle Zero, SPEC 7.3, SPEC 14):

  1. the policy decides whether the action may run at all;
  2. a deny is audited (one decide event) and answered per `on_deny`:
     "forbidden" (403), "not_found" (404, so a probe never learns that a
     restricted item exists) or "empty" (the route serves an empty result;
     `scope.allowed` is False and `scope.filter` refuses to run);
  3. an allow sets the caller's RLS context on the connection, so the policy
     row filter (`scope.filter`) and RLS apply together inside the query;
  4. when the block ends, normally or by an exception (a 404 for a missing
     row, a model outage), the decide event and every read the route recorded
     are written in one batch. A route cannot read without being audited.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy.engine import Connection

from app.audit.events import audit_events, decide_event, query_event
from app.authz.context import AccessContext
from app.authz.policy import RowFilter, get_policy
from app.db import set_rls_context_for

OnDeny = Literal["forbidden", "not_found", "empty"]


class Scope:
    """What a route may do inside a guarded block."""

    def __init__(self, ctx: AccessContext, allowed: bool) -> None:
        self.ctx = ctx
        self.allowed = allowed
        self.events: list[dict[str, Any]] = []

    def filter(self, resource: str) -> RowFilter:
        """The policy row filter for `resource`, to put inside the SQL."""
        if not self.allowed:
            raise RuntimeError("no row filter for a denied request")
        return get_policy().row_filter(self.ctx, resource)

    def read(self, resource: str, rows: int, **ids: Any) -> None:
        """Record that `rows` rows of `resource` were read (ids: record_ids, item_ids...)."""
        self.events.append(query_event(self.ctx, resource, rows, **ids))

    def event(self, payload: dict[str, Any]) -> None:
        """Record any other audit event that belongs to this request."""
        self.events.append(payload)


@contextmanager
def guarded(
    ctx: AccessContext,
    conn: Connection | None,
    action: str,
    resource: str,
    *,
    on_deny: OnDeny = "forbidden",
    audit_resource: str | None = None,
) -> Iterator[Scope]:
    """Decide, deny or scope the connection, and audit the request on the way out.

    `audit_resource` names the decide event's resource when it differs from the
    policy resource (e.g. "connected_map" for a record read through the map).
    `conn` may be None for a route that reads nothing through the database.
    """
    decision = get_policy().decide(ctx, action, resource)
    decided = decide_event(ctx, decision, resource=audit_resource or resource, requested=action)
    if not decision.allowed:
        audit_events([decided])
        if on_deny == "forbidden":
            raise HTTPException(status_code=403, detail="forbidden")
        if on_deny == "not_found":
            raise HTTPException(status_code=404, detail="not found")
        yield Scope(ctx, allowed=False)
        return
    if conn is not None:
        set_rls_context_for(conn, ctx)
    scope = Scope(ctx, allowed=True)
    try:
        yield scope
    finally:
        audit_events([decided, *scope.events])

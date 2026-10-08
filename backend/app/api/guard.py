"""Guarded routes: the HTTP face of app.authz.scope.

    with guarded(ctx, conn, "read", "document") as scope:
        documents = list_documents(scope)
        scope.read("document", len(documents))

`guarded` runs the one authorization sequence (`authorize`, then `open_scope`;
see app.authz.scope) and answers a deny the way the route needs:

  * on_deny="forbidden": 403;
  * on_deny="not_found": 404, so a probe never learns that a restricted item
    exists.

`guarded_or_empty` yields None on a deny instead (the route serves an empty
result), and `permitted` is for routes that read nothing through the
request's connection (the audit viewer).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.engine import Connection

from app.audit.events import audit_events
from app.authz.context import AccessContext
from app.authz.scope import Forbidden, Scope, authorize, open_scope

OnDeny = Literal["forbidden", "not_found"]


def _denied(on_deny: OnDeny) -> HTTPException:
    if on_deny == "not_found":
        return HTTPException(status_code=404, detail="not found")
    return HTTPException(status_code=403, detail="forbidden")


@contextmanager
def guarded(
    ctx: AccessContext,
    conn: Connection,
    action: str,
    resource: str,
    *,
    on_deny: OnDeny = "forbidden",
) -> Iterator[Scope]:
    """Decide, then scope the connection; a deny is audited and answered per `on_deny`."""
    try:
        decided = authorize(ctx, [(action, resource)])
    except Forbidden:
        raise _denied(on_deny) from None
    with open_scope(ctx, conn, decided) as scope:
        yield scope


@contextmanager
def guarded_or_empty(
    ctx: AccessContext, conn: Connection, action: str, resource: str, *, audit_resource: str
) -> Iterator[Scope | None]:
    """Like `guarded`, but a deny yields None: the route answers with an empty result.

    `audit_resource` names the view in the decide event (e.g. "connected_map").
    """
    try:
        decided = authorize(ctx, [(action, resource)], audit_resource=audit_resource)
    except Forbidden:
        yield None
        return
    with open_scope(ctx, conn, decided) as scope:
        yield scope


def permitted(ctx: AccessContext, action: str, resource: str) -> None:
    """Decide and audit an action that reads nothing through the request connection; 403 on deny."""
    try:
        audit_events(authorize(ctx, [(action, resource)]))
    except Forbidden:
        raise _denied("forbidden") from None

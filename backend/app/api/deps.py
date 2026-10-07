"""FastAPI dependencies: bearer token -> AccessContext, and the request connection.

One gateway_app database connection per request: the token validator reads the
identity tables through it first, then the endpoint sets the RLS context in
the same transaction and runs its query — authorization before retrieval
(AGENTS.md Principle Zero), never the other way around.

`audit_events` is the single wiring point from HTTP into the hash-chained
audit log (SPEC 14): endpoints batch their events through it, and a token
that fails validation is audited here before the generic 401.
"""

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException
from sqlalchemy.engine import Connection

from app.audit.chain import append_events, utc_now_iso
from app.authz.context import AccessContext
from app.authz.policy import Decision
from app.authz.tokens import DevTokenValidator, TokenError
from app.db import get_engine


def get_conn() -> Iterator[Connection]:
    """Yield the request's connection; closed (rolled back) when the request ends."""
    with get_engine().connect() as conn:
        yield conn


ConnDep = Annotated[Connection, Depends(get_conn)]


def audit_events(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append a batch of audit events; failure is blocking (500, no data served).

    Returns the stored rows (seq/event_id/... in insertion order) so callers
    that need to surface an audit id (the assistant answer event) can do so.
    """
    if not payloads:
        return []
    return append_events(get_engine(), payloads)


def decide_event(
    ctx: AccessContext, decision: Decision, *, resource: str, requested: str
) -> dict[str, Any]:
    """Audit payload for a policy decision (allow or deny)."""
    payload: dict[str, Any] = {
        "actor": ctx.username,
        "action": "decide",
        "resource": resource,
        "requested": requested,
        "decision": "allow" if decision.allowed else "deny",
        "timestamp": utc_now_iso(),
    }
    if not decision.allowed:
        payload["reasons"] = list(decision.reasons)
    return payload


def query_event(ctx: AccessContext, resource: str, rows: int, **extra: Any) -> dict[str, Any]:
    """Audit payload for rows actually read; `extra` carries ids (record_ids, item_ids)."""
    return {
        "actor": ctx.username,
        "action": "query",
        "resource": resource,
        "decision": "allow",
        "rows": int(rows),
        **extra,
        "timestamp": utc_now_iso(),
    }


def _unauthenticated() -> HTTPException:
    # Fresh instance per raise; the same generic 401 for every auth failure.
    return HTTPException(
        status_code=401, detail="not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )


def current_context(
    conn: ConnDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AccessContext:
    """Resolve `Authorization: Bearer <jwt>` to an AccessContext, or 401.

    Missing header, malformed header, bad/expired/forged token, unknown or
    inactive user — all produce the same generic 401, never a 500 and never
    a hint about which part failed. Rejected tokens are audited (the audit
    trail records attempted access); bare/absent credentials are not.
    """
    if not authorization:
        raise _unauthenticated()
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise _unauthenticated()
    try:
        return DevTokenValidator().validate(token.strip(), conn=conn)
    except TokenError as exc:
        audit_events(
            [
                {
                    "actor": "anonymous",
                    "action": "authenticate",
                    "resource": "auth",
                    "decision": "deny",
                    "reasons": [str(exc)],
                    "timestamp": utc_now_iso(),
                }
            ]
        )
        raise _unauthenticated() from exc


CurrentContext = Annotated[AccessContext, Depends(current_context)]

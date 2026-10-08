"""FastAPI dependencies: bearer token -> AccessContext, and the request connection.

One gateway_app database connection per request: the token validator reads the
identity tables through it first, then the endpoint sets the RLS context in
the same transaction and runs its query — authorization before retrieval
(AGENTS.md Principle Zero), never the other way around.

A token that fails validation is audited here (app.audit.events) before the
generic 401.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.engine import Connection

from app.ai_gateway.port import ModelPort
from app.audit.chain import utc_now_iso
from app.audit.events import audit_events
from app.authz.context import AccessContext
from app.authz.tokens import DevTokenValidator, TokenError
from app.db import get_engine


def get_conn() -> Iterator[Connection]:
    """Yield the request's connection; closed (rolled back) when the request ends."""
    with get_engine().connect() as conn:
        yield conn


ConnDep = Annotated[Connection, Depends(get_conn)]


def get_models() -> ModelPort:
    """The model seam for this request: the configured AI gateway + local embedder.

    Tests and scripts replace it with `app.dependency_overrides[get_models]`.
    """
    return ModelPort()


ModelsDep = Annotated[ModelPort, Depends(get_models)]


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

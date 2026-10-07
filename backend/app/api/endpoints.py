"""HTTP endpoints: login, identity, and classified list/detail reads.

Authorization order is fixed: LocalPolicy.decide first (may this action run
at all?), then set_rls_context + LocalPolicy.row_filter together inside one
transaction (which rows?). The detail route returns 404 for anything not
visible — including callers whose action was denied — so a probe can never
distinguish a restricted document from a non-existent one.
"""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.deps import ConnDep, CurrentContext
from app.authz.context import AccessContext
from app.authz.policy import LocalPolicy
from app.authz.tokens import DevTokenValidator
from app.db import set_rls_context

POLICY = LocalPolicy()
_HASHER = PasswordHasher()
# Same generic 401 for unknown user and wrong password; a dummy verify keeps
# the two paths close in timing so the message is not the only protection.
_DUMMY_HASH = _HASHER.hash("timing-equaliser")

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


def _set_context(conn: Connection, ctx: AccessContext) -> None:
    set_rls_context(
        conn,
        user_id=ctx.user_id,
        clearance_rank=ctx.clearance_rank,
        compartments=ctx.compartments,
        unit_path=ctx.unit_path,
        data_scope=ctx.data_scope,
        session_id=ctx.session_id,
    )


@router.post("/auth/login", tags=["auth"])
def login(body: LoginRequest, conn: ConnDep) -> dict[str, str]:
    row = conn.execute(
        text("SELECT password_hash, is_active FROM users WHERE username = :username"),
        {"username": body.username},
    ).first()
    is_active = row is not None and bool(row.is_active)
    stored_hash = row.password_hash if is_active else _DUMMY_HASH
    try:
        _HASHER.verify(stored_hash, body.password)
        password_ok = is_active
    except (Argon2Error, ValueError):
        password_ok = False
    if not password_ok:
        raise HTTPException(
            status_code=401,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "access_token": DevTokenValidator().issue_token(body.username),
        "token_type": "bearer",
    }


@router.get("/me", tags=["auth"])
def me(ctx: CurrentContext) -> dict[str, str | int | list[str] | None]:
    """UI-facing identity read: exactly the context fields the UI needs, nothing internal."""
    return {
        "username": ctx.username,
        "role": ctx.role,
        "unit_path": ctx.unit_path,
        "clearance_code": ctx.clearance_code,
        "clearance_rank": ctx.clearance_rank,
        "compartments": sorted(ctx.compartments),
        "data_scope": ctx.data_scope,
    }


@router.get("/documents", tags=["data"])
def list_documents(ctx: CurrentContext, conn: ConnDep) -> list[dict[str, str | None]]:
    if not POLICY.decide(ctx, "read", "document").allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    _set_context(conn, ctx)
    row_filter = POLICY.row_filter(ctx, "document")
    rows = conn.execute(
        text(
            "SELECT source_ref, title, classification_code FROM documents"
            f" WHERE {row_filter.where_sql} ORDER BY source_ref"
        ),
        row_filter.params,
    ).mappings()
    return [dict(row) for row in rows]


@router.get("/records", tags=["data"])
def list_records(ctx: CurrentContext, conn: ConnDep) -> list[dict[str, str]]:
    if not POLICY.decide(ctx, "retrieve", "record").allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    _set_context(conn, ctx)
    row_filter = POLICY.row_filter(ctx, "record")
    rows = conn.execute(
        text(
            "SELECT source_ref, entity_type, classification_code FROM canonical_records"
            f" WHERE {row_filter.where_sql} ORDER BY source_ref"
        ),
        row_filter.params,
    ).mappings()
    return [dict(row) for row in rows]


@router.get("/documents/{source_ref}", tags=["data"])
def get_document(source_ref: str, ctx: CurrentContext, conn: ConnDep) -> dict[str, str]:
    # 404 — not 403 — whenever the row is not visible, including a denied
    # action: never confirm that a restricted document exists.
    if POLICY.decide(ctx, "read", "document").allowed:
        _set_context(conn, ctx)
        row_filter = POLICY.row_filter(ctx, "document")
        row = (
            conn.execute(
                text(
                    "SELECT source_ref, title, classification_code FROM documents"
                    f" WHERE source_ref = :source_ref AND {row_filter.where_sql}"
                ),
                {"source_ref": source_ref, **row_filter.params},
            )
            .mappings()
            .first()
        )
        if row is not None:
            return dict(row)
    raise HTTPException(status_code=404, detail="not found")

"""HTTP endpoints: login, identity, classified reads, and the audit viewer.

Authorization order is fixed: LocalPolicy.decide first (may this action run
at all?), then set_rls_context + LocalPolicy.row_filter together inside one
transaction (which rows?). The detail route returns 404 for anything not
visible — including callers whose action was denied — so a probe can never
distinguish a restricted document from a non-existent one.

Audit wiring (SPEC 14): one decide event for every request that consults the
policy (allow or deny, written before the response or status raise), plus a
query event carrying the row count when rows were actually read. Login
attempts are audited as single login events. The SELECT inside GET /audit is
itself not audited — the viewer's own read would otherwise recurse.
"""

from typing import Annotated, Any

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.deps import ConnDep, CurrentContext, audit_events
from app.audit.chain import recent_events, utc_now_iso, verify_report
from app.authz.context import AccessContext
from app.authz.policy import Decision, LocalPolicy
from app.authz.tokens import DevTokenValidator
from app.db import get_engine, set_rls_context

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


def _decide_event(ctx: AccessContext, decision: Decision, action: str, resource: str) -> dict:
    payload: dict[str, Any] = {
        "actor": ctx.username,
        "action": "decide",
        "resource": resource,
        "requested": action,
        "decision": "allow" if decision.allowed else "deny",
        "timestamp": utc_now_iso(),
    }
    if not decision.allowed:
        payload["reasons"] = list(decision.reasons)
    return payload


def _query_event(ctx: AccessContext, resource: str, rows: int) -> dict[str, Any]:
    return {
        "actor": ctx.username,
        "action": "query",
        "resource": resource,
        "decision": "allow",
        "rows": int(rows),
        "timestamp": utc_now_iso(),
    }


@router.post("/auth/login", tags=["auth"])
def login(body: LoginRequest, conn: ConnDep) -> dict[str, str]:
    row = conn.execute(
        text("SELECT id, password_hash, is_active FROM users WHERE username = :username"),
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
        audit_events(
            [
                {
                    "actor": body.username,
                    "action": "login",
                    "resource": "auth",
                    "decision": "deny",
                    "reasons": ["invalid credentials"],
                    "timestamp": utc_now_iso(),
                }
            ]
        )
        raise HTTPException(
            status_code=401,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    audit_events(
        [
            {
                "actor": body.username,
                "action": "login",
                "resource": "auth",
                "decision": "allow",
                "user_id": str(row.id),
                "timestamp": utc_now_iso(),
            }
        ]
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
    decision = POLICY.decide(ctx, "read", "document")
    if not decision.allowed:
        audit_events([_decide_event(ctx, decision, "read", "document")])
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
    results = [dict(row) for row in rows]
    audit_events(
        [
            _decide_event(ctx, decision, "read", "document"),
            _query_event(ctx, "documents", len(results)),
        ]
    )
    return results


@router.get("/records", tags=["data"])
def list_records(ctx: CurrentContext, conn: ConnDep) -> list[dict[str, str]]:
    decision = POLICY.decide(ctx, "retrieve", "record")
    if not decision.allowed:
        audit_events([_decide_event(ctx, decision, "retrieve", "record")])
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
    results = [dict(row) for row in rows]
    audit_events(
        [
            _decide_event(ctx, decision, "retrieve", "record"),
            _query_event(ctx, "canonical_records", len(results)),
        ]
    )
    return results


@router.get("/documents/{source_ref}", tags=["data"])
def get_document(source_ref: str, ctx: CurrentContext, conn: ConnDep) -> dict[str, str]:
    # 404 — not 403 — whenever the row is not visible, including a denied
    # action: never confirm that a restricted document exists.
    decision = POLICY.decide(ctx, "read", "document")
    if not decision.allowed:
        audit_events([_decide_event(ctx, decision, "read", "document")])
        raise HTTPException(status_code=404, detail="not found")
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
    audit_events(
        [
            _decide_event(ctx, decision, "read", "document"),
            _query_event(ctx, "documents", 0 if row is None else 1),
        ]
    )
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return dict(row)


@router.get("/audit", tags=["audit"])
def list_audit(
    ctx: CurrentContext,
    conn: ConnDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    """Newest-first audit trail for the audit viewer (SPEC 14)."""
    decision = POLICY.decide(ctx, "read_audit", "audit")
    audit_events([_decide_event(ctx, decision, "read_audit", "audit")])
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    # The viewer's own SELECT is not audited (no recursion); the decide event
    # above already records that the read happened.
    return recent_events(get_engine(), limit)


@router.get("/audit/verify", tags=["audit"])
def audit_verify(ctx: CurrentContext) -> dict[str, Any]:
    """Chain verification plus both tamper-evidence layers (SPEC 14.2)."""
    decision = POLICY.decide(ctx, "read_audit", "audit")
    audit_events([_decide_event(ctx, decision, "read_audit", "audit")])
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    return verify_report(get_engine())

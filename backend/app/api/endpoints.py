"""HTTP endpoints: login, identity, classified reads, and the audit viewer.

Everything is mounted under /api/v1 (one route convention; no root-level
aliases) so the Next.js UI can proxy /api/* to this service same-origin.

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
from uuid import UUID

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

router = APIRouter(prefix="/api/v1")


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
def me(ctx: CurrentContext, conn: ConnDep) -> dict[str, Any]:
    """UI-facing identity read: exactly the context fields the shell needs.

    `unit_breadcrumb` resolves the caller's unit path to readable unit names
    (oldest ancestor first) so the top bar can show "Command A > Brigade 2 >
    Battalion 4"; `permissions` is what the nav may offer — the server still
    enforces every action itself (SPEC 7.1).
    """
    breadcrumb = [
        {"path": str(row.path), "name": str(row.name)}
        for row in conn.execute(
            text(
                "SELECT path, name FROM units"
                " WHERE starts_with(:unit_path, path) ORDER BY length(path)"
            ),
            {"unit_path": ctx.unit_path},
        ).all()
    ]
    return {
        "username": ctx.username,
        "display_name": ctx.display_name,
        "role": ctx.role,
        "unit_path": ctx.unit_path,
        "unit_breadcrumb": breadcrumb,
        "clearance_code": ctx.clearance_code,
        "clearance_rank": ctx.clearance_rank,
        "compartments": sorted(ctx.compartments),
        "permissions": sorted(ctx.permissions),
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


@router.get("/documents/{document_id}/chunks/{chunk_id}", tags=["data"])
def get_document_chunk(
    document_id: str, chunk_id: str, ctx: CurrentContext, conn: ConnDep
) -> dict[str, Any]:
    """Cited-passage viewer: open the exact page/section a citation points at.

    Same authorization order and the same policy row filter + RLS as every
    other classified read. Anything not visible — including a caller whose
    action was denied, or a malformed id — answers 404 rather than 403, so a
    probe can never confirm that a restricted passage exists. `document_id`
    accepts the user-facing source_ref a citation carries, or the document's
    internal uuid.
    """
    decision = POLICY.decide(ctx, "read", "chunk")
    if not decision.allowed:
        audit_events([_decide_event(ctx, decision, "read", "chunk")])
        raise HTTPException(status_code=404, detail="not found")
    _set_context(conn, ctx)
    row_filter = POLICY.row_filter(ctx, "chunk")
    try:
        chunk_key = str(UUID(chunk_id))
    except ValueError:
        chunk_key = None
    document_where = "documents.source_ref = :document_id"
    document_value = document_id
    try:
        document_value = str(UUID(document_id))
        document_where = "documents.id = :document_id"
    except ValueError:
        pass
    row = None
    if chunk_key is not None:
        row = (
            conn.execute(
                text(
                    "SELECT chunks.id AS chunk_id, documents.id AS document_id,"
                    " documents.source_ref, documents.title, chunks.text, chunks.page,"
                    " chunks.section, chunks.classification_code, chunks.compartments"
                    " FROM chunks"
                    " JOIN documents ON documents.id = chunks.document_id"
                    f" WHERE chunks.id = :chunk_id AND {document_where}"
                    f" AND {row_filter.where_sql}"
                ),
                {"chunk_id": chunk_key, "document_id": document_value, **row_filter.params},
            )
            .mappings()
            .first()
        )
    audit_events(
        [
            _decide_event(ctx, decision, "read", "chunk"),
            _query_event(ctx, "chunks", 0 if row is None else 1),
        ]
    )
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "chunk_id": str(row["chunk_id"]),
        "document_id": str(row["document_id"]),
        "document_ref": str(row["source_ref"] or ""),
        "document_title": str(row["title"]),
        "text": str(row["text"]),
        "page": row["page"],
        "section": row["section"],
        "classification_code": str(row["classification_code"]),
        "compartments": [str(code) for code in (row["compartments"] or [])],
    }


@router.get("/audit", tags=["audit"])
def list_audit(
    ctx: CurrentContext,
    conn: ConnDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    event_id: Annotated[str | None, Query(description="return only this event")] = None,
) -> list[dict[str, Any]]:
    """Newest-first audit trail for the audit viewer (SPEC 14).

    Every item carries `event_id`, so an answer's audit_event_id deep-links
    here with `?event_id=`.
    """
    decision = POLICY.decide(ctx, "read_audit", "audit")
    audit_events([_decide_event(ctx, decision, "read_audit", "audit")])
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    # The viewer's own SELECT is not audited (no recursion); the decide event
    # above already records that the read happened.
    return recent_events(get_engine(), limit, event_id=event_id)


@router.get("/audit/verify", tags=["audit"])
def audit_verify(ctx: CurrentContext) -> dict[str, Any]:
    """Chain verification plus both tamper-evidence layers (SPEC 14.2)."""
    decision = POLICY.decide(ctx, "read_audit", "audit")
    audit_events([_decide_event(ctx, decision, "read_audit", "audit")])
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    return verify_report(get_engine())

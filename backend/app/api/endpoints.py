"""HTTP endpoints: login, identity, classified reads, and the audit viewer.

Everything is mounted under /api/v1 (one route convention; no root-level
aliases) so the Next.js UI can proxy /api/* to this service same-origin.

Every classified read runs inside `guarded` (app.api.guard): the policy
decides first, then the policy row filter and RLS apply together inside the
query, and the decide event plus a query event with the row count are audited
on the way out. The detail routes answer 404 for anything not visible —
including callers whose action was denied — so a probe can never distinguish
a restricted document from a non-existent one. Login attempts are audited as
single login events. The SELECT inside GET /audit is itself not audited — the
viewer's own read would otherwise recurse.
"""

from dataclasses import asdict
from typing import Annotated, Any

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded, permitted
from app.audit.chain import recent_events, verify_report
from app.audit.events import audit_events, event
from app.authz.tokens import DevTokenValidator
from app.connectors import get_adapter
from app.connectors.base import RecordFilter
from app.db import get_engine
from app.knowledge import passages

_HASHER = PasswordHasher()
# Same generic 401 for unknown user and wrong password; a dummy verify keeps
# the two paths close in timing so the message is not the only protection.
_DUMMY_HASH = _HASHER.hash("timing-equaliser")

router = APIRouter(prefix="/api/v1")


class LoginRequest(BaseModel):
    username: str
    password: str


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
            [event(body.username, "login", "auth", "deny", reasons=["invalid credentials"])]
        )
        raise HTTPException(
            status_code=401,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    audit_events([event(body.username, "login", "auth", "allow", user_id=str(row.id))])
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
    with guarded(ctx, conn, "read", "document") as scope:
        documents = passages.list_documents(scope)
        scope.read("document", len(documents))
    return [asdict(document) for document in documents]


@router.get("/records", tags=["data"])
def list_records(ctx: CurrentContext, conn: ConnDep) -> list[dict[str, str]]:
    with guarded(ctx, conn, "retrieve", "record") as scope:
        records = get_adapter().search(scope, RecordFilter())
        scope.read("record", len(records))
    return [
        {
            "source_ref": record.source_ref,
            "entity_type": record.entity_type,
            "classification_code": record.classification_code,
        }
        for record in records
    ]


class RecordDetail(BaseModel):
    source_ref: str
    entity_type: str
    source_system: str
    classification_code: str
    compartments: list[str]
    unit_path: str
    retrieved_at: str
    data: dict[str, Any]


@router.get("/records/{source_ref}", tags=["data"], response_model=RecordDetail)
def get_record(source_ref: str, ctx: CurrentContext, conn: ConnDep) -> RecordDetail:
    """One record, through the adapter (policy row filter + RLS). 404 when not visible."""
    with guarded(ctx, conn, "retrieve", "record", on_deny="not_found") as scope:
        record = get_adapter().get(scope, source_ref)
        scope.read("record", 0 if record is None else 1)
    if record is None:
        raise HTTPException(status_code=404, detail="not found")
    return RecordDetail(
        source_ref=record.source_ref,
        entity_type=record.entity_type,
        source_system=record.source_system,
        classification_code=record.classification_code,
        compartments=list(record.compartments),
        unit_path=record.unit_path,
        retrieved_at=record.retrieved_at.isoformat(),
        data=record.data,
    )


@router.get("/documents/{source_ref}", tags=["data"])
def get_document(source_ref: str, ctx: CurrentContext, conn: ConnDep) -> dict[str, str]:
    # 404 — not 403 — whenever the row is not visible, including a denied
    # action: never confirm that a restricted document exists.
    with guarded(ctx, conn, "read", "document", on_deny="not_found") as scope:
        found = passages.list_documents(scope, source_ref)
        scope.read("document", len(found))
    if not found:
        raise HTTPException(status_code=404, detail="not found")
    return asdict(found[0])


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
    with guarded(ctx, conn, "read", "chunk", on_deny="not_found") as scope:
        passage = passages.visible_passage(scope, document_id, chunk_id)
        scope.read("chunk", 0 if passage is None else 1)
    if passage is None:
        raise HTTPException(status_code=404, detail="not found")
    return {**asdict(passage), "compartments": list(passage.compartments)}


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
    # The viewer's own SELECT is not audited (no recursion); the decide event
    # already records that the read happened.
    permitted(ctx, "read_audit", "audit")
    return recent_events(get_engine(), limit, event_id=event_id)


@router.get("/audit/verify", tags=["audit"])
def audit_verify(ctx: CurrentContext) -> dict[str, Any]:
    """Chain verification plus both tamper-evidence layers (SPEC 14.2)."""
    permitted(ctx, "read_audit", "audit")
    return verify_report(get_engine())

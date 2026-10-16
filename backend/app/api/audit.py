"""The audit viewer: GET /api/v1/audit and /api/v1/audit/verify (SPEC 14).

Both need `read_audit`, decided and audited by `permitted`. The SELECT inside GET /audit is
itself not audited: the viewer's own read would otherwise recurse.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import permitted
from app.audit.chain import recent_events, verify_report
from app.db import get_engine

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditEventOut(BaseModel):
    seq: int
    event_id: str
    created_at: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class ChainTip(BaseModel):
    seq: int
    hash: str


class VerifyReport(BaseModel):
    valid: bool
    checked_count: int
    first_bad_event_id: str | None
    checkpoint_ok: bool | None
    checkpoint_tip: ChainTip | None
    ledger_ok: bool | None
    ledger_tip: ChainTip | None


@router.get("", response_model=list[AuditEventOut])
def list_audit(
    ctx: CurrentContext,
    conn: ConnDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    event_id: Annotated[str | None, Query(description="return only this event")] = None,
) -> list[AuditEventOut]:
    """Newest-first audit trail for the audit viewer (SPEC 14).

    Every item carries `event_id`, so an answer's audit_event_id deep-links
    here with `?event_id=`.
    """
    # The viewer's own SELECT is not audited (no recursion); the decide event
    # already records that the read happened.
    permitted(ctx, "read_audit", "audit")
    return [
        AuditEventOut.model_validate(item)
        for item in recent_events(get_engine(), limit, event_id=event_id)
    ]


@router.get("/verify", response_model=VerifyReport)
def audit_verify(ctx: CurrentContext) -> VerifyReport:
    """Chain verification plus both tamper-evidence layers (SPEC 14.2)."""
    permitted(ctx, "read_audit", "audit")
    return VerifyReport.model_validate(verify_report(get_engine()))

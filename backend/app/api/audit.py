"""The audit viewer: GET /api/v1/audit and /api/v1/audit/verify (SPEC 14).

Both need `read_audit`, decided and audited by `permitted`. The SELECT inside GET /audit is
itself not audited: the viewer's own read would otherwise recurse.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import permitted
from app.audit.chain import recent_events, verify_report
from app.db import get_engine

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("")
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


@router.get("/verify")
def audit_verify(ctx: CurrentContext) -> dict[str, Any]:
    """Chain verification plus both tamper-evidence layers (SPEC 14.2)."""
    permitted(ctx, "read_audit", "audit")
    return verify_report(get_engine())

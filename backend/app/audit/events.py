"""Writing audit events from the application (SPEC 14).

`audit_events` is the single wiring point into the hash-chained log: callers
batch their events through it, and a failed write is blocking (it raises, so
no data is served without its audit record). `decide_event` and `query_event`
build the two payloads every guarded read writes (see app.api.guard).
"""

from __future__ import annotations

from typing import Any

from app.audit.chain import append_events, utc_now_iso
from app.authz.context import AccessContext
from app.authz.policy import Decision
from app.db import get_engine


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

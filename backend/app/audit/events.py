"""Writing audit events from the application (SPEC 14).

`audit_events` is the single wiring point into the hash-chained log: callers
batch their events through it, and a failed write is blocking (it raises, so
no data is served without its audit record). `event` builds every payload, so
each one carries the same core fields (actor, action, resource, decision,
timestamp); `decide_event` and `query_event` are the two every guarded read
writes (see app.authz.scope).

Vocabulary: `resource` is a policy resource name ("document", "chunk",
"record", "conversation", "message", "finding", "dashboard", "assistant",
"auth"), or a view's audit name where a route reads records for a view
("connected_map", "connected_replay").
"""

from __future__ import annotations

from typing import Any

from app.audit.chain import append_events, utc_now_iso
from app.authz.context import AccessContext
from app.authz.policy import Decision
from app.db import get_engine

AUDIT_TEXT_LIMIT = 300


def audit_events(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append a batch of audit events; failure is blocking (500, no data served).

    Returns the stored rows (seq/event_id/... in insertion order) so callers
    that need to surface an audit id (the assistant answer event) can do so.
    """
    if not payloads:
        return []
    return append_events(get_engine(), payloads)


def event(actor: str, action: str, resource: str, decision: str, **fields: Any) -> dict[str, Any]:
    """One audit payload: the core fields, then `fields`, then the timestamp."""
    return {
        "actor": actor,
        "action": action,
        "resource": resource,
        "decision": decision,
        **fields,
        "timestamp": utc_now_iso(),
    }


def decide_event(
    ctx: AccessContext, decision: Decision, *, resource: str, requested: str
) -> dict[str, Any]:
    """Audit payload for a policy decision (allow or deny)."""
    if decision.allowed:
        return event(ctx.username, "decide", resource, "allow", requested=requested)
    return event(
        ctx.username,
        "decide",
        resource,
        "deny",
        requested=requested,
        reasons=list(decision.reasons),
    )


def query_event(ctx: AccessContext, resource: str, rows: int, **ids: Any) -> dict[str, Any]:
    """Audit payload for rows actually read; `ids` carries record_ids, item_ids..."""
    return event(ctx.username, "query", resource, "allow", rows=int(rows), **ids)

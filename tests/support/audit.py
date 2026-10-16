"""Audit helpers: read the trail through GET /audit, or one event straight from the chain."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from support.http import auth_header


def audit_events(client, username: str = "group.audit", limit: int = 200) -> list[dict]:
    response = client.get(f"/api/v1/audit?limit={limit}", headers=auth_header(client, username))
    assert response.status_code == 200, response.text
    return response.json()


def latest_event(events: list[dict], **match) -> dict | None:
    for event in sorted(events, key=lambda item: item["seq"], reverse=True):
        if all(event["payload"].get(key) == value for key, value in match.items()):
            return event
    return None


def audit_tip(client) -> int:
    """Current newest audit seq: a watermark for 'what did this request write?'."""
    return max(event["seq"] for event in audit_events(client, limit=1))


def event_payload(engine: Engine, event_id: str) -> dict | None:
    """Resolve an audit_event_id straight from the chain (the viewer omits it)."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT payload FROM audit_events WHERE event_id = :id"), {"id": event_id}
        ).first()
    return dict(row[0]) if row is not None else None

"""Prefill audit tagging (scripts/prefill_cache.py sets AUDIT_SOURCE).

Events written while AUDIT_SOURCE is set carry a `source` field in their payload so an
auditor can tell prefill traffic from live demo traffic. The tag lives in the audit
payload only: the model prompt and the cache key must be identical with and without it,
and the hash chain must stay valid.
"""

from __future__ import annotations

import pytest
from app.ai_gateway import LLMResponseCache
from app.ai_gateway.base import LLMResult
from app.audit.chain import verify_report
from app.config import Settings, get_settings
from pydantic import ValidationError
from sqlalchemy import text
from test_assistant_endpoints import _ask

QUESTION = "Show me the equipment currently awaiting maintenance"


class Capture:
    def __init__(self) -> None:
        self.requests: list = []

    def complete(self, request):
        self.requests.append(request)
        return LLMResult(text="explained", provider="p", model="m")


@pytest.fixture
def capture(monkeypatch, models):
    gateway = Capture()
    models(gateway)
    yield gateway
    monkeypatch.delenv("AUDIT_SOURCE", raising=False)
    get_settings.cache_clear()


def _set_source(monkeypatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("AUDIT_SOURCE", raising=False)
    else:
        monkeypatch.setenv("AUDIT_SOURCE", value)
    get_settings.cache_clear()


def _events_after(owner_engine, seq: int) -> list[dict]:
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT payload FROM audit_events WHERE seq > :seq ORDER BY seq"), {"seq": seq}
        ).all()
    return [dict(row[0]) for row in rows]


def _tip(owner_engine) -> int:
    with owner_engine.connect() as conn:
        return int(
            conn.execute(text("SELECT coalesce(max(seq), 0) FROM audit_events")).scalar_one()
        )


def test_prefill_events_are_tagged_and_prompts_are_not_affected(
    client, capture, owner_engine, monkeypatch
) -> None:
    _set_source(monkeypatch, None)
    start = _tip(owner_engine)
    assert _ask(client, "owner", QUESTION).status_code == 200
    plain_events = _events_after(owner_engine, start)
    assert plain_events and all("source" not in event for event in plain_events)

    _set_source(monkeypatch, "prefill")
    start = _tip(owner_engine)
    assert _ask(client, "owner", QUESTION).status_code == 200
    tagged_events = _events_after(owner_engine, start)
    assert tagged_events and all(event.get("source") == "prefill" for event in tagged_events)

    first, second = capture.requests
    assert first == second
    assert LLMResponseCache.key(first) == LLMResponseCache.key(second)
    assert "prefill" not in second.messages[-1].text
    assert "prefill" not in (second.system or "")

    assert verify_report(owner_engine)["valid"] is True


def test_audit_source_accepts_only_known_tags(monkeypatch) -> None:
    for value in ("prefill", "prefill-verify"):
        monkeypatch.setenv("AUDIT_SOURCE", value)
        assert Settings().audit_source == value
    monkeypatch.setenv("AUDIT_SOURCE", "free-text-label")
    with pytest.raises(ValidationError):
        Settings()

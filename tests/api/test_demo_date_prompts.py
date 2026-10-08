"""DEMO_DATE and the cache key (docs/DEMO_SCOPE.md).

The data-pathway prompt is derived from the rows a tool returns, and the rows
depend on a date cutoff. Pinned, the prompt and cache key do not move when the
clock does; unpinned, they do once a record crosses the cutoff, which is exactly
why the pin exists. DEMO_DATE must not leak into audit timestamps. The clock is
injected; the seeded dates are read back from the database, not assumed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from app import clock
from app.ai_gateway import LLMResponseCache
from app.ai_gateway.base import LLMResult
from app.config import get_settings
from sqlalchemy import text
from test_assistant_endpoints import _ask

QUESTION = "Show me the equipment currently awaiting maintenance"
REC_011_OFFSET = -12  # app.seed: REC-011 is due 12 days before the seed day
REC_017_OFFSET = 90  # due in 90 days: outside the 30-day window on the seed day
WINDOW_DAYS = 30


class Capture:
    def __init__(self) -> None:
        self.requests: list = []

    def complete(self, request):
        self.requests.append(request)
        return LLMResult(text="explained", provider="p", model="m")


@pytest.fixture
def seed_day(owner_engine, seeded) -> date:
    with owner_engine.connect() as conn:
        due = conn.execute(
            text(
                "SELECT data->>'maintenance_due_date' FROM canonical_records"
                " WHERE source_ref = 'REC-011'"
            )
        ).scalar_one()
    return date.fromisoformat(due) - timedelta(days=REC_011_OFFSET)


@pytest.fixture
def setup(monkeypatch, models, seed_day):
    capture = Capture()
    models(capture)
    state = {"today": seed_day}
    monkeypatch.setattr(clock, "real_today", lambda: state["today"])

    def pin(value: str | None) -> None:
        if value is None:
            monkeypatch.delenv("DEMO_DATE", raising=False)
        else:
            monkeypatch.setenv("DEMO_DATE", value)
        get_settings.cache_clear()

    yield capture, state, pin
    monkeypatch.delenv("DEMO_DATE", raising=False)
    get_settings.cache_clear()


def _key(capture: Capture, client, user: str = "a.bello") -> str:
    before = len(capture.requests)
    assert _ask(client, user, QUESTION).status_code == 200
    assert len(capture.requests) == before + 1
    return LLMResponseCache.key(capture.requests[-1])


def test_pinned_prompt_and_key_survive_the_clock_moving(client, setup, seed_day) -> None:
    capture, state, pin = setup
    pin(seed_day.isoformat())
    baseline = _key(capture, client)
    for days in (1, 5):
        state["today"] = seed_day + timedelta(days=days)
        assert _key(capture, client) == baseline, f"key moved with the clock +{days}d"
    assert capture.requests[0].messages == capture.requests[-1].messages


def test_unpinned_set_changes_when_a_record_crosses_the_cutoff(client, setup, seed_day) -> None:
    capture, state, pin = setup
    pin(None)
    baseline = _key(capture, client)
    state["today"] = seed_day + timedelta(days=1)
    assert _key(capture, client) == baseline  # nothing crosses the cutoff in a day
    state["today"] = seed_day + timedelta(days=REC_017_OFFSET - WINDOW_DAYS + 5)
    assert _key(capture, client) != baseline
    assert "REC-017" in capture.requests[-1].messages[-1].text


def test_demo_date_does_not_touch_the_real_clock(client, setup, owner_engine) -> None:
    capture, state, pin = setup
    pin("2020-01-01")
    before = datetime.now(UTC)
    login = client.post(
        "/api/v1/auth/login", json={"username": "a.bello", "password": "Demo!Gateway2026"}
    )
    assert login.status_code == 200
    with owner_engine.connect() as conn:
        created, stamp = conn.execute(
            text(
                "SELECT created_at, payload->>'timestamp' FROM audit_events"
                " ORDER BY seq DESC LIMIT 1"
            )
        ).one()
    assert created >= before - timedelta(seconds=5)
    assert datetime.fromisoformat(stamp) >= before - timedelta(seconds=5)

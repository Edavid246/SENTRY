"""DEMO_DATE: one anchor for the seed offsets and the data-tool cutoffs (app/clock.py).

The clock is injected (app.clock.real_today), so nothing here depends on the real date.
"""

from __future__ import annotations

from datetime import date

import pytest
from app import clock, seed
from app.config import Settings, get_settings
from pydantic import ValidationError


@pytest.fixture
def real_clock(monkeypatch):
    """Inject the 'real' calendar date; tests move it through the returned dict."""
    state = {"today": date(2030, 3, 1)}
    monkeypatch.setattr(clock, "real_today", lambda: state["today"])
    return state


@pytest.fixture
def pin(monkeypatch):
    def apply(value: str | None) -> None:
        if value is None:
            monkeypatch.delenv("DEMO_DATE", raising=False)
        else:
            monkeypatch.setenv("DEMO_DATE", value)
        get_settings.cache_clear()

    yield apply
    monkeypatch.delenv("DEMO_DATE", raising=False)
    get_settings.cache_clear()


def test_unset_means_the_live_clock(real_clock, pin) -> None:
    pin(None)
    assert clock.demo_today() == date(2030, 3, 1)
    real_clock["today"] = date(2030, 3, 6)
    assert clock.demo_today() == date(2030, 3, 6)


def test_pinned_date_ignores_the_live_clock(real_clock, pin) -> None:
    pin("2026-10-07")
    for moved in (date(2030, 3, 1), date(2030, 3, 2), date(2030, 3, 6)):
        real_clock["today"] = moved
        assert clock.demo_today() == date(2026, 10, 7)


def test_seed_offsets_follow_the_one_anchor(real_clock, pin) -> None:
    pin("2026-10-07")
    assert seed._days_from_today(0) == "2026-10-07"
    assert seed._days_from_today(-5) == "2026-10-02"
    pin(None)
    assert seed._days_from_today(10) == "2030-03-11"


def test_demo_date_is_refused_outside_the_dev_profile(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_DATE", "2026-10-07")
    assert Settings().demo_date == date(2026, 10, 7)  # dev is the default profile
    monkeypatch.setenv("APP_PROFILE", "onprem")
    with pytest.raises(ValidationError, match="DEMO_DATE"):
        Settings()

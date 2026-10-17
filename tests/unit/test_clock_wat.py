"""WAT display labels (app/clock.py): storage stays UTC, people read West Africa Time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app import clock


def test_wat_label_is_utc_plus_one():
    assert clock.wat_label(datetime(2026, 10, 17, 10, 5, tzinfo=UTC)) == "2026-10-17 11:05 WAT"


def test_wat_label_rolls_the_date_over_at_midnight():
    assert clock.wat_label(datetime(2026, 12, 31, 23, 30, tzinfo=UTC)) == "2027-01-01 00:30 WAT"


def test_wat_label_converts_from_any_offset():
    moment = datetime(2026, 10, 17, 13, 0, tzinfo=timezone(timedelta(hours=3)))
    assert clock.wat_label(moment) == "2026-10-17 11:00 WAT"


def test_wat_has_no_daylight_saving():
    winter = clock.wat_label(datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
    summer = clock.wat_label(datetime(2026, 7, 15, 12, 0, tzinfo=UTC))
    assert winter.endswith("13:00 WAT") and summer.endswith("13:00 WAT")


def test_storage_helper_is_still_utc():
    assert datetime.fromisoformat(clock.utc_now_iso()).utcoffset() == timedelta(0)

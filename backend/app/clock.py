"""The demo date anchor (DEMO_DATE), and the real-clock timestamp helper.

DEMO_DATE pins the *business* date used by exactly two things: the seed's
date offsets and the data-tool cutoffs ("due within 30 days", "expired").
Together they decide which records reach a model prompt, so pinning both keeps
the prefilled LLM cache valid on any day (docs/DEMO_SCOPE.md).

It deliberately does NOT touch the real clock: audit timestamps, token
issue/expiry, created_at and retrieved_at never read the demo date.
`utc_now_iso` is the real clock and ignores DEMO_DATE. Unset (the default)
means the live date. Settings refuse DEMO_DATE outside the dev profile.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

UTC_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
"""Fixed-width UTC timestamp; such strings order correctly as text."""

WAT = timezone(timedelta(hours=1), "WAT")
"""West Africa Time, UTC+1 all year (no daylight saving). Display only: storage stays UTC."""


def utc_now_iso() -> str:
    """The real time now, ISO 8601 in UTC (audit timestamps, `generated_at`)."""
    return datetime.now(UTC).isoformat()


def wat_label(moment: datetime) -> str:
    """An aware datetime as "YYYY-MM-DD HH:MM WAT", for text people read (report exports)."""
    return moment.astimezone(WAT).strftime("%Y-%m-%d %H:%M WAT")


def wat_now_label() -> str:
    """The real time now as a WAT display label."""
    return wat_label(datetime.now(UTC))


def real_today() -> date:
    """The real calendar date; tests replace this to inject a clock."""
    return date.today()


def demo_today() -> date:
    from app.config import get_settings

    pinned = get_settings().demo_date
    return pinned if pinned is not None else real_today()


def demo_now() -> datetime:
    """Noon UTC on the demo date: the fixed 'now' for hour-based windows.

    Detection timestamps are seeded as hour offsets from this instant and the
    detection tool measures "last 48 hours" back from it, so a pinned DEMO_DATE
    reproduces the same sets (and the same cached prompts) on any day.
    """
    return datetime.combine(demo_today(), time(12, 0), tzinfo=UTC)

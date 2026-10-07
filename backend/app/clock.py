"""The demo date anchor (DEMO_DATE).

DEMO_DATE pins the *business* date used by exactly two things: the seed's
date offsets and the data-tool cutoffs ("due within 30 days", "expired").
Together they decide which records reach a model prompt, so pinning both keeps
the prefilled LLM cache valid on any day (docs/DEMO_SCOPE.md).

It deliberately does NOT touch the real clock: audit timestamps, token
issue/expiry, created_at and retrieved_at never read this module. Unset (the
default) means the live date. Settings refuse DEMO_DATE outside the dev profile.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time


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

"""UAS and surveillance tools: missions, fleet, sensors, detections."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from app.authz.scope import Scope
from app.clock import UTC_TS_FORMAT, demo_now, demo_today
from app.connectors.base import SourceRecord
from app.data_queries.tools.base import (
    MAX_WITHIN_DAYS,
    Table,
    bounded_int,
    checked_state,
    choice,
    columns,
    given,
    matching,
    number,
    search,
    tool,
)

MAX_PERIOD_HOURS = 24 * 30
DEFAULT_DETECTION_HOURS = 48
DEFAULT_MISSION_DAYS = 30
MISSION_STATUSES = ("completed", "cancelled")
_SITE_RE = re.compile(r"^(?:DEP-[A-Z0-9]{1,8}|UAS-HANGAR)$")


@tool("status", "period_days", "state")
def uas_missions(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """UAS missions dated in the last `period_days` (default 30), optionally by status."""
    status = choice(params.get("status"), "status", MISSION_STATUSES)
    state = checked_state(params.get("state"))
    period_days = bounded_int(
        params.get("period_days", DEFAULT_MISSION_DAYS), "period_days", 1, MAX_WITHIN_DAYS
    )
    today = demo_today()
    start = (today - timedelta(days=period_days)).isoformat()
    found = search(scope, "Mission", unit_path, date_field="mission_date", on_or_before=today)
    records = [
        r
        for r in found
        if r.data["mission_date"] >= start
        and (status is None or r.data.get("status") == status)
        and (state is None or r.data.get("state") == state)
    ]
    records.sort(key=lambda r: (r.data["mission_date"], r.source_ref), reverse=True)
    return Table(
        records,
        columns("mission", "platform", "status", "mission_date", "area", "reason"),
        {"period_days": period_days, **given(status=status, state=state)},
    )


@tool("site", "period_hours", "state")
def detections_near_site(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Surveillance detections at a site (depot or facility) in the last `period_hours`."""
    site = matching(params.get("site"), _SITE_RE, "site must look like DEP-B4 or UAS-HANGAR")
    state = checked_state(params.get("state"))
    period_hours = bounded_int(
        params.get("period_hours", DEFAULT_DETECTION_HOURS), "period_hours", 1, MAX_PERIOD_HOURS
    )
    now = demo_now()
    start = (now - timedelta(hours=period_hours)).strftime(UTC_TS_FORMAT)
    end = now.strftime(UTC_TS_FORMAT)
    # Fixed-width UTC timestamps order correctly as text; compared on authorized rows only.
    records = [
        r
        for r in search(scope, "Detection", unit_path)
        if start <= str(r.data.get("observed_at", "")) <= end
        and (site is None or r.data.get("site") == site)
        and (state is None or r.data.get("state") == state)
    ]
    records.sort(key=lambda r: (r.data["observed_at"], r.source_ref), reverse=True)
    return Table(
        records,
        columns("observed_at", "site", "sensor_id", "object_type", "confidence"),
        {"period_hours": period_hours, **given(site=site, state=state)},
    )


@tool()
def uas_fleet(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Aircraft (equipment that logs flight hours), with hours left to the next service."""
    found = search(scope, "Equipment", unit_path)
    records = [r for r in found if number(r.data.get("flight_hours")) is not None]
    records.sort(key=lambda r: (r.data["name"], r.source_ref))

    def hours_left(record: SourceRecord) -> float | None:
        interval = number(record.data.get("service_interval_hours"))
        return None if interval is None else interval - record.data["flight_hours"]

    return Table(
        records,
        {
            **columns("name", "status", "flight_hours", "service_interval_hours", "next_service"),
            "hours_to_service": hours_left,
        },
    )


@tool()
def sensors_status(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Every sensor the caller may see, with its site and whether it is online."""
    records = search(scope, "Sensor", unit_path)
    records.sort(key=lambda r: (r.data["site"], r.data["sensor_id"], r.source_ref))
    return Table(records, columns("sensor_id", "site", "kind", "status"))

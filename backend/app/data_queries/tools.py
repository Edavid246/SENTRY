"""Typed, parameterized query tools (SPEC 8.2 data pathway).

Each tool validates its parameters, then asks the adapter for records on the
caller's authorized Scope; it never builds SQL and never touches the record
tables (the adapter does, with the authorization filter inside the query). The
output is a deterministic table plus the source records behind it: `_table`
projects the records through the tool's columns, so a column and its row key
can never disagree.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.authz.context import AccessContext
from app.authz.scope import Scope
from app.clock import UTC_TS_FORMAT, demo_now, demo_today
from app.connectors import get_adapter
from app.connectors.base import RecordFilter, SourceRecord
from app.correlation.store import list_findings
from app.data_queries.errors import ToolParamError

MAX_WITHIN_DAYS = 365
MAX_PERIOD_HOURS = 24 * 30
DEFAULT_DETECTION_HOURS = 48
DEFAULT_MISSION_DAYS = 30
MISSION_STATUSES = frozenset({"completed", "cancelled"})
DEFAULT_PERIOD_DAYS = 90  # one quarter
_DEPOT_RE = re.compile(r"^DEP-[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8})?$")
_SITE_RE = re.compile(r"^(?:DEP-[A-Z0-9]{1,8}|UAS-HANGAR)$")
_UNIT_PATH_RE = re.compile(r"^/(?:[a-z0-9-]+/)+$")

Column = Callable[[SourceRecord], Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool: str
    params: dict[str, Any]
    columns: tuple[str, ...]
    rows: list[dict[str, Any]]
    records: tuple[SourceRecord, ...]


def _source_ref(record: SourceRecord) -> str:
    return record.source_ref


def _unit_path(record: SourceRecord) -> str:
    return record.unit_path


def _field(name: str) -> Column:
    return lambda record: record.data.get(name)


def _fields(*names: str) -> dict[str, Column]:
    return {name: _field(name) for name in names}


def _table(
    tool: str,
    params: dict[str, Any],
    records: list[SourceRecord],
    columns: dict[str, Column],
) -> ToolResult:
    return ToolResult(
        tool=tool,
        params=params,
        columns=tuple(columns),
        rows=[{name: value(record) for name, value in columns.items()} for record in records],
        records=tuple(records),
    )


def _given(**optional: Any) -> dict[str, Any]:
    """The optional parameters that were actually given (for the echoed params)."""
    return {name: value for name, value in optional.items() if value is not None}


def _check_names(params: Mapping[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(str(name) for name in params if name not in allowed)
    if unknown:
        raise ToolParamError(f"unknown parameter(s): {', '.join(unknown)[:80]}")


def _resolve_unit_path(ctx: AccessContext, value: Any) -> str:
    """Default to the caller's unit; an explicit one must be at or below it."""
    if value is None:
        return ctx.unit_path
    if not isinstance(value, str):
        raise ToolParamError("unit_path must be a string")
    candidate = value if value.endswith("/") else value + "/"
    if len(candidate) > 200 or not _UNIT_PATH_RE.match(candidate):
        raise ToolParamError("unit_path is not a valid unit path")
    if not candidate.startswith(ctx.unit_path):
        raise ToolParamError("unit_path is outside your unit scope")
    return candidate


def _bounded_int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolParamError(f"{name} must be an integer")
    if not low <= value <= high:
        raise ToolParamError(f"{name} must be between {low} and {high}")
    return value


def _pattern(value: Any, pattern: re.Pattern[str], message: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not pattern.match(value):
        raise ToolParamError(message)
    return value


def _number(value: Any) -> float | None:
    return None if isinstance(value, bool) or not isinstance(value, int | float) else value


def equipment_due_for_maintenance(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    _check_names(params, frozenset({"unit_path", "within_days"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    within_days = _bounded_int(params.get("within_days", 30), "within_days", 0, MAX_WITHIN_DAYS)
    records = get_adapter().search(
        scope,
        RecordFilter(
            entity_type="Equipment",
            unit_path=unit_path,
            date_field="maintenance_due_date",
            on_or_before=demo_today() + timedelta(days=within_days),
        ),
    )
    records.sort(key=lambda r: (r.data["maintenance_due_date"], r.source_ref))
    return _table(
        "equipment_due_for_maintenance",
        {"unit_path": unit_path, "within_days": within_days},
        records,
        {
            "id": _source_ref,
            **_fields("name", "type", "status", "maintenance_due_date", "location"),
            "unit_path": _unit_path,
        },
    )


def expired_certifications(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    _check_names(params, frozenset({"unit_path"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    records = get_adapter().search(
        scope,
        RecordFilter(
            entity_type="Qualification",
            unit_path=unit_path,
            date_field="expires",
            on_or_before=demo_today() - timedelta(days=1),
        ),
    )
    records.sort(key=lambda r: (r.data["expires"], r.source_ref))
    return _table(
        "expired_certifications",
        {"unit_path": unit_path},
        records,
        {
            "id": _source_ref,
            **_fields("name", "rank", "certification"),
            "expired_date": _field("expires"),
            "unit_path": _unit_path,
        },
    )


def stock_below_threshold(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    _check_names(params, frozenset({"unit_path", "depot"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    depot = _pattern(params.get("depot"), _DEPOT_RE, "depot must look like DEP-B2")
    found = get_adapter().search(scope, RecordFilter(entity_type="StockItem", unit_path=unit_path))
    # Quantities are compared here, on rows the adapter already authorized.
    records = [
        record
        for record in found
        if (qty := _number(record.data.get("quantity"))) is not None
        and (thr := _number(record.data.get("threshold"))) is not None
        and qty < thr
        and (depot is None or record.data.get("depot") == depot)
    ]
    records.sort(key=lambda r: (r.data["quantity"] - r.data["threshold"], r.source_ref))
    return _table(
        "stock_below_threshold",
        {"unit_path": unit_path, **_given(depot=depot)},
        records,
        {
            "id": _source_ref,
            **_fields("item", "depot", "quantity", "threshold"),
            "shortfall": lambda r: r.data["threshold"] - r.data["quantity"],
            "unit_path": _unit_path,
        },
    )


def correlation_findings(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """The correlation findings this caller may see (row filter + RLS in the query).

    Findings are produced by our own correlation job, not a source system, so this
    reads the findings store rather than an adapter. Each finding is wrapped as a
    record so the answer inherits its classification and compartments like any other.
    """
    _check_names(params, frozenset())
    records = [
        SourceRecord(
            source_ref=f.key,
            entity_type="Finding",
            source_system="correlation",
            data={"title": f.title, "summary": f.summary, "severity": f.severity},
            classification_code=f.classification_code,
            compartments=tuple(f.compartments),
            unit_path=f.unit_path,
            retrieved_at=f.created_at,
        )
        for f in list_findings(scope)
    ]
    return _table(
        "correlation_findings",
        {},
        records,
        {
            "id": _source_ref,
            **_fields("title", "severity"),
            "classification": lambda r: r.classification_code,
            "unit_path": _unit_path,
            "summary": _field("summary"),
        },
    )


def training_activity(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Training events that started in the last `period_days` (default one quarter)."""
    _check_names(params, frozenset({"unit_path", "period_days"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    period_days = _bounded_int(
        params.get("period_days", DEFAULT_PERIOD_DAYS), "period_days", 1, MAX_WITHIN_DAYS
    )
    today = demo_today()
    start = today - timedelta(days=period_days)
    found = get_adapter().search(
        scope, RecordFilter(entity_type="TrainingEvent", unit_path=unit_path)
    )

    def started(record: SourceRecord) -> date | None:
        try:
            return date.fromisoformat(str(record.data.get("start_date")))
        except ValueError:
            return None

    records = [r for r in found if (d := started(r)) is not None and start <= d <= today]
    records.sort(key=lambda r: (r.data["start_date"], r.source_ref), reverse=True)
    return _table(
        "training_activity",
        {"unit_path": unit_path, "period_days": period_days},
        records,
        {
            "id": _source_ref,
            **_fields("course", "start_date", "attendees"),
            "unit_path": _unit_path,
        },
    )


def uas_missions(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """UAS missions dated in the last `period_days` (default 30), optionally by status."""
    _check_names(params, frozenset({"unit_path", "status", "period_days"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    status = params.get("status")
    if status is not None and status not in MISSION_STATUSES:
        raise ToolParamError("status must be 'completed' or 'cancelled'")
    period_days = _bounded_int(
        params.get("period_days", DEFAULT_MISSION_DAYS), "period_days", 1, MAX_WITHIN_DAYS
    )
    today = demo_today()
    start = (today - timedelta(days=period_days)).isoformat()
    found = get_adapter().search(
        scope,
        RecordFilter(
            entity_type="Mission",
            unit_path=unit_path,
            date_field="mission_date",
            on_or_before=today,
        ),
    )
    records = [
        r
        for r in found
        if r.data["mission_date"] >= start and (status is None or r.data.get("status") == status)
    ]
    records.sort(key=lambda r: (r.data["mission_date"], r.source_ref), reverse=True)
    return _table(
        "uas_missions",
        {"unit_path": unit_path, "period_days": period_days, **_given(status=status)},
        records,
        {
            "id": _source_ref,
            **_fields("mission", "platform", "status", "mission_date", "area", "reason"),
            "unit_path": _unit_path,
        },
    )


def detections_near_site(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Surveillance detections at a site (depot or facility) in the last `period_hours`."""
    _check_names(params, frozenset({"unit_path", "site", "period_hours"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    site = _pattern(params.get("site"), _SITE_RE, "site must look like DEP-B4 or UAS-HANGAR")
    period_hours = _bounded_int(
        params.get("period_hours", DEFAULT_DETECTION_HOURS), "period_hours", 1, MAX_PERIOD_HOURS
    )
    now = demo_now()
    start = (now - timedelta(hours=period_hours)).strftime(UTC_TS_FORMAT)
    end = now.strftime(UTC_TS_FORMAT)
    found = get_adapter().search(scope, RecordFilter(entity_type="Detection", unit_path=unit_path))
    # Fixed-width UTC timestamps order correctly as text; compared on authorized rows only.
    records = [
        r
        for r in found
        if start <= str(r.data.get("observed_at", "")) <= end
        and (site is None or r.data.get("site") == site)
    ]
    records.sort(key=lambda r: (r.data["observed_at"], r.source_ref), reverse=True)
    return _table(
        "detections_near_site",
        {"unit_path": unit_path, "period_hours": period_hours, **_given(site=site)},
        records,
        {
            "id": _source_ref,
            **_fields("observed_at", "site", "sensor_id", "object_type", "confidence"),
            "unit_path": _unit_path,
        },
    )

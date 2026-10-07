"""Typed, parameterized query tools (SPEC 8.2 data pathway).

Each tool validates its parameters, then asks the adapter for records; it
never builds SQL and never touches the record tables (the adapter does, with
the authorization filter inside the query). The output is a deterministic
table plus the source records behind it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.engine import Connection

from app.authz.context import AccessContext
from app.clock import demo_today
from app.connectors.base import RecordFilter, SourceRecord
from app.connectors.demo import DemoReferenceAdapter
from app.correlation.store import list_findings
from app.data_queries.errors import ToolParamError

MAX_WITHIN_DAYS = 365
DEFAULT_PERIOD_DAYS = 90  # one quarter
_DEPOT_RE = re.compile(r"^DEP-[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8})?$")
_UNIT_PATH_RE = re.compile(r"^/(?:[a-z0-9-]+/)+$")
ADAPTER = DemoReferenceAdapter()


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool: str
    params: dict[str, Any]
    columns: tuple[str, ...]
    rows: list[dict[str, Any]]
    records: tuple[SourceRecord, ...]


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


def _resolve_within_days(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolParamError("within_days must be an integer")
    if not 0 <= value <= MAX_WITHIN_DAYS:
        raise ToolParamError(f"within_days must be between 0 and {MAX_WITHIN_DAYS}")
    return value


def equipment_due_for_maintenance(
    ctx: AccessContext, params: Mapping[str, Any], conn: Connection
) -> ToolResult:
    _check_names(params, frozenset({"unit_path", "within_days"}))
    unit_path = _resolve_unit_path(ctx, params.get("unit_path"))
    within_days = _resolve_within_days(params.get("within_days", 30))
    cutoff = demo_today() + timedelta(days=within_days)
    records = ADAPTER.search(
        conn,
        ctx,
        RecordFilter(
            entity_type="Equipment",
            unit_path=unit_path,
            date_field="maintenance_due_date",
            on_or_before=cutoff,
        ),
    )
    records.sort(key=lambda record: (record.data["maintenance_due_date"], record.source_ref))
    columns = (
        "id",
        "name",
        "type",
        "status",
        "maintenance_due_date",
        "location",
        "unit_path",
    )
    rows = [
        {
            "id": record.source_ref,
            "name": record.data.get("name"),
            "type": record.data.get("type"),
            "status": record.data.get("status"),
            "maintenance_due_date": record.data["maintenance_due_date"],
            "location": record.data.get("location"),
            "unit_path": record.unit_path,
        }
        for record in records
    ]
    return ToolResult(
        tool="equipment_due_for_maintenance",
        params={"unit_path": unit_path, "within_days": within_days},
        columns=columns,
        rows=rows,
        records=tuple(records),
    )


def expired_certifications(
    ctx: AccessContext, params: Mapping[str, Any], conn: Connection
) -> ToolResult:
    _check_names(params, frozenset({"unit_path"}))
    unit_path = _resolve_unit_path(ctx, params.get("unit_path"))
    records = ADAPTER.search(
        conn,
        ctx,
        RecordFilter(
            entity_type="Qualification",
            unit_path=unit_path,
            date_field="expires",
            on_or_before=demo_today() - timedelta(days=1),
        ),
    )
    records.sort(key=lambda record: (record.data["expires"], record.source_ref))
    columns = ("id", "name", "rank", "certification", "expired_date", "unit_path")
    rows = [
        {
            "id": record.source_ref,
            "name": record.data.get("name"),
            "rank": record.data.get("rank"),
            "certification": record.data.get("certification"),
            "expired_date": record.data["expires"],
            "unit_path": record.unit_path,
        }
        for record in records
    ]
    return ToolResult(
        tool="expired_certifications",
        params={"unit_path": unit_path},
        columns=columns,
        rows=rows,
        records=tuple(records),
    )


def _resolve_depot(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _DEPOT_RE.match(value):
        raise ToolParamError("depot must look like DEP-B2")
    return value


def _number(value: Any) -> float | None:
    return None if isinstance(value, bool) or not isinstance(value, int | float) else value


def stock_below_threshold(
    ctx: AccessContext, params: Mapping[str, Any], conn: Connection
) -> ToolResult:
    _check_names(params, frozenset({"unit_path", "depot"}))
    unit_path = _resolve_unit_path(ctx, params.get("unit_path"))
    depot = _resolve_depot(params.get("depot"))
    found = ADAPTER.search(conn, ctx, RecordFilter(entity_type="StockItem", unit_path=unit_path))
    # Quantities are compared here, on rows the adapter already authorized.
    records = [
        record
        for record in found
        if (qty := _number(record.data.get("quantity"))) is not None
        and (thr := _number(record.data.get("threshold"))) is not None
        and qty < thr
        and (depot is None or record.data.get("depot") == depot)
    ]
    records.sort(
        key=lambda r: (r.data["quantity"] - r.data["threshold"], r.source_ref),
    )
    columns = ("id", "item", "depot", "quantity", "threshold", "shortfall", "unit_path")
    rows = [
        {
            "id": record.source_ref,
            "item": record.data.get("item"),
            "depot": record.data.get("depot"),
            "quantity": record.data["quantity"],
            "threshold": record.data["threshold"],
            "shortfall": record.data["threshold"] - record.data["quantity"],
            "unit_path": record.unit_path,
        }
        for record in records
    ]
    return ToolResult(
        tool="stock_below_threshold",
        params={"unit_path": unit_path, **({"depot": depot} if depot else {})},
        columns=columns,
        rows=rows,
        records=tuple(records),
    )


def correlation_findings(
    ctx: AccessContext, params: Mapping[str, Any], conn: Connection
) -> ToolResult:
    """The correlation findings this caller may see (row filter + RLS in the query).

    Findings are produced by our own correlation job, not a source system, so this
    reads the findings store rather than an adapter. Each finding is wrapped as a
    record so the answer inherits its classification and compartments like any other.
    """
    _check_names(params, frozenset())
    findings = list_findings(conn, ctx)
    records = tuple(
        SourceRecord(
            source_ref=f.key,
            entity_type="Finding",
            source_system="correlation",
            data={"title": f.title, "summary": f.summary, "severity": f.severity},
            classification_code=f.classification_code,
            compartments=tuple(f.compartments),
            unit_path=f.unit_path,
            retrieved_at=datetime.fromisoformat(f.created_at),
        )
        for f in findings
    )
    columns = ("id", "title", "severity", "classification", "unit_path", "summary")
    rows = [
        {
            "id": f.key,
            "title": f.title,
            "severity": f.severity,
            "classification": f.classification_code,
            "unit_path": f.unit_path,
            "summary": f.summary,
        }
        for f in findings
    ]
    return ToolResult(
        tool="correlation_findings", params={}, columns=columns, rows=rows, records=records
    )


def training_activity(
    ctx: AccessContext, params: Mapping[str, Any], conn: Connection
) -> ToolResult:
    """Training events that started in the last `period_days` (default one quarter)."""
    _check_names(params, frozenset({"unit_path", "period_days"}))
    unit_path = _resolve_unit_path(ctx, params.get("unit_path"))
    period_days = params.get("period_days", DEFAULT_PERIOD_DAYS)
    if isinstance(period_days, bool) or not isinstance(period_days, int):
        raise ToolParamError("period_days must be an integer")
    if not 1 <= period_days <= MAX_WITHIN_DAYS:
        raise ToolParamError(f"period_days must be between 1 and {MAX_WITHIN_DAYS}")
    today = demo_today()
    start = today - timedelta(days=period_days)
    found = ADAPTER.search(
        conn, ctx, RecordFilter(entity_type="TrainingEvent", unit_path=unit_path)
    )

    def started(record: SourceRecord) -> date | None:
        try:
            return date.fromisoformat(str(record.data.get("start_date")))
        except ValueError:
            return None

    records = [r for r in found if (d := started(r)) is not None and start <= d <= today]
    records.sort(key=lambda r: (r.data["start_date"], r.source_ref), reverse=True)
    columns = ("id", "course", "start_date", "attendees", "unit_path")
    rows = [
        {
            "id": r.source_ref,
            "course": r.data.get("course"),
            "start_date": r.data["start_date"],
            "attendees": r.data.get("attendees"),
            "unit_path": r.unit_path,
        }
        for r in records
    ]
    return ToolResult(
        tool="training_activity",
        params={"unit_path": unit_path, "period_days": period_days},
        columns=columns,
        rows=rows,
        records=tuple(records),
    )

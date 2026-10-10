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
from app.geo.states import check_state

MAX_WITHIN_DAYS = 365
MAX_PERIOD_HOURS = 24 * 30
DEFAULT_DETECTION_HOURS = 48
DEFAULT_MISSION_DAYS = 30
MISSION_STATUSES = frozenset({"completed", "cancelled"})
DEFAULT_PERIOD_DAYS = 90  # one quarter
_DEPOT_RE = re.compile(r"^DEP-[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8})?$")
_SITE_RE = re.compile(r"^(?:DEP-[A-Z0-9]{1,8}|UAS-HANGAR)$")
_CLIENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .&-]{0,39}$")
CONTRACT_STATUSES = frozenset({"active", "at_risk", "completed"})
_SERIAL_RE = re.compile(r"^[A-Z]{2,4}(?:-[A-Z]{2,4})?-\d{3,5}$")
_CASE_RE = re.compile(r"^FR-\d{4}-\d{3}$")
_EVIDENCE_RE = re.compile(r"^EV-\d{3}-\d{2}$")
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


def _state(value: Any) -> str | None:
    try:
        return check_state(value)
    except ValueError as exc:
        raise ToolParamError(str(exc)) from None


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
    _check_names(params, frozenset({"unit_path", "status", "period_days", "state"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    status = params.get("status")
    if status is not None and status not in MISSION_STATUSES:
        raise ToolParamError("status must be 'completed' or 'cancelled'")
    state = _state(params.get("state"))
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
        if r.data["mission_date"] >= start
        and (status is None or r.data.get("status") == status)
        and (state is None or r.data.get("state") == state)
    ]
    records.sort(key=lambda r: (r.data["mission_date"], r.source_ref), reverse=True)
    return _table(
        "uas_missions",
        {"unit_path": unit_path, "period_days": period_days, **_given(status=status, state=state)},
        records,
        {
            "id": _source_ref,
            **_fields("mission", "platform", "status", "mission_date", "area", "reason"),
            "unit_path": _unit_path,
        },
    )


def detections_near_site(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Surveillance detections at a site (depot or facility) in the last `period_hours`."""
    _check_names(params, frozenset({"unit_path", "site", "period_hours", "state"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    site = _pattern(params.get("site"), _SITE_RE, "site must look like DEP-B4 or UAS-HANGAR")
    state = _state(params.get("state"))
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
        and (state is None or r.data.get("state") == state)
    ]
    records.sort(key=lambda r: (r.data["observed_at"], r.source_ref), reverse=True)
    return _table(
        "detections_near_site",
        {"unit_path": unit_path, "period_hours": period_hours, **_given(site=site, state=state)},
        records,
        {
            "id": _source_ref,
            **_fields("observed_at", "site", "sensor_id", "object_type", "confidence"),
            "unit_path": _unit_path,
        },
    )


def deliveries_overdue(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Deliveries past their due date and not yet delivered, optionally for one client."""
    _check_names(params, frozenset({"unit_path", "client"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    client = _pattern(params.get("client"), _CLIENT_RE, "client is not a valid client name")
    today = demo_today()
    found = get_adapter().search(
        scope,
        RecordFilter(
            entity_type="Delivery",
            unit_path=unit_path,
            date_field="due_date",
            on_or_before=today - timedelta(days=1),
        ),
    )
    records = [
        r
        for r in found
        if r.data.get("status") != "delivered"
        and (client is None or r.data.get("client") == client)
    ]
    records.sort(key=lambda r: (r.data["due_date"], r.source_ref))
    return _table(
        "deliveries_overdue",
        {"unit_path": unit_path, **_given(client=client)},
        records,
        {
            "id": _source_ref,
            **_fields("delivery_ref", "contract_ref", "client", "item", "quantity", "due_date"),
            "days_overdue": lambda r: (today - date.fromisoformat(r.data["due_date"])).days,
            "status": _field("status"),
            "unit_path": _unit_path,
        },
    )


def contracts_status(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Contracts the caller may see, optionally for one client and/or one status."""
    _check_names(params, frozenset({"unit_path", "client", "status"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    client = _pattern(params.get("client"), _CLIENT_RE, "client is not a valid client name")
    status = params.get("status")
    if status is not None and status not in CONTRACT_STATUSES:
        raise ToolParamError("status must be 'active', 'at_risk' or 'completed'")
    found = get_adapter().search(scope, RecordFilter(entity_type="Contract", unit_path=unit_path))
    records = [
        r
        for r in found
        if (client is None or r.data.get("client") == client)
        and (status is None or r.data.get("status") == status)
    ]
    records.sort(key=lambda r: (r.data["contract_ref"], r.source_ref))
    return _table(
        "contracts_status",
        {"unit_path": unit_path, **_given(client=client, status=status)},
        records,
        {
            "id": _source_ref,
            **_fields("contract_ref", "client", "subject", "status", "end_date", "value_musd"),
            "unit_path": _unit_path,
        },
    )


def serial_trace(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """One serial number's production run, QC state and delivery. A serial the caller may
    not see is indistinguishable from one that does not exist: the result is simply empty."""
    _check_names(params, frozenset({"unit_path", "serial"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    serial = params.get("serial")
    if not isinstance(serial, str) or not _SERIAL_RE.match(serial):
        raise ToolParamError("serial is not a valid serial number")
    found = get_adapter().search(scope, RecordFilter(entity_type="SerialUnit", unit_path=unit_path))
    records = [r for r in found if r.data.get("serial") == serial]
    return _table(
        "serial_trace",
        {"unit_path": unit_path, "serial": serial},
        records,
        {
            "id": _source_ref,
            **_fields("serial", "product", "run_ref", "qc_status", "delivered_to", "delivery_ref"),
            "unit_path": _unit_path,
        },
    )


def production_qc_holds(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Production runs on QC hold, with how many visible serials each affects."""
    _check_names(params, frozenset({"unit_path"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    adapter = get_adapter()
    runs = adapter.search(scope, RecordFilter(entity_type="ProductionRun", unit_path=unit_path))
    serials = adapter.search(scope, RecordFilter(entity_type="SerialUnit", unit_path=unit_path))
    held = sorted(
        (r for r in runs if r.data.get("qc_status") == "hold"),
        key=lambda r: (r.data["run_ref"], r.source_ref),
    )
    affected = {
        r.data["run_ref"]: sum(1 for s in serials if s.data.get("run_ref") == r.data["run_ref"])
        for r in held
    }
    return _table(
        "production_qc_holds",
        {"unit_path": unit_path},
        held,
        {
            "id": _source_ref,
            **_fields("run_ref", "product", "quantity", "qc_status", "hold_reason"),
            "serials_traced": lambda r: affected[r.data["run_ref"]],
            "unit_path": _unit_path,
        },
    )


def production_runs(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Every production run the caller may see, with how many visible serials each traces to."""
    _check_names(params, frozenset({"unit_path"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    adapter = get_adapter()
    runs = adapter.search(scope, RecordFilter(entity_type="ProductionRun", unit_path=unit_path))
    serials = adapter.search(scope, RecordFilter(entity_type="SerialUnit", unit_path=unit_path))
    runs.sort(key=lambda r: (r.data["run_ref"], r.source_ref))
    traced = {
        r.data["run_ref"]: sum(1 for s in serials if s.data.get("run_ref") == r.data["run_ref"])
        for r in runs
    }
    return _table(
        "production_runs",
        {"unit_path": unit_path},
        runs,
        {
            "id": _source_ref,
            **_fields("run_ref", "product", "quantity", "qc_status", "hold_reason"),
            "serials_traced": lambda r: traced[r.data["run_ref"]],
            "unit_path": _unit_path,
        },
    )


def uas_fleet(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Aircraft (equipment that logs flight hours), with hours left to the next service."""
    _check_names(params, frozenset({"unit_path"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    found = get_adapter().search(scope, RecordFilter(entity_type="Equipment", unit_path=unit_path))
    records = [r for r in found if _number(r.data.get("flight_hours")) is not None]
    records.sort(key=lambda r: (r.data["name"], r.source_ref))

    def hours_left(record: SourceRecord) -> float | None:
        interval = _number(record.data.get("service_interval_hours"))
        return None if interval is None else interval - record.data["flight_hours"]

    return _table(
        "uas_fleet",
        {"unit_path": unit_path},
        records,
        {
            "id": _source_ref,
            **_fields("name", "status", "flight_hours", "service_interval_hours", "next_service"),
            "hours_to_service": hours_left,
            "unit_path": _unit_path,
        },
    )


def sensors_status(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Every sensor the caller may see, with its site and whether it is online."""
    _check_names(params, frozenset({"unit_path"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    records = get_adapter().search(scope, RecordFilter(entity_type="Sensor", unit_path=unit_path))
    records.sort(key=lambda r: (r.data["site"], r.data["sensor_id"], r.source_ref))
    return _table(
        "sensors_status",
        {"unit_path": unit_path},
        records,
        {
            "id": _source_ref,
            **_fields("sensor_id", "site", "kind", "status"),
            "unit_path": _unit_path,
        },
    )


def field_personnel(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Personnel certifications the caller may see, each marked valid or expired."""
    _check_names(params, frozenset({"unit_path"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    records = get_adapter().search(
        scope, RecordFilter(entity_type="Qualification", unit_path=unit_path)
    )
    records.sort(key=lambda r: (str(r.data.get("name", "")), r.data["expires"], r.source_ref))
    today = demo_today().isoformat()
    return _table(
        "field_personnel",
        {"unit_path": unit_path},
        records,
        {
            "id": _source_ref,
            **_fields("name", "rank", "certification", "expires"),
            "status": lambda r: "expired" if r.data["expires"] < today else "valid",
            "unit_path": _unit_path,
        },
    )


def _custody_chains(events: list[SourceRecord]) -> dict[str, list[tuple[SourceRecord, str | None]]]:
    """Each evidence item's visible custody events in date order, each with the holder it should
    have been taken from (the previous event's `to_holder`) when the record says otherwise.

    A break is a transfer whose `from_holder` is not whoever last received the item. Worked out
    from the events the caller can see: a trail with a hidden event in the middle would read as
    broken, so the forensic records of one case share one label (checked by a test).
    """
    by_item: dict[str, list[SourceRecord]] = {}
    for event in events:
        by_item.setdefault(str(event.data["evidence_ref"]), []).append(event)
    chains: dict[str, list[tuple[SourceRecord, str | None]]] = {}
    for evidence_ref, items in by_item.items():
        items.sort(key=lambda e: (e.data["event_date"], e.source_ref))
        chain: list[tuple[SourceRecord, str | None]] = []
        previous: SourceRecord | None = None
        for event in items:
            expected = None
            if previous is not None and event.data["from_holder"] != previous.data["to_holder"]:
                expected = str(previous.data["to_holder"])
            chain.append((event, expected))
            previous = event
        chains[evidence_ref] = chain
    return chains


Chains = dict[str, list[tuple[SourceRecord, str | None]]]


def _forensics(scope: Scope, unit_path: str) -> tuple[list[SourceRecord], Chains]:
    adapter = get_adapter()
    evidence = adapter.search(scope, RecordFilter(entity_type="EvidenceItem", unit_path=unit_path))
    events = adapter.search(scope, RecordFilter(entity_type="CustodyEvent", unit_path=unit_path))
    return evidence, _custody_chains(events)


def forensic_cases(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Forensic cases, with how many evidence items and custody breaks the caller can see."""
    _check_names(params, frozenset({"unit_path", "case_ref"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    case_ref = _pattern(params.get("case_ref"), _CASE_RE, "case_ref must look like FR-2026-014")
    cases = get_adapter().search(scope, RecordFilter(entity_type="Case", unit_path=unit_path))
    cases = [c for c in cases if case_ref is None or c.data["case_ref"] == case_ref]
    evidence, chains = _forensics(scope, unit_path)
    cases.sort(key=lambda r: (r.data["state"] != "open", r.data["case_ref"]))
    items = {c.data["case_ref"]: 0 for c in cases}
    breaks = dict(items)
    for item in evidence:
        if item.data["case_ref"] in items:
            items[item.data["case_ref"]] += 1
    for chain in chains.values():
        for event, expected in chain:
            if expected is not None and event.data["case_ref"] in breaks:
                breaks[event.data["case_ref"]] += 1
    return _table(
        "forensic_cases",
        {"unit_path": unit_path, **_given(case_ref=case_ref)},
        cases,
        {
            "id": _source_ref,
            **_fields("case_ref", "title", "state", "opened", "lead_examiner"),
            "evidence_items": lambda r: items[r.data["case_ref"]],
            "custody_breaks": lambda r: breaks[r.data["case_ref"]],
            "unit_path": _unit_path,
        },
    )


def evidence_items(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Evidence items, with how many custody events and breaks each has."""
    _check_names(params, frozenset({"unit_path", "case_ref"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    case_ref = _pattern(params.get("case_ref"), _CASE_RE, "case_ref must look like FR-2026-014")
    evidence, chains = _forensics(scope, unit_path)
    records = [e for e in evidence if case_ref is None or e.data["case_ref"] == case_ref]
    records.sort(key=lambda r: r.data["evidence_ref"])

    def chain(record: SourceRecord) -> list[tuple[SourceRecord, str | None]]:
        return chains.get(record.data["evidence_ref"], [])

    return _table(
        "evidence_items",
        {"unit_path": unit_path, **_given(case_ref=case_ref)},
        records,
        {
            "id": _source_ref,
            **_fields("evidence_ref", "case_ref", "item", "kind", "status"),
            "sha256": lambda r: str(r.data["sha256"])[:16],
            "custody_events": lambda r: len(chain(r)),
            "custody_breaks": lambda r: sum(1 for _e, expected in chain(r) if expected),
            "unit_path": _unit_path,
        },
    )


def custody_gaps(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """Custody events whose recorded holder is not whoever last received the item."""
    _check_names(params, frozenset({"unit_path"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    _evidence, chains = _forensics(scope, unit_path)
    broken = [
        (event, expected)
        for chain in chains.values()
        for event, expected in chain
        if expected is not None
    ]
    broken.sort(key=lambda pair: (pair[0].data["event_date"], pair[0].source_ref))
    expected_by_ref = {event.source_ref: expected for event, expected in broken}
    return _table(
        "custody_gaps",
        {"unit_path": unit_path},
        [event for event, _ in broken],
        {
            "id": _source_ref,
            **_fields("evidence_ref", "case_ref", "action", "event_date"),
            "recorded_holder": _field("from_holder"),
            "expected_holder": lambda r: expected_by_ref[r.source_ref],
            "unit_path": _unit_path,
        },
    )


def custody_trail(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """One evidence item's chain of custody, oldest first, with any break marked."""
    _check_names(params, frozenset({"unit_path", "evidence_ref"}))
    unit_path = _resolve_unit_path(scope.ctx, params.get("unit_path"))
    evidence_ref = params.get("evidence_ref")
    if not isinstance(evidence_ref, str) or not _EVIDENCE_RE.match(evidence_ref):
        raise ToolParamError("evidence_ref must look like EV-014-01")
    _evidence, chains = _forensics(scope, unit_path)
    chain = chains.get(evidence_ref, [])
    expected_by_ref = {event.source_ref: expected for event, expected in chain}
    return _table(
        "custody_trail",
        {"unit_path": unit_path, "evidence_ref": evidence_ref},
        [event for event, _ in chain],
        {
            "id": _source_ref,
            **_fields("evidence_ref", "action", "event_date", "from_holder", "to_holder"),
            "break": lambda r: expected_by_ref[r.source_ref] is not None,
            "expected_holder": lambda r: expected_by_ref[r.source_ref],
            "unit_path": _unit_path,
        },
    )

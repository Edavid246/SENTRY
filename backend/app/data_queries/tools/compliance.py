"""Equipment, certification, stock and training tools."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from app.authz.scope import Scope
from app.clock import demo_today
from app.connectors.base import SourceRecord
from app.data_queries.tools.base import (
    MAX_WITHIN_DAYS,
    Table,
    bounded_int,
    column,
    columns,
    given,
    matching,
    number,
    search,
    tool,
)

DEFAULT_PERIOD_DAYS = 90  # one quarter
_DEPOT_RE = re.compile(r"^DEP-[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8})?$")


@tool("within_days")
def equipment_due_for_maintenance(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    within_days = bounded_int(params.get("within_days", 30), "within_days", 0, MAX_WITHIN_DAYS)
    records = search(
        scope,
        "Equipment",
        unit_path,
        date_field="maintenance_due_date",
        on_or_before=demo_today() + timedelta(days=within_days),
    )
    records.sort(key=lambda r: (r.data["maintenance_due_date"], r.source_ref))
    return Table(
        records,
        columns("name", "type", "status", "maintenance_due_date", "location"),
        {"within_days": within_days},
    )


@tool()
def expired_certifications(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    records = search(
        scope,
        "Qualification",
        unit_path,
        date_field="expires",
        on_or_before=demo_today() - timedelta(days=1),
    )
    records.sort(key=lambda r: (r.data["expires"], r.source_ref))
    return Table(
        records,
        {**columns("name", "rank", "certification"), "expired_date": column("expires")},
    )


@tool("depot")
def stock_below_threshold(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    depot = matching(params.get("depot"), _DEPOT_RE, "depot must look like DEP-B2")
    found = search(scope, "StockItem", unit_path)
    # Quantities are compared here, on rows the adapter already authorized.
    records = [
        record
        for record in found
        if (qty := number(record.data.get("quantity"))) is not None
        and (thr := number(record.data.get("threshold"))) is not None
        and qty < thr
        and (depot is None or record.data.get("depot") == depot)
    ]
    records.sort(key=lambda r: (r.data["quantity"] - r.data["threshold"], r.source_ref))
    return Table(
        records,
        {
            **columns("item", "depot", "quantity", "threshold"),
            "shortfall": lambda r: r.data["threshold"] - r.data["quantity"],
        },
        given(depot=depot),
    )


@tool("period_days")
def training_activity(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Training events that started in the last `period_days` (default one quarter)."""
    period_days = bounded_int(
        params.get("period_days", DEFAULT_PERIOD_DAYS), "period_days", 1, MAX_WITHIN_DAYS
    )
    today = demo_today()
    start = today - timedelta(days=period_days)

    def started(record: SourceRecord) -> date | None:
        try:
            return date.fromisoformat(str(record.data.get("start_date")))
        except ValueError:
            return None

    found = search(scope, "TrainingEvent", unit_path)
    records = [r for r in found if (d := started(r)) is not None and start <= d <= today]
    records.sort(key=lambda r: (r.data["start_date"], r.source_ref), reverse=True)
    return Table(
        records, columns("course", "start_date", "attendees"), {"period_days": period_days}
    )


@tool()
def field_personnel(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Personnel certifications the caller may see, each marked valid or expired."""
    records = search(scope, "Qualification", unit_path)
    records.sort(key=lambda r: (str(r.data.get("name", "")), r.data["expires"], r.source_ref))
    today = demo_today().isoformat()
    return Table(
        records,
        {
            **columns("name", "rank", "certification", "expires"),
            "status": lambda r: "expired" if r.data["expires"] < today else "valid",
        },
    )

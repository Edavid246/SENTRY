"""Contract and delivery tools."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from app.authz.scope import Scope
from app.clock import demo_today
from app.data_queries.errors import ToolParamError
from app.data_queries.tools.base import Table, column, columns, given, matching, search, tool

CONTRACT_STATUSES = frozenset({"active", "at_risk", "completed"})
_CLIENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .&-]{0,39}$")
_CLIENT_MESSAGE = "client is not a valid client name"


@tool("client")
def deliveries_overdue(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Deliveries past their due date and not yet delivered, optionally for one client."""
    client = matching(params.get("client"), _CLIENT_RE, _CLIENT_MESSAGE)
    today = demo_today()
    found = search(
        scope,
        "Delivery",
        unit_path,
        date_field="due_date",
        on_or_before=today - timedelta(days=1),
    )
    records = [
        r
        for r in found
        if r.data.get("status") != "delivered"
        and (client is None or r.data.get("client") == client)
    ]
    records.sort(key=lambda r: (r.data["due_date"], r.source_ref))
    return Table(
        records,
        {
            **columns("delivery_ref", "contract_ref", "client", "item", "quantity", "due_date"),
            "days_overdue": lambda r: (today - date.fromisoformat(r.data["due_date"])).days,
            "status": column("status"),
        },
        given(client=client),
    )


@tool("client", "status")
def contracts_status(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Contracts the caller may see, optionally for one client and/or one status."""
    client = matching(params.get("client"), _CLIENT_RE, _CLIENT_MESSAGE)
    status = params.get("status")
    if status is not None and status not in CONTRACT_STATUSES:
        raise ToolParamError("status must be 'active', 'at_risk' or 'completed'")
    records = [
        r
        for r in search(scope, "Contract", unit_path)
        if (client is None or r.data.get("client") == client)
        and (status is None or r.data.get("status") == status)
    ]
    records.sort(key=lambda r: (r.data["contract_ref"], r.source_ref))
    return Table(
        records,
        columns("contract_ref", "client", "subject", "status", "end_date", "value_musd"),
        given(client=client, status=status),
    )

"""Production and serial-traceability tools."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.authz.scope import Scope
from app.connectors.base import SourceRecord
from app.data_queries.errors import ToolParamError
from app.data_queries.tools.base import Table, columns, search, tool

_SERIAL_RE = re.compile(r"^[A-Z]{2,4}(?:-[A-Z]{2,4})?-\d{3,5}$")
_RUN_COLUMNS = ("run_ref", "product", "quantity", "qc_status", "hold_reason")


def _with_serial_counts(scope: Scope, unit_path: str, runs: list[SourceRecord]) -> Table:
    """The runs as a table, each with how many visible serials trace to it."""
    serials = search(scope, "SerialUnit", unit_path)
    traced = {
        r.data["run_ref"]: sum(1 for s in serials if s.data.get("run_ref") == r.data["run_ref"])
        for r in runs
    }
    return Table(
        runs,
        {**columns(*_RUN_COLUMNS), "serials_traced": lambda r: traced[r.data["run_ref"]]},
    )


@tool("serial")
def serial_trace(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """One serial number's production run, QC state and delivery. A serial the caller may
    not see is indistinguishable from one that does not exist: the result is simply empty."""
    serial = params.get("serial")
    if not isinstance(serial, str) or not _SERIAL_RE.match(serial):
        raise ToolParamError("serial is not a valid serial number")
    records = [r for r in search(scope, "SerialUnit", unit_path) if r.data.get("serial") == serial]
    return Table(
        records,
        columns("serial", "product", "run_ref", "qc_status", "delivered_to", "delivery_ref"),
        {"serial": serial},
    )


@tool()
def production_qc_holds(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Production runs on QC hold, with how many visible serials each affects."""
    held = sorted(
        (r for r in search(scope, "ProductionRun", unit_path) if r.data.get("qc_status") == "hold"),
        key=lambda r: (r.data["run_ref"], r.source_ref),
    )
    return _with_serial_counts(scope, unit_path, held)


@tool()
def production_runs(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Every production run the caller may see, with how many visible serials each traces to."""
    runs = search(scope, "ProductionRun", unit_path)
    runs.sort(key=lambda r: (r.data["run_ref"], r.source_ref))
    return _with_serial_counts(scope, unit_path, runs)

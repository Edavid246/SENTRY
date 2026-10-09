"""Tool registry and audited execution (SPEC 8.2, 14).

name -> callable(scope, params). `tool_requirements` names the policy decisions
a caller must make before a tool runs. `execute_tool` is the only entry point: it
validates the tool name, runs the tool on the caller's authorized Scope, and
records exactly one `data_query` audit event per call on that scope (written
with the rest of the request's events, after the decision that allowed it):
an allow with the row count, or a deny when the call was refused with a
ToolParamError (no SQL ran).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.audit.events import event
from app.authz.scope import Requirement, Scope
from app.connectors.base import SourceRecord
from app.data_queries.errors import ToolParamError
from app.data_queries.tools import (
    ToolResult,
    contracts_status,
    correlation_findings,
    deliveries_overdue,
    detections_near_site,
    equipment_due_for_maintenance,
    expired_certifications,
    production_qc_holds,
    production_runs,
    sensors_status,
    serial_trace,
    stock_below_threshold,
    training_activity,
    uas_fleet,
    uas_missions,
)

ToolFn = Callable[[Scope, Mapping[str, Any]], ToolResult]

REGISTRY: dict[str, ToolFn] = {
    "equipment_due_for_maintenance": equipment_due_for_maintenance,
    "expired_certifications": expired_certifications,
    "stock_below_threshold": stock_below_threshold,
    "correlation_findings": correlation_findings,
    "training_activity": training_activity,
    "uas_missions": uas_missions,
    "uas_fleet": uas_fleet,
    "sensors_status": sensors_status,
    "detections_near_site": detections_near_site,
    "deliveries_overdue": deliveries_overdue,
    "contracts_status": contracts_status,
    "serial_trace": serial_trace,
    "production_qc_holds": production_qc_holds,
    "production_runs": production_runs,
}

# The policy decisions a caller needs before a tool runs. Tools read source records;
# correlation_findings reads our own findings store, which `query` on records does not cover.
_RECORD_QUERY: tuple[Requirement, ...] = (("query", "record"),)
_REQUIREMENTS: dict[str, tuple[Requirement, ...]] = {
    "correlation_findings": (("read", "finding"),),
}

_AUDIT_VALUE_LIMIT = 120


def tool_requirements(name: str) -> tuple[Requirement, ...]:
    """The (action, resource) decisions to make before running tool `name`."""
    return _REQUIREMENTS.get(name, _RECORD_QUERY)


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    tool: str
    result: ToolResult | None
    refusal: str | None

    @property
    def refused(self) -> bool:
        return self.refusal is not None

    @property
    def records(self) -> tuple[SourceRecord, ...]:
        """The source records behind the result (none for a refusal)."""
        return self.result.records if self.result else ()


def sanitize_params(params: Mapping[str, Any]) -> dict[str, Any]:
    """Audit-safe copy: bounded keys, scalars kept, everything else stringified and cut."""
    clean: dict[str, Any] = {}
    for key, value in list(params.items())[:20]:
        if value is None or isinstance(value, bool | int | float):
            clean[str(key)[:64]] = value
        else:
            clean[str(key)[:64]] = str(value)[:_AUDIT_VALUE_LIMIT]
    return clean


def execute_tool(scope: Scope, name: str, params: Mapping[str, Any]) -> ToolOutcome:
    tool = REGISTRY.get(name)
    try:
        if tool is None:
            raise ToolParamError("unknown tool")
        result = tool(scope, params)
    except ToolParamError as exc:
        scope.record(
            event(
                scope.ctx.username,
                "data_query",
                "record",
                "deny",
                tool=name[:64],
                params=sanitize_params(params),
                rows=0,
                reasons=[str(exc)],
            )
        )
        return ToolOutcome(tool=name, result=None, refusal=str(exc))
    scope.record(
        event(
            scope.ctx.username,
            "data_query",
            "record",
            "allow",
            tool=name[:64],
            params=sanitize_params(result.params),
            rows=len(result.rows),
            record_ids=[record.source_ref for record in result.records],
        )
    )
    return ToolOutcome(tool=name, result=result, refusal=None)

"""What every typed query tool shares (SPEC 8.2 data pathway).

A tool is a function `(scope, params, unit_path) -> Table`, registered with `@tool(...)`. The
decorator owns everything that must be identical across tools: unknown parameters are refused, the
unit path is defaulted and checked against the caller's unit, and the output is projected through
the tool's columns so a column and its row key can never disagree. The tool body only does what
is particular to it: validate its own parameters, ask the adapter for records on the caller's
authorized Scope (it never builds SQL and never touches the record tables), and name its columns.
The allowed-parameter set is the decorator's arguments, in one place per tool.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from app.authz.context import AccessContext
from app.authz.scope import Scope
from app.connectors import get_adapter
from app.connectors.base import RecordFilter, SourceRecord
from app.data_queries.errors import ToolParamError
from app.geo.states import check_state

MAX_WITHIN_DAYS = 365
_UNIT_PATH_RE = re.compile(r"^/(?:[a-z0-9-]+/)+$")

Column = Callable[[SourceRecord], Any]
ToolFn = Callable[[Scope, Mapping[str, Any]], "ToolResult"]
ToolBody = Callable[[Scope, Mapping[str, Any], str], "Table"]  # (scope, params, unit_path)


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool: str
    params: dict[str, Any]
    columns: tuple[str, ...]
    rows: list[dict[str, Any]]
    records: tuple[SourceRecord, ...]


@dataclass(frozen=True, slots=True)
class Table:
    """What a tool body returns: its records, its columns, and the optional params it echoes."""

    records: list[SourceRecord]
    columns: dict[str, Column]
    params: dict[str, Any] = field(default_factory=dict)


TOOLS: dict[str, ToolFn] = {}


def source_ref(record: SourceRecord) -> str:
    return record.source_ref


def owning_unit(record: SourceRecord) -> str:
    return record.unit_path


def column(name: str) -> Column:
    return lambda record: record.data.get(name)


def columns(*names: str) -> dict[str, Column]:
    return {name: column(name) for name in names}


def given(**optional: Any) -> dict[str, Any]:
    """The optional parameters that were actually given (for the echoed params)."""
    return {name: value for name, value in optional.items() if value is not None}


def search(scope: Scope, entity_type: str, unit_path: str, **filters: Any) -> list[SourceRecord]:
    """Records of one entity type on the caller's authorized scope (filter inside the query)."""
    return get_adapter().search(
        scope, RecordFilter(entity_type=entity_type, unit_path=unit_path, **filters)
    )


def project(
    tool_name: str, params: dict[str, Any], records: list[SourceRecord], cols: dict[str, Column]
) -> ToolResult:
    return ToolResult(
        tool=tool_name,
        params=params,
        columns=tuple(cols),
        rows=[{name: value(record) for name, value in cols.items()} for record in records],
        records=tuple(records),
    )


def check_names(params: Mapping[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(str(name) for name in params if name not in allowed)
    if unknown:
        raise ToolParamError(f"unknown parameter(s): {', '.join(unknown)[:80]}")


def resolve_unit_path(ctx: AccessContext, value: Any) -> str:
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


def bounded_int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolParamError(f"{name} must be an integer")
    if not low <= value <= high:
        raise ToolParamError(f"{name} must be between {low} and {high}")
    return value


def matching(value: Any, pattern: re.Pattern[str], message: str) -> str | None:
    """An optional string parameter that must match `pattern` (None when not given)."""
    if value is None:
        return None
    if not isinstance(value, str) or not pattern.match(value):
        raise ToolParamError(message)
    return value


def choice(value: Any, name: str, allowed: tuple[str, ...]) -> str | None:
    """An optional parameter that must be one of `allowed`; the refusal lists them in order."""
    if value is None:
        return None
    if value not in allowed:
        quoted = [f"'{item}'" for item in allowed]
        raise ToolParamError(f"{name} must be {', '.join(quoted[:-1])} or {quoted[-1]}")
    return value


def checked_state(value: Any) -> str | None:
    try:
        return check_state(value)
    except ValueError as exc:
        raise ToolParamError(str(exc)) from None


def number(value: Any) -> float | None:
    return None if isinstance(value, bool) or not isinstance(value, int | float) else value


def tool(
    *extra_params: str,
) -> Callable[[Callable[[Scope, Mapping[str, Any], str], Table]], ToolFn]:
    """Register a tool that takes `unit_path` plus `extra_params`, named after the function."""
    allowed = frozenset({"unit_path", *extra_params})

    def register(body: ToolBody) -> ToolFn:
        @wraps(body)
        def run(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
            check_names(params, allowed)
            unit_path = resolve_unit_path(scope.ctx, params.get("unit_path"))
            table = body(scope, params, unit_path)
            return project(
                body.__name__,
                {"unit_path": unit_path, **table.params},
                table.records,
                {"id": source_ref, **table.columns, "unit_path": owning_unit},
            )

        TOOLS[body.__name__] = run
        return run

    return register

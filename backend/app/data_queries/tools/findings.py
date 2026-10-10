"""The correlation findings tool: our own findings store, not a source system."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.authz.scope import Scope
from app.connectors.base import SourceRecord
from app.correlation.store import list_findings
from app.data_queries.tools.base import (
    TOOLS,
    ToolResult,
    check_names,
    column,
    columns,
    owning_unit,
    project,
    source_ref,
)


def correlation_findings(scope: Scope, params: Mapping[str, Any]) -> ToolResult:
    """The correlation findings this caller may see (row filter + RLS in the query).

    Findings are produced by our own correlation job, not a source system, so this reads the
    findings store rather than an adapter, and takes no unit path (hence no `@tool`). Each
    finding is wrapped as a record so the answer inherits its classification and compartments
    like any other.
    """
    check_names(params, frozenset())
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
    return project(
        "correlation_findings",
        {},
        records,
        {
            "id": source_ref,
            **columns("title", "severity"),
            "classification": lambda r: r.classification_code,
            "unit_path": owning_unit,
            "summary": column("summary"),
        },
    )


TOOLS["correlation_findings"] = correlation_findings

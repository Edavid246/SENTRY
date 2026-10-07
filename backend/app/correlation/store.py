"""Findings store: writes and reads through RLS + the policy row filter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.authz.context import AccessContext
from app.authz.policy import LocalPolicy
from app.correlation.types import FindingDraft
from app.db import set_rls_context_for

POLICY = LocalPolicy()


@dataclass(frozen=True, slots=True)
class FindingRow:
    key: str
    analysis: str
    title: str
    summary: str
    severity: str
    classification_code: str
    compartments: list[str]
    unit_path: str
    evidence_ids: list[str]
    details: dict[str, Any]
    created_at: str


def save_findings(conn: Connection, ctx: AccessContext, drafts: list[FindingDraft]) -> None:
    """Insert or update by key. RLS WITH CHECK refuses anything above the runner's label."""
    set_rls_context_for(conn, ctx)
    for draft in drafts:
        unit_id = conn.execute(
            text("SELECT id FROM units WHERE path = :path"), {"path": draft.unit_path}
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO findings (id, key, analysis, title, summary, severity,"
                " classification_code, compartments, unit_id, evidence_ids, details, created_by)"
                " VALUES (gen_random_uuid(), :key, :analysis, :title, :summary, :severity,"
                " :classification, :compartments, :unit_id,"
                " CAST(:evidence AS jsonb), CAST(:details AS jsonb), :created_by)"
                " ON CONFLICT (key) DO UPDATE SET title = EXCLUDED.title,"
                " summary = EXCLUDED.summary, severity = EXCLUDED.severity,"
                " classification_code = EXCLUDED.classification_code,"
                " compartments = EXCLUDED.compartments, unit_id = EXCLUDED.unit_id,"
                " evidence_ids = EXCLUDED.evidence_ids, details = EXCLUDED.details,"
                " updated_at = now()"
            ),
            {
                "key": draft.key,
                "analysis": draft.analysis,
                "title": draft.title,
                "summary": draft.summary,
                "severity": draft.severity,
                "classification": draft.classification_code,
                "compartments": draft.compartments,
                "unit_id": unit_id,
                "evidence": json.dumps(draft.evidence_ids),
                "details": json.dumps(draft.details),
                "created_by": ctx.user_id,
            },
        )


def list_findings(conn: Connection, ctx: AccessContext, key: str | None = None) -> list[FindingRow]:
    """The findings this caller may see; the row filter is inside the query."""
    set_rls_context_for(conn, ctx)
    row_filter = POLICY.row_filter(ctx, "finding")
    where = row_filter.where_sql
    params: dict[str, Any] = dict(row_filter.params)
    if key is not None:
        where += " AND findings.key = :key"
        params["key"] = key
    rows = (
        conn.execute(
            text(
                "SELECT findings.key, findings.analysis, findings.title, findings.summary,"
                " findings.severity, findings.classification_code, findings.compartments,"
                " units.path AS unit_path, findings.evidence_ids, findings.details,"
                " findings.created_at FROM findings JOIN units ON units.id = findings.unit_id"
                f" WHERE {where} ORDER BY findings.created_at DESC, findings.key"
            ),
            params,
        )
        .mappings()
        .all()
    )
    return [
        FindingRow(
            key=str(r["key"]),
            analysis=str(r["analysis"]),
            title=str(r["title"]),
            summary=str(r["summary"]),
            severity=str(r["severity"]),
            classification_code=str(r["classification_code"]),
            compartments=[str(c) for c in (r["compartments"] or [])],
            unit_path=str(r["unit_path"]),
            evidence_ids=[str(e) for e in r["evidence_ids"]],
            details=dict(r["details"]),
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]

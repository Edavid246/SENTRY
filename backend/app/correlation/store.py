"""Findings store: writes and reads on an authorized Scope (RLS + the policy row filter)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.authz.scope import Scope
from app.correlation.types import FindingDraft


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
    created_at: datetime


def save_findings(scope: Scope, drafts: list[FindingDraft]) -> list[str]:
    """Insert, or update a stored finding the runner may see; returns the keys written.

    RLS WITH CHECK refuses anything above the runner's label. A key already held by
    a finding the runner may NOT see is left untouched and nothing is stored for it:
    a single upsert would hit the UPDATE USING policy and raise, and that error would
    tell the runner a hidden finding exists. The scope commits after its audit batch.
    """
    conn = scope.conn
    row_filter = scope.filter("finding")
    stored: list[str] = []
    for draft in drafts:
        unit_id = conn.execute(
            text("SELECT id FROM units WHERE path = :path"), {"path": draft.unit_path}
        ).scalar_one()
        values = {
            "key": draft.key,
            "title": draft.title,
            "summary": draft.summary,
            "severity": draft.severity,
            "classification": draft.classification_code,
            "new_compartments": draft.compartments,
            "unit_id": unit_id,
            "evidence": json.dumps(draft.evidence_ids),
            "details": json.dumps(draft.details),
        }
        written = conn.execute(
            text(
                "INSERT INTO findings (id, key, analysis, title, summary, severity,"
                " classification_code, compartments, unit_id, evidence_ids, details, created_by)"
                " VALUES (gen_random_uuid(), :key, :analysis, :title, :summary, :severity,"
                " :classification, :new_compartments, :unit_id,"
                " CAST(:evidence AS jsonb), CAST(:details AS jsonb), :created_by)"
                " ON CONFLICT (key) DO NOTHING RETURNING key"
            ),
            {**values, "analysis": draft.analysis, "created_by": scope.ctx.user_id},
        ).scalar_one_or_none()
        if written is None:
            # The key exists: update it only if it is visible (filter + RLS USING).
            written = conn.execute(
                text(
                    "UPDATE findings SET title = :title, summary = :summary,"
                    " severity = :severity, classification_code = :classification,"
                    " compartments = :new_compartments, unit_id = :unit_id,"
                    " evidence_ids = CAST(:evidence AS jsonb),"
                    " details = CAST(:details AS jsonb), updated_at = now()"
                    f" WHERE findings.key = :key AND {row_filter.where_sql} RETURNING key"
                ),
                {**values, **row_filter.params},
            ).scalar_one_or_none()
        if written is not None:
            stored.append(draft.key)
    scope.commit()
    return stored


def list_findings(scope: Scope, key: str | None = None) -> list[FindingRow]:
    """The findings this caller may see; the row filter is inside the query."""
    row_filter = scope.filter("finding")
    where = row_filter.where_sql
    params: dict[str, Any] = dict(row_filter.params)
    if key is not None:
        where += " AND findings.key = :key"
        params["key"] = key
    rows = (
        scope.conn.execute(
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
            created_at=r["created_at"],
        )
        for r in rows
    ]

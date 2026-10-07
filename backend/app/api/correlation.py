"""Correlation pathway (SPEC 10.6): POST /api/v1/correlation/run, GET .../findings.

Run is on demand and commander-only (`run_correlation` permission). The job runs
as the caller, over the rows the caller may see, through the audited typed tools
and the adapter. A finding stores the highest classification and the union of
compartments of its evidence, its evidence references and the analysis
parameters that produced it. Reads go through the policy row filter + RLS, so a
finding above the caller's clearance is simply absent from the list and 404s on
the detail route (never 403: existence is not confirmed).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import ConnDep, CurrentContext, audit_events
from app.audit.chain import utc_now_iso
from app.authz.policy import LocalPolicy
from app.correlation.analysis import ANALYSIS, run_rising_faults
from app.correlation.store import FindingRow, list_findings, save_findings

POLICY = LocalPolicy()

router = APIRouter(prefix="/api/v1/correlation", tags=["correlation"])


class FindingOut(BaseModel):
    id: str = Field(description="stable finding id, e.g. FND-RISING-FAULTS-BN-4")
    analysis: str
    title: str
    summary: str
    severity: str
    classification_code: str
    compartments: list[str]
    unit_path: str
    unit_name: str
    evidence_ids: list[str] = Field(description="record references (open via /records/{id})")
    details: dict[str, Any] = Field(description="the analysis parameters that produced it")
    created_at: str


class RunResult(BaseModel):
    analysis: str
    findings: list[FindingOut]


def _decide(ctx, action: str):
    decision = POLICY.decide(ctx, action, "finding")
    event: dict[str, Any] = {
        "actor": ctx.username,
        "action": "decide",
        "resource": "finding",
        "requested": action,
        "decision": "allow" if decision.allowed else "deny",
        "timestamp": utc_now_iso(),
    }
    if not decision.allowed:
        event["reasons"] = list(decision.reasons)
    return decision, event


def _unit_names(conn) -> dict[str, str]:
    return {
        str(r["path"]): str(r["name"])
        for r in conn.execute(text("SELECT path, name FROM units")).mappings()
    }


def finding_out(row: FindingRow, names: dict[str, str]) -> FindingOut:
    return FindingOut(
        id=row.key,
        analysis=row.analysis,
        title=row.title,
        summary=row.summary,
        severity=row.severity,
        classification_code=row.classification_code,
        compartments=row.compartments,
        unit_path=row.unit_path,
        unit_name=names.get(row.unit_path, row.unit_path),
        evidence_ids=row.evidence_ids,
        details=row.details,
        created_at=row.created_at,
    )


@router.post("/run", response_model=RunResult)
def run_correlation(ctx: CurrentContext, conn: ConnDep) -> RunResult:
    decision, decide_event = _decide(ctx, "run_correlation")
    if not decision.allowed:
        audit_events([decide_event])
        raise HTTPException(status_code=403, detail="forbidden")
    ranks = {
        str(r["code"]): int(r["rank"])
        for r in conn.execute(text("SELECT code, rank FROM classification_levels")).mappings()
    }
    names = _unit_names(conn)
    drafts = run_rising_faults(ctx, conn, ranks, names)
    save_findings(conn, ctx, drafts)
    conn.commit()
    rows = list_findings(conn, ctx)
    audit_events(
        [
            decide_event,
            {
                "actor": ctx.username,
                "action": "correlation_run",
                "resource": "finding",
                "analysis": ANALYSIS,
                "decision": "allow",
                "findings": [
                    {
                        "id": d.key,
                        "classification": d.classification_code,
                        "compartments": d.compartments,
                        "evidence": d.evidence_ids,
                    }
                    for d in drafts
                ],
                "timestamp": utc_now_iso(),
            },
        ]
    )
    return RunResult(analysis=ANALYSIS, findings=[finding_out(r, names) for r in rows])


@router.get("/findings", response_model=list[FindingOut])
def findings(ctx: CurrentContext, conn: ConnDep) -> list[FindingOut]:
    decision, decide_event = _decide(ctx, "read")
    if not decision.allowed:
        audit_events([decide_event])
        raise HTTPException(status_code=403, detail="forbidden")
    rows = list_findings(conn, ctx)
    audit_events(
        [
            decide_event,
            {
                "actor": ctx.username,
                "action": "query",
                "resource": "finding",
                "decision": "allow",
                "rows": len(rows),
                "item_ids": [r.key for r in rows],
                "timestamp": utc_now_iso(),
            },
        ]
    )
    names = _unit_names(conn)
    return [finding_out(r, names) for r in rows]


@router.get("/findings/{finding_id}", response_model=FindingOut)
def finding(finding_id: str, ctx: CurrentContext, conn: ConnDep) -> FindingOut:
    decision, decide_event = _decide(ctx, "read")
    if not decision.allowed:
        audit_events([decide_event])
        raise HTTPException(status_code=404, detail="not found")
    rows = list_findings(conn, ctx, key=finding_id)
    audit_events(
        [
            decide_event,
            {
                "actor": ctx.username,
                "action": "query",
                "resource": "finding",
                "decision": "allow",
                "rows": len(rows),
                "item_ids": [r.key for r in rows],
                "timestamp": utc_now_iso(),
            },
        ]
    )
    if not rows:
        raise HTTPException(status_code=404, detail="not found")
    return finding_out(rows[0], _unit_names(conn))

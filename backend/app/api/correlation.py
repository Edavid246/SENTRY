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

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.audit.events import event
from app.authz.labels import Labels
from app.correlation.analysis import ANALYSIS, run_rising_faults
from app.correlation.store import FindingRow, list_findings, save_findings
from app.units import unit_names

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
        created_at=row.created_at.isoformat(),
    )


@router.post("/run", response_model=RunResult)
def run_correlation(ctx: CurrentContext, conn: ConnDep) -> RunResult:
    with guarded(ctx, conn, "run_correlation", "finding") as scope:
        names = unit_names(conn)
        drafts = run_rising_faults(scope, Labels.load(conn), names)
        stored = set(save_findings(scope, drafts))  # committed once the audit batch is written
        rows = list_findings(scope)
        scope.record(
            event(
                ctx.username,
                "correlation_run",
                "finding",
                "allow",
                analysis=ANALYSIS,
                findings=[
                    {
                        "id": d.key,
                        "classification": d.classification_code,
                        "compartments": d.compartments,
                        "evidence": d.evidence_ids,
                        # False: the key belongs to a finding above the runner's label
                        "stored": d.key in stored,
                    }
                    for d in drafts
                ],
            )
        )
    return RunResult(analysis=ANALYSIS, findings=[finding_out(r, names) for r in rows])


@router.get("/findings", response_model=list[FindingOut])
def findings(ctx: CurrentContext, conn: ConnDep) -> list[FindingOut]:
    with guarded(ctx, conn, "read", "finding") as scope:
        rows = list_findings(scope)
        scope.read("finding", len(rows), item_ids=[r.key for r in rows])
    names = unit_names(conn)
    return [finding_out(r, names) for r in rows]


@router.get("/findings/{finding_id}", response_model=FindingOut)
def finding(finding_id: str, ctx: CurrentContext, conn: ConnDep) -> FindingOut:
    with guarded(ctx, conn, "read", "finding", on_deny="not_found") as scope:
        rows = list_findings(scope, key=finding_id)
        scope.read("finding", len(rows), item_ids=[r.key for r in rows])
    if not rows:
        raise HTTPException(status_code=404, detail="not found")
    return finding_out(rows[0], unit_names(conn))

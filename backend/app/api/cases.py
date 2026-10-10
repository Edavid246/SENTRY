"""Forensic case workspace: GET /api/v1/cases/{case_ref}.

One case with its evidence items and each item's chain of custody. Built from the audited typed
tools (forensic_cases, evidence_items, custody_trail), so the filter runs inside every query and
RLS sits under it. A case the caller cannot see answers 404, exactly like one that does not exist.
The view is a derived item: it takes the highest classification and the union of compartments of
every case, evidence and custody record behind it.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.audit.chain import utc_now_iso
from app.authz.labels import Labels
from app.data_queries.registry import execute_tool

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])

_CASE_REF = re.compile(r"^FR-\d{4}-\d{3}$")


class CustodyStep(BaseModel):
    ref: str = Field(description="source record reference of the custody event")
    action: str
    event_date: str
    from_holder: str
    to_holder: str
    expected_holder: str | None = Field(
        description="who the item should have been taken from, when the record says someone else"
    )


class EvidenceView(BaseModel):
    ref: str
    evidence_ref: str
    item: str
    kind: str
    status: str
    sha256: str = Field(description="synthetic hash prefix, not of any real content")
    steps: list[CustodyStep]


class CaseView(BaseModel):
    generated_at: str
    ref: str = Field(description="source record reference of the case")
    case_ref: str
    title: str
    state: str
    opened: str
    lead_examiner: str
    breaks: int
    classification: str
    compartments: list[str]
    evidence: list[EvidenceView]


@router.get("/{case_ref}", response_model=CaseView)
def case_view(case_ref: str, ctx: CurrentContext, conn: ConnDep) -> CaseView:
    if not _CASE_REF.match(case_ref):
        raise HTTPException(status_code=404, detail="not found")
    with guarded(ctx, conn, "read", "dashboard", on_deny="not_found") as scope:
        cases = execute_tool(scope, "forensic_cases", {}).result
        found = (
            [(row, rec) for row, rec in zip(cases.rows, cases.records, strict=True)]
            if cases
            else []
        )
        match = next(((row, rec) for row, rec in found if row["case_ref"] == case_ref), None)
        if match is None:
            raise HTTPException(status_code=404, detail="not found")
        case_row, case_record = match

        items = execute_tool(scope, "evidence_items", {"case_ref": case_ref}).result
        evidence: list[EvidenceView] = []
        records = [case_record]
        for row, record in zip(items.rows, items.records, strict=True) if items else ():
            records.append(record)
            trail = execute_tool(scope, "custody_trail", {"evidence_ref": row["evidence_ref"]})
            steps: list[CustodyStep] = []
            if trail.result:
                for step, event in zip(trail.result.rows, trail.result.records, strict=True):
                    records.append(event)
                    steps.append(
                        CustodyStep(
                            ref=event.source_ref,
                            action=step["action"],
                            event_date=step["event_date"],
                            from_holder=step["from_holder"],
                            to_holder=step["to_holder"],
                            expected_holder=step["expected_holder"],
                        )
                    )
            evidence.append(
                EvidenceView(
                    ref=record.source_ref,
                    evidence_ref=row["evidence_ref"],
                    item=row["item"],
                    kind=row["kind"],
                    status=row["status"],
                    sha256=record.data["sha256"],
                    steps=steps,
                )
            )
        label = Labels.load(conn).derive(records)
        scope.read("dashboard", len(records), item_ids=[r.source_ref for r in records])
    return CaseView(
        generated_at=utc_now_iso(),
        ref=case_record.source_ref,
        case_ref=case_ref,
        title=case_row["title"],
        state=case_row["state"],
        opened=case_row["opened"],
        lead_examiner=case_row["lead_examiner"],
        breaks=case_row["custody_breaks"],
        classification=label.code,
        compartments=list(label.compartments),
        evidence=evidence,
    )

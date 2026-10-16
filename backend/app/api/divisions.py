"""Division dashboards: GET /api/v1/divisions/{key} and /{key}/trace?serial=.

Same rules as every data endpoint: a guarded read (policy first, filter inside the query, RLS
under it), and a division the caller cannot see answers 404, exactly like one that does not
exist. The sections are built by `app.divisions.view`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.clock import utc_now_iso
from app.divisions.catalog import DivisionNotFound
from app.divisions.view import Fact, Section, TraceRefused, build_division, build_trace

router = APIRouter(prefix="/api/v1/divisions", tags=["divisions"])


class DivisionView(BaseModel):
    key: str
    name: str
    tagline: str
    generated_at: str
    facts: list[Fact] = Field(description="a few plain figures for the header, may be empty")
    sections: list[Section] = Field(description="empty until this division's dashboard exists")


@router.get("/{key}", response_model=DivisionView)
def division_view(key: str, ctx: CurrentContext, conn: ConnDep) -> DivisionView:
    with guarded(ctx, conn, "read", "dashboard", on_deny="not_found") as scope:
        try:
            built = build_division(scope, key)
        except DivisionNotFound:
            raise HTTPException(status_code=404, detail="not found") from None
        division, sections = built.division, built.sections
        scope.read(
            "dashboard",
            sum(len(s.rows) for s in sections),
            item_ids=[r.ref for s in sections for r in s.rows],
        )
    return DivisionView(
        key=division.key,
        name=division.name,
        tagline=division.tagline,
        generated_at=utc_now_iso(),
        facts=built.facts,
        sections=sections,
    )


@router.get("/{key}/trace", response_model=Section)
def serial_trace(
    key: str,
    ctx: CurrentContext,
    conn: ConnDep,
    serial: Annotated[str, Query(max_length=20)],
) -> Section:
    """One serial number's run, QC state and delivery. Unseen and nonexistent read the same."""
    with guarded(ctx, conn, "read", "dashboard", on_deny="not_found") as scope:
        try:
            section = build_trace(scope, key, serial)
        except DivisionNotFound:
            raise HTTPException(status_code=404, detail="not found") from None
        except TraceRefused as refused:
            raise HTTPException(status_code=422, detail=str(refused)) from None
        scope.read("dashboard", len(section.rows), item_ids=[r.ref for r in section.rows])
    return section

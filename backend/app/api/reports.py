"""Division reports: GET /api/v1/reports/{division} and /export?format=pdf|docx.

A report is the division dashboard set out as a document, from the same audited typed tools, so
it holds exactly what the page holds and nothing more (a division the caller cannot see answers
404). It is a derived item: marked with the highest classification and the union of compartments
of every row behind it. Exporting a file takes it out of the system, so an export writes its own
audit event (who, which division, which format, which records, which marking).

Reports are informational drafts. There is no approval flow: people review and decide.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.audit.events import event
from app.authz.context import AccessContext
from app.authz.labels import Label, Labels
from app.clock import wat_now_label
from app.divisions.catalog import DivisionNotFound
from app.divisions.view import Section, build_division
from app.reporting.division import (
    DivisionReport,
    ReportRow,
    ReportSection,
    build_division_report,
)
from app.reporting.export import DOCX_TYPE, PDF_TYPE, filename, render_docx, render_pdf
from app.reporting.marking import marking

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class ReportRowOut(BaseModel):
    label: str
    detail: str
    ref: str
    flagged: bool


class ReportSectionOut(BaseModel):
    title: str
    empty_text: str
    flagged: int
    marking: str | None
    rows: list[ReportRowOut]


class DivisionReportOut(BaseModel):
    division: str
    title: str
    tagline: str
    generated_at: str
    prepared_for: str
    banner: str
    marking: str = Field(description="banner text: the level as the UI names it, then compartments")
    classification: str = Field(description="the internal classification code, not the UI name")
    compartments: list[str]
    facts: list[tuple[str, str]]
    summary: list[str]
    sections: list[ReportSectionOut]
    refs: list[str] = Field(description="every record reference the report was built from")
    notice: str


def _section(section: Section, labels: Labels) -> ReportSection:
    return ReportSection(
        title=section.title,
        empty_text=section.empty_text,
        flagged=section.flagged,
        marking=marking(labels.display(section.classification), section.compartments)
        if section.classification
        else None,
        rows=tuple(ReportRow(r.label, r.detail, r.ref, r.flagged) for r in section.rows),
    )


def _build(ctx: AccessContext, conn: Connection, key: str, *, export: str | None) -> DivisionReport:
    with guarded(ctx, conn, "read", "dashboard", on_deny="not_found") as scope:
        try:
            built = build_division(scope, key)
        except DivisionNotFound:
            raise HTTPException(status_code=404, detail="not found") from None
        division, sections, labels = built.division, built.sections, built.labels
        parts = [
            Label(s.classification, tuple(s.compartments)) for s in sections if s.classification
        ]
        label = labels.derive(parts, empty_ok=True)
        report = build_division_report(
            division=division.key,
            name=division.name,
            tagline=division.tagline,
            generated_at=wat_now_label(),
            prepared_for=f"{scope.ctx.display_name}, {scope.ctx.unit_path}",
            facts=tuple((f.label, f.value) for f in built.facts),
            sections=tuple(_section(s, labels) for s in sections),
            label=label,
            labels=labels,
        )
        scope.read("dashboard", len(report.refs), item_ids=list(report.refs))
        if export:
            scope.record(
                event(
                    scope.ctx.username,
                    "export",
                    "report",
                    "allow",
                    division=division.key,
                    format=export,
                    record_ids=list(report.refs),
                    classification=report.classification,
                    compartments=list(report.compartments),
                )
            )
    return report


@router.get("/{key}", response_model=DivisionReportOut)
def report_view(key: str, ctx: CurrentContext, conn: ConnDep) -> DivisionReport:
    return _build(ctx, conn, key, export=None)


@router.get("/{key}/export")
def report_export(
    key: str,
    ctx: CurrentContext,
    conn: ConnDep,
    format: Annotated[Literal["pdf", "docx"], Query()],  # noqa: A002 - the query parameter's public name
) -> Response:
    report = _build(ctx, conn, key, export=format)
    data, media = (
        (render_pdf(report), PDF_TYPE) if format == "pdf" else (render_docx(report), DOCX_TYPE)
    )
    return Response(
        content=data,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename(report, format)}"',
            "Cache-Control": "no-store",
        },
    )

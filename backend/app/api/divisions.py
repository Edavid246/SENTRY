"""Division dashboards: GET /api/v1/divisions/{key}.

One page per business. Each section is the output of an audited typed tool, narrowed to the
division's unit, so every figure is a list of records the caller is cleared for, and every row
links to its record and evidence panel. Same rules as every data endpoint: a guarded read (policy
first, filter inside the query, RLS under it), and a division the caller cannot see answers 404,
exactly like one that does not exist. A section is a derived item, so it takes the highest
classification and the union of compartments of its rows.

To add a division's dashboard, add its entry to SECTIONS in division_specs.py. Nothing else changes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.audit.chain import utc_now_iso
from app.authz.labels import Labels
from app.authz.scope import Scope
from app.connectors.base import SourceRecord
from app.data_queries.registry import ToolOutcome, execute_tool
from app.units import is_site, unit_names

from .division_specs import COMPLIANCE, SECTIONS, SectionSpec, trace_spec
from .home import DIVISIONS, FIELD_OPS, Division

router = APIRouter(prefix="/api/v1/divisions", tags=["divisions"])
compliance_router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


class SectionRow(BaseModel):
    ref: str = Field(description="source record reference")
    href: str = Field(description="where the row opens: its record, or its finding")
    label: str
    detail: str
    flagged: bool = Field(description="true when this row needs attention")
    meter: float | None = Field(description="0..1 gauge fill, e.g. hours flown of the interval")
    unit_name: str = Field(description="readable name of the unit that owns the record")


class Section(BaseModel):
    key: str
    title: str
    tool: str = Field(description="the typed tool that produced the rows")
    empty_text: str
    flagged: int
    classification: str | None = Field(description="null when the section has no rows")
    compartments: list[str]
    rows: list[SectionRow]


class Fact(BaseModel):
    label: str
    value: str


class DivisionView(BaseModel):
    key: str
    name: str
    tagline: str
    generated_at: str
    facts: list[Fact] = Field(description="a few plain figures for the header, may be empty")
    sections: list[Section] = Field(description="empty until this division's dashboard exists")


def _run(scope: Scope, spec: SectionSpec, unit_path: str) -> ToolOutcome:
    params = {**spec.params, "unit_path": unit_path} if spec.scoped else dict(spec.params)
    return execute_tool(scope, spec.tool, params)


def _build(
    labels: Labels,
    spec: SectionSpec,
    outcome: ToolOutcome,
    keep: Callable[[str], bool],
    names: Mapping[str, str],
) -> Section:
    result = outcome.result
    rows: list[SectionRow] = []
    kept: list[SourceRecord] = []
    if result is not None:
        for row, record in zip(result.rows, result.records, strict=True):
            if not keep(record.unit_path):
                continue  # the division's own records only (matters for unscoped tools)
            kept.append(record)
            rows.append(
                SectionRow(
                    ref=record.source_ref,
                    href=spec.row_href(row) if spec.row_href else spec.href(record.source_ref),
                    label=spec.label(row),
                    detail=spec.detail(row),
                    flagged=spec.flagged(row),
                    meter=spec.meter(row),
                    unit_name=names.get(record.unit_path, record.unit_path),
                )
            )
    label = labels.derive(kept) if kept else None
    return Section(
        key=spec.key,
        title=spec.title,
        tool=spec.tool,
        empty_text=spec.empty_text,
        flagged=sum(1 for r in rows if r.flagged),
        classification=label.code if label else None,
        compartments=list(label.compartments) if label else [],
        rows=rows,
    )


def _reach(path: str, caller: str) -> bool:
    return path.startswith(caller) or caller.startswith(path)


def _division(
    key: str, scope: Scope, names: Mapping[str, str]
) -> tuple[Division, str, Callable[[str], bool]]:
    """The division, the unit its tools run on, and which records count as its own.

    404 unless the caller's unit overlaps the division. Field Operations has no unit of its own:
    it is every site unit the caller can reach, so its tools run on the caller's unit and the
    rows are narrowed to site units afterwards.
    """
    division = next((d for d in DIVISIONS if d.key == key), None)
    caller = scope.ctx.unit_path
    if division is None:
        raise HTTPException(status_code=404, detail="not found")
    if division.path is None:
        if not any(is_site(p) and _reach(p, caller) for p in names):
            raise HTTPException(status_code=404, detail="not found")
        return division, caller, is_site
    if not _reach(division.path, caller):
        raise HTTPException(status_code=404, detail="not found")
    unit_path = division.path if division.path.startswith(caller) else caller
    return division, unit_path, lambda path: path.startswith(unit_path)


def _field_ops_facts(sections: list[Section], names: Mapping[str, str], caller: str) -> list[Fact]:
    sites = sorted(p for p in names if is_site(p) and _reach(p, caller))
    owners = {next(d.name for d in DIVISIONS if d.key == p.split("/")[2]) for p in sites}
    by_key = {s.key: s for s in sections}
    people = {r.label for r in by_key["personnel"].rows} if "personnel" in by_key else set()
    return [
        Fact(label="Field sites", value=", ".join(names[p] for p in sites)),
        Fact(label="Supporting", value=", ".join(sorted(owners))),
        Fact(label="Personnel", value=str(len(people))),
    ]


@dataclass(frozen=True, slots=True)
class BuiltDivision:
    division: Division
    sections: list[Section]
    facts: list[Fact]
    labels: Labels


def build_division(scope: Scope, conn: Connection, key: str) -> BuiltDivision:
    """The division and its sections, run as audited typed tools for the caller (404 if hidden).

    Shared by the dashboard and the report, so a report can never show more than the page does.
    """
    names = unit_names(conn)
    division, unit_path, keep = _division(key, scope, names)
    labels = Labels.load(conn)
    sections = [
        _build(labels, s, _run(scope, s, unit_path), keep, names) for s in SECTIONS.get(key, ())
    ]
    facts = _field_ops_facts(sections, names, scope.ctx.unit_path) if key == FIELD_OPS else []
    return BuiltDivision(division, sections, facts, labels)


@router.get("/{key}", response_model=DivisionView)
def division_view(key: str, ctx: CurrentContext, conn: ConnDep) -> DivisionView:
    with guarded(ctx, conn, "read", "dashboard", on_deny="not_found") as scope:
        built = build_division(scope, conn, key)
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
    serial: str = Query(max_length=20),
) -> Section:
    """One serial number's run, QC state and delivery. Unseen and nonexistent read the same."""
    with guarded(ctx, conn, "read", "dashboard", on_deny="not_found") as scope:
        names = unit_names(conn)
        _, unit_path, keep = _division(key, scope, names)
        spec = trace_spec(serial)
        outcome = _run(scope, spec, unit_path)
        if outcome.refused:
            raise HTTPException(status_code=422, detail=outcome.refusal)
        section = _build(Labels.load(conn), spec, outcome, keep, names)
        scope.read("dashboard", len(section.rows), item_ids=[r.ref for r in section.rows])
    return section


class ComplianceView(BaseModel):
    generated_at: str
    sections: list[Section]


@compliance_router.get("", response_model=ComplianceView)
def group_compliance(ctx: CurrentContext, conn: ConnDep) -> ComplianceView:
    """Certifications and maintenance across every business the caller can see.

    The same two typed tools as each division's compliance section, run on the caller's own
    unit instead of one division's. Rows carry the owning unit's name; the filter is in the
    query, exactly as everywhere else.
    """
    with guarded(ctx, conn, "read", "dashboard", on_deny="not_found") as scope:
        names, labels = unit_names(conn), Labels.load(conn)
        sections = [
            _build(labels, s, _run(scope, s, scope.ctx.unit_path), lambda _path: True, names)
            for s in COMPLIANCE
        ]
        scope.read(
            "dashboard",
            sum(len(s.rows) for s in sections),
            item_ids=[r.ref for s in sections for r in s.rows],
        )
    return ComplianceView(generated_at=utc_now_iso(), sections=sections)

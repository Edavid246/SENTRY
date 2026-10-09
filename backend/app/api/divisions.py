"""Division dashboards: GET /api/v1/divisions/{key}.

One page per business. Each section is the output of an audited typed tool, narrowed to the
division's unit, so every figure is a list of records the caller is cleared for, and every row
links to its record and evidence panel. Same rules as every data endpoint: a guarded read (policy
first, filter inside the query, RLS under it), and a division the caller cannot see answers 404,
exactly like one that does not exist. A section is a derived item, so it takes the highest
classification and the union of compartments of its rows.

To add a division's dashboard, add its entry to SECTIONS. Nothing else changes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.audit.chain import utc_now_iso
from app.authz.labels import Labels
from app.authz.scope import Scope
from app.clock import demo_today
from app.data_queries.registry import ToolOutcome, execute_tool

from .home import DIVISIONS

router = APIRouter(prefix="/api/v1/divisions", tags=["divisions"])

Row = Mapping[str, Any]


class SectionRow(BaseModel):
    ref: str = Field(description="source record reference; links to /records/{ref}")
    label: str
    detail: str
    flagged: bool = Field(description="true when this row needs attention")


class Section(BaseModel):
    key: str
    title: str
    tool: str = Field(description="the typed tool that produced the rows")
    empty_text: str
    flagged: int
    classification: str | None = Field(description="null when the section has no rows")
    compartments: list[str]
    rows: list[SectionRow]


class DivisionView(BaseModel):
    key: str
    name: str
    tagline: str
    generated_at: str
    sections: list[Section] = Field(description="empty until this division's dashboard exists")


@dataclass(frozen=True, slots=True)
class SectionSpec:
    key: str
    title: str
    tool: str
    empty_text: str
    label: Callable[[Row], str]
    detail: Callable[[Row], str]
    flagged: Callable[[Row], bool] = lambda row: True
    params: Mapping[str, Any] = field(default_factory=dict)


def _run_detail(row: Row) -> str:
    text = f"{row['product']} · qty {row['quantity']} · QC {row['qc_status']}"
    text += f" · {row['serials_traced']} serials traced"
    return f"{text} · {row['hold_reason']}" if row.get("hold_reason") else text


_COMPLIANCE = (
    SectionSpec(
        "maintenance",
        "Maintenance due within 30 days",
        "equipment_due_for_maintenance",
        "No equipment is due for maintenance.",
        lambda r: str(r["name"]),
        lambda r: f"{r['type']} · due {r['maintenance_due_date']} · {r['status']}",
        lambda r: str(r["maintenance_due_date"]) < demo_today().isoformat(),
        {"within_days": 30},
    ),
    SectionSpec(
        "certifications",
        "Expired certifications",
        "expired_certifications",
        "No certification has expired.",
        lambda r: str(r["name"]),
        lambda r: f"{r['certification']} · expired {r['expired_date']}",
    ),
)


SECTIONS: dict[str, tuple[SectionSpec, ...]] = {
    "poctova": (
        SectionSpec(
            "qc-holds",
            "Production runs on QC hold",
            "production_qc_holds",
            "No production run is on hold.",
            lambda r: f"{r['run_ref']} · {r['product']}",
            lambda r: (
                f"qty {r['quantity']} · {r['serials_traced']} serials traced · {r['hold_reason']}"
            ),
        ),
        SectionSpec(
            "runs",
            "All production runs",
            "production_runs",
            "No production runs are visible to you.",
            lambda r: f"{r['run_ref']} · {r['product']}",
            _run_detail,
            lambda r: r["qc_status"] == "hold",
        ),
        SectionSpec(
            "stock",
            "Stock below threshold",
            "stock_below_threshold",
            "No stock line is short.",
            lambda r: str(r["item"]),
            lambda r: (
                f"{r['depot']} · {r['quantity']} on hand, threshold {r['threshold']} "
                f"(short by {r['shortfall']})"
            ),
        ),
        SectionSpec(
            "deliveries",
            "Overdue deliveries",
            "deliveries_overdue",
            "No delivery is overdue.",
            lambda r: f"{r['delivery_ref']} · {r['item']}",
            lambda r: (
                f"{r['client']} · qty {r['quantity']} · due {r['due_date']} "
                f"({r['days_overdue']} days overdue) · {r['status']}"
            ),
        ),
        *_COMPLIANCE,
    ),
}


def _run(scope: Scope, spec: SectionSpec, unit_path: str) -> ToolOutcome:
    return execute_tool(scope, spec.tool, {**spec.params, "unit_path": unit_path})


def _build(labels: Labels, spec: SectionSpec, outcome: ToolOutcome) -> Section:
    result = outcome.result
    rows: list[SectionRow] = []
    if result is not None:
        for row, record in zip(result.rows, result.records, strict=True):
            rows.append(
                SectionRow(
                    ref=record.source_ref,
                    label=spec.label(row),
                    detail=spec.detail(row),
                    flagged=spec.flagged(row),
                )
            )
    label = labels.derive(list(outcome.records)) if outcome.records else None
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


def _division(key: str, scope: Scope) -> tuple[Any, str]:
    """The division and the unit its tools are scoped to; 404 unless the caller's unit overlaps."""
    division = next((d for d in DIVISIONS if d.key == key and d.path is not None), None)
    caller = scope.ctx.unit_path
    if division is None or not (
        division.path.startswith(caller) or caller.startswith(division.path)
    ):
        raise HTTPException(status_code=404, detail="not found")
    return division, division.path if division.path.startswith(caller) else caller


@router.get("/{key}", response_model=DivisionView)
def division_view(key: str, ctx: CurrentContext, conn: ConnDep) -> DivisionView:
    with guarded(ctx, conn, "read", "dashboard", on_deny="not_found") as scope:
        division, unit_path = _division(key, scope)
        labels = Labels.load(conn)
        sections = [_build(labels, s, _run(scope, s, unit_path)) for s in SECTIONS.get(key, ())]
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
        _, unit_path = _division(key, scope)
        spec = SectionSpec(
            "trace",
            f"Serial {serial}",
            "serial_trace",
            "No such serial number.",
            lambda r: f"{r['serial']} · {r['product']}",
            lambda r: (
                f"run {r['run_ref']} · QC {r['qc_status']} · "
                f"{('delivered to ' + r['delivered_to']) if r['delivered_to'] else 'in stock'}"
            ),
            lambda r: r["qc_status"] == "hold",
            {"serial": serial},
        )
        outcome = _run(scope, spec, unit_path)
        if outcome.refused:
            raise HTTPException(status_code=422, detail=outcome.refusal)
        section = _build(Labels.load(conn), spec, outcome)
        scope.read("dashboard", len(section.rows), item_ids=[r.ref for r in section.rows])
    return section

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
from app.units import unit_names

from .home import DIVISIONS

router = APIRouter(prefix="/api/v1/divisions", tags=["divisions"])
compliance_router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])

Row = Mapping[str, Any]


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
    meter: Callable[[Row], float | None] = lambda row: None
    href: Callable[[str], str] = lambda ref: f"/records/{ref}"
    row_href: Callable[[Row], str] | None = None  # when the link needs more than the ref
    scoped: bool = True  # False for tools that take no unit_path (the findings store)


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


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _fleet_detail(row: Row) -> str:
    left = row["hours_to_service"]
    text = f"{row['flight_hours']:g} flight hours"
    if row.get("status"):
        text += f" · {str(row['status']).replace('_', ' ')}"
    if left is not None:
        return f"{text} · {left:g} h to service"
    return f"{text} · next service {row['next_service']}" if row.get("next_service") else text


def _fleet_meter(row: Row) -> float | None:
    interval = row["service_interval_hours"]
    return None if not interval else min(1.0, row["flight_hours"] / interval)


SECTIONS: dict[str, tuple[SectionSpec, ...]] = {
    "giga": (
        SectionSpec(
            "custody-breaks",
            "Custody breaks",
            "custody_gaps",
            "Every chain of custody is unbroken.",
            lambda r: f"{r['evidence_ref']} · {r['action']} on {r['event_date']}",
            lambda r: (
                f"Recorded as taken from {r['recorded_holder']}, "
                f"but the last holder was {r['expected_holder']}"
            ),
            row_href=lambda r: f"/cases/{r['case_ref']}",
        ),
        SectionSpec(
            "cases",
            "Cases",
            "forensic_cases",
            "No cases are visible to you.",
            lambda r: f"{r['case_ref']} · {r['title']}",
            lambda r: (
                f"{r['state']} · opened {r['opened']} · "
                f"{_count(r['evidence_items'], 'evidence item')}"
                + (
                    f" · {_count(r['custody_breaks'], 'custody break')}"
                    if r["custody_breaks"]
                    else ""
                )
            ),
            lambda r: r["custody_breaks"] > 0,
            row_href=lambda r: f"/cases/{r['case_ref']}",
        ),
        SectionSpec(
            "evidence",
            "Evidence items",
            "evidence_items",
            "No evidence items are visible to you.",
            lambda r: f"{r['evidence_ref']} · {r['item']}",
            lambda r: (
                f"{r['case_ref']} · {r['kind']} · {r['status']} · "
                f"{_count(r['custody_events'], 'custody event')}"
            ),
            lambda r: r["custody_breaks"] > 0,
        ),
        *_COMPLIANCE,
    ),
    "field-ops": (
        SectionSpec(
            "personnel",
            "Personnel and certifications",
            "field_personnel",
            "No personnel are visible to you.",
            lambda r: str(r["name"]),
            lambda r: (
                f"{r['rank']} · {r['certification']} · "
                + ("expired " if r["status"] == "expired" else "valid until ")
                + str(r["expires"])
            ),
            lambda r: r["status"] == "expired",
        ),
        SectionSpec(
            "training",
            "Training, last 90 days",
            "training_activity",
            "No training in the last 90 days.",
            lambda r: str(r["course"]),
            lambda r: f"{r['start_date']} · {r['attendees']} attendees",
            lambda r: False,
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
        _COMPLIANCE[0],
    ),
    "stratoc": (
        SectionSpec(
            "findings",
            "Correlation findings",
            "correlation_findings",
            "No findings yet. Run the correlation to look for patterns.",
            lambda r: str(r["title"]),
            lambda r: f"{r['severity']} severity · {r['summary']}",
            href=lambda ref: f"/findings/{ref}",
            scoped=False,
        ),
        SectionSpec(
            "detections",
            "Detections, last 48 hours",
            "detections_near_site",
            "No detections in the last 48 hours.",
            lambda r: f"{str(r['object_type']).capitalize()} at {r['site']}",
            lambda r: (
                f"{r['observed_at']} · {r['sensor_id']} · confidence {float(r['confidence']):.0%}"
            ),
            lambda r: False,
        ),
        SectionSpec(
            "sensors",
            "Sensors and sites",
            "sensors_status",
            "No sensors are visible to you.",
            lambda r: f"{r['sensor_id']} · {r['site']}",
            lambda r: f"{r['kind']} · {r['status']}",
            lambda r: r["status"] != "online",
        ),
        *_COMPLIANCE,
    ),
    "briech": (
        SectionSpec(
            "fleet",
            "Aircraft and hours to service",
            "uas_fleet",
            "No aircraft are visible to you.",
            lambda r: str(r["name"]),
            _fleet_detail,
            lambda r: (
                r["status"] not in (None, "in_service")
                or (r["hours_to_service"] is not None and r["hours_to_service"] <= 25)
            ),
            meter=_fleet_meter,
        ),
        SectionSpec(
            "missions",
            "Missions, last 30 days",
            "uas_missions",
            "No missions in the last 30 days.",
            lambda r: f"{r['mission']} · {r['platform']}",
            lambda r: (
                f"{r['mission_date']} · {r['area']} · {r['status']}"
                + (f" · {r['reason']}" if r.get("reason") else "")
            ),
            lambda r: r["status"] == "cancelled",
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
        SectionSpec(
            "contracts",
            "Contracts",
            "contracts_status",
            "No contracts are visible to you.",
            lambda r: f"{r['contract_ref']} · {r['subject']}",
            lambda r: f"{r['client']} · {r['status'].replace('_', ' ')} · ends {r['end_date']}",
            lambda r: r["status"] == "at_risk",
        ),
        *_COMPLIANCE,
    ),
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
    kept: list[Any] = []
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


def _is_site(unit_path: str) -> bool:
    """A field site is a unit below a subsidiary: /eib-group/<subsidiary>/<site>/."""
    parts = unit_path.strip("/").split("/")
    return parts[0] == "eib-group" and len(parts) >= 3


def _reach(path: str, caller: str) -> bool:
    return path.startswith(caller) or caller.startswith(path)


def _division(
    key: str, scope: Scope, names: Mapping[str, str]
) -> tuple[Any, str, Callable[[str], bool]]:
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
        if not any(_is_site(p) and _reach(p, caller) for p in names):
            raise HTTPException(status_code=404, detail="not found")
        return division, caller, _is_site
    if not _reach(division.path, caller):
        raise HTTPException(status_code=404, detail="not found")
    unit_path = division.path if division.path.startswith(caller) else caller
    return division, unit_path, lambda path: path.startswith(unit_path)


def _facts(key: str, sections: list[Section], names: Mapping[str, str], caller: str) -> list[Fact]:
    if key != "field-ops":
        return []
    sites = sorted(p for p in names if _is_site(p) and _reach(p, caller))
    owners = {next(d.name for d in DIVISIONS if d.key == p.split("/")[2]) for p in sites}
    by_key = {s.key: s for s in sections}
    people = {r.label for r in by_key["personnel"].rows} if "personnel" in by_key else set()
    return [
        Fact(label="Field sites", value=", ".join(names[p] for p in sites)),
        Fact(label="Supporting", value=", ".join(sorted(owners))),
        Fact(label="Personnel", value=str(len(people))),
    ]


@router.get("/{key}", response_model=DivisionView)
def division_view(key: str, ctx: CurrentContext, conn: ConnDep) -> DivisionView:
    with guarded(ctx, conn, "read", "dashboard", on_deny="not_found") as scope:
        names = unit_names(conn)
        division, unit_path, keep = _division(key, scope, names)
        labels = Labels.load(conn)
        sections = [
            _build(labels, s, _run(scope, s, unit_path), keep, names) for s in SECTIONS.get(key, ())
        ]
        facts = _facts(key, sections, names, scope.ctx.unit_path)
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
        facts=facts,
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
            for s in _COMPLIANCE
        ]
        scope.read(
            "dashboard",
            sum(len(s.rows) for s in sections),
            item_ids=[r.ref for s in sections for r in s.rows],
        )
    return ComplianceView(generated_at=utc_now_iso(), sections=sections)

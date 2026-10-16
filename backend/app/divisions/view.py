"""A division's dashboard: its sections, each the output of an audited typed tool.

Each section is narrowed to the division's unit, so every figure is a list of records the caller
is cleared for, and every row links to its record and evidence panel. A division the caller
cannot see raises `DivisionNotFound`, exactly like one that does not exist. A section is a derived
item, so it takes the highest classification and the union of compartments of its rows.

The dashboard and the report both build from here, so a report can never show more than the
page does. To add a division's dashboard, add its entry to SECTIONS in `specs.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.authz.labels import Labels
from app.authz.scope import Scope
from app.connectors.base import SourceRecord
from app.data_queries.registry import ToolOutcome, execute_tool
from app.divisions.catalog import DIVISIONS, FIELD_OPS, Division, DivisionNotFound
from app.divisions.specs import SECTIONS, SectionSpec, trace_spec
from app.units import covers, is_site, overlaps, subsidiary_key, unit_names


class TraceRefused(Exception):
    """The serial trace tool refused its parameters; the message says why."""


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


@dataclass(frozen=True, slots=True)
class BuiltDivision:
    division: Division
    sections: list[Section]
    facts: list[Fact]
    labels: Labels


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


def _division(
    key: str, scope: Scope, names: Mapping[str, str]
) -> tuple[Division, str, Callable[[str], bool]]:
    """The division, the unit its tools run on, and which records count as its own.

    DivisionNotFound unless the caller's unit overlaps the division. Field Operations has no unit
    of its own: it is every site unit the caller can reach, so its tools run on the caller's unit
    and the rows are narrowed to site units afterwards.
    """
    division = next((d for d in DIVISIONS if d.key == key), None)
    caller = scope.ctx.unit_path
    if division is None:
        raise DivisionNotFound(key)
    if division.path is None:
        if not any(is_site(p) and overlaps(p, caller) for p in names):
            raise DivisionNotFound(key)
        return division, caller, is_site
    if not overlaps(division.path, caller):
        raise DivisionNotFound(key)
    unit_path = division.path if covers(caller, division.path) else caller
    return division, unit_path, lambda path: covers(unit_path, path)


def _field_ops_facts(sections: list[Section], names: Mapping[str, str], caller: str) -> list[Fact]:
    sites = sorted(p for p in names if is_site(p) and overlaps(p, caller))
    owners = {next(d.name for d in DIVISIONS if d.key == subsidiary_key(p)) for p in sites}
    by_key = {s.key: s for s in sections}
    people = {r.label for r in by_key["personnel"].rows} if "personnel" in by_key else set()
    return [
        Fact(label="Field sites", value=", ".join(names[p] for p in sites)),
        Fact(label="Supporting", value=", ".join(sorted(owners))),
        Fact(label="Personnel", value=str(len(people))),
    ]


def build_division(scope: Scope, key: str) -> BuiltDivision:
    """The division and its sections, run as audited typed tools for the caller.

    Raises DivisionNotFound for a division that is hidden from the caller or does not exist.
    """
    names = unit_names(scope.conn)
    division, unit_path, keep = _division(key, scope, names)
    labels = scope.labels
    sections = [
        _build(labels, s, _run(scope, s, unit_path), keep, names) for s in SECTIONS.get(key, ())
    ]
    facts = _field_ops_facts(sections, names, scope.ctx.unit_path) if key == FIELD_OPS else []
    return BuiltDivision(division, sections, facts, labels)


def build_trace(scope: Scope, key: str, serial: str) -> Section:
    """One serial number's run, QC state and delivery, within the division.

    Raises DivisionNotFound as `build_division` does, and TraceRefused when the tool refuses
    the serial.
    """
    names = unit_names(scope.conn)
    _, unit_path, keep = _division(key, scope, names)
    spec = trace_spec(serial)
    outcome = _run(scope, spec, unit_path)
    if outcome.refusal is not None:
        raise TraceRefused(outcome.refusal)
    return _build(scope.labels, spec, outcome, keep, names)

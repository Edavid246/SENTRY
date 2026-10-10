"""Group home summary: GET /api/v1/home/summary.

One card per business the caller can see (Briech UAS, EIB Stratoc, Giga Forensics, Poctova)
plus Field Operations, the people and sites out in the field. A card carries an alert only
when something genuinely needs attention; a quiet division has no alert at all.

Same rules as every other data endpoint: a guarded read, so the policy decides first, and the
numbers come from audited typed tools filtered inside the query. A division the caller cannot
see is absent from the response, never present-but-locked. An alert is a derived count, so it
takes the highest classification and the union of compartments of what it counts.

Certifications are deliberately not counted here: they are background compliance, shown on
the compliance views, not a reason to interrupt the owner on the landing screen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.audit.chain import utc_now_iso
from app.authz.labels import Labels
from app.correlation.store import list_findings
from app.data_queries.registry import execute_tool
from app.units import GROUP_ROOT, is_site, unit_names

router = APIRouter(prefix="/api/v1/home", tags=["home"])


class AlertPart(BaseModel):
    what: str = Field(description="what is counted, e.g. 'deliveries overdue'")
    count: int


class HomeAlert(BaseModel):
    count: int = Field(description="everything in this division that needs attention")
    parts: list[AlertPart]
    classification: str
    compartments: list[str]


class HomeDivision(BaseModel):
    key: str
    name: str
    tagline: str
    alert: HomeAlert | None = Field(description="null when nothing needs attention")


class HomeSummary(BaseModel):
    generated_at: str
    divisions: list[HomeDivision]


@dataclass(frozen=True, slots=True)
class Division:
    key: str
    name: str
    tagline: str
    path: str | None  # the subsidiary's unit path; None for Field Operations


DIVISIONS = (
    Division("briech", "Briech UAS", "Drones and airborne surveillance", "/eib-group/briech/"),
    Division("stratoc", "EIB Stratoc", "Surveillance and intelligence", "/eib-group/stratoc/"),
    Division("giga", "Giga Forensics", "Digital forensics and evidence", "/eib-group/giga/"),
    Division("poctova", "Poctova", "Protective gear, made and traced", "/eib-group/poctova/"),
    Division("field-ops", "Field Operations", "Personnel and sites in the field", None),
)
FIELD_OPS = "field-ops"

# (tool, params, what it counts). Certifications are left out on purpose, see the module doc.
ATTENTION_TOOLS: tuple[tuple[str, Mapping[str, Any], str], ...] = (
    ("equipment_due_for_maintenance", {"within_days": 0}, "equipment overdue"),
    ("deliveries_overdue", {}, "deliveries overdue"),
    ("production_qc_holds", {}, "production runs on QC hold"),
    ("stock_below_threshold", {}, "stock lines short"),
    ("uas_missions", {"status": "cancelled"}, "UAS missions cancelled"),
    ("custody_gaps", {}, "custody breaks"),
)
FINDINGS_WHAT = "findings open"


@dataclass(frozen=True, slots=True)
class _Member:
    """One counted thing, reduced to what labelling needs (satisfies authz.labels.Labelled)."""

    ref: str
    classification_code: str
    compartments: tuple[str, ...]


def _division_key(unit_path: str, *, finding: bool = False) -> str | None:
    """Which card a record counts toward. A site team (a unit below a subsidiary) belongs to
    Field Operations; a finding about a site stays with the subsidiary that raised it."""
    if not unit_path.startswith(GROUP_ROOT):
        return None
    parts = unit_path.strip("/").split("/")
    if len(parts) < 2:
        return None  # group-level record: no division
    if len(parts) >= 3 and not finding:
        return FIELD_OPS
    return parts[1]


@router.get("/summary", response_model=HomeSummary)
def home_summary(ctx: CurrentContext, conn: ConnDep) -> HomeSummary:
    with guarded(ctx, conn, "read", "dashboard") as scope:
        labels, names = Labels.load(conn), unit_names(conn)
        counted: dict[str, dict[str, list[_Member]]] = {}

        def add(key: str | None, what: str, member: _Member) -> None:
            if key is not None:
                counted.setdefault(key, {}).setdefault(what, []).append(member)

        for tool, params, what in ATTENTION_TOOLS:
            for record in execute_tool(scope, tool, params).records:
                add(
                    _division_key(record.unit_path),
                    what,
                    _Member(record.source_ref, record.classification_code, record.compartments),
                )
        for row in list_findings(scope):
            add(
                _division_key(row.unit_path, finding=True),
                FINDINGS_WHAT,
                _Member(row.key, row.classification_code, tuple(row.compartments)),
            )

        # A division is shown when the caller's unit covers it, or when anything in it is visible.
        site_units = [p for p in names if is_site(p)]
        divisions: list[HomeDivision] = []
        item_ids: list[str] = []
        for division in DIVISIONS:
            by_what = counted.get(division.key, {})
            if division.path is not None:
                covered = division.path.startswith(ctx.unit_path)
            else:
                covered = any(p.startswith(ctx.unit_path) for p in site_units)
            if not covered and not by_what:
                continue
            members = [m for found in by_what.values() for m in found]
            alert = None
            if members:
                label = labels.derive(members)
                alert = HomeAlert(
                    count=len(members),
                    parts=[AlertPart(what=w, count=len(found)) for w, found in by_what.items()],
                    classification=label.code,
                    compartments=list(label.compartments),
                )
                item_ids.extend(m.ref for m in members)
            divisions.append(
                HomeDivision(
                    key=division.key, name=division.name, tagline=division.tagline, alert=alert
                )
            )
        scope.read("dashboard", len(item_ids), item_ids=item_ids)
    return HomeSummary(generated_at=utc_now_iso(), divisions=divisions)

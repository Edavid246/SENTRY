"""Dashboard summary (SPEC 18 step 1): GET /api/v1/dashboard/summary.

Built from the caller's AccessContext. A guarded read (app.api.guard), like
every other data endpoint: the policy decides first (may this role read the
dashboard at all?), then every item is filtered through the policy's `item_visible`, the
SPEC 7.1 rule, before it is added to the response. Nothing the caller may not
see is ever put into a tile. Audited: a decide event and a query event with
the item ids returned.

TILE CONTRACT (Part D keeps this shape; only `stub` flips to false as tiles
become real). Each tile is `{stub, source, title, items[]}`; each item is
`{id, label, value, unit, detail, severity, trend, classification,
compartments, unit_path, unit_name}`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.audit.chain import utc_now_iso
from app.authz.context import AccessContext
from app.authz.labels import Labels
from app.authz.policy import get_policy
from app.authz.scope import Scope
from app.connectors.base import SourceRecord
from app.correlation.store import list_findings
from app.dashboard.fixtures import READINESS, FixtureTile
from app.data_queries.registry import execute_tool
from app.units import unit_names, unit_slug

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class DashboardItem(BaseModel):
    id: str
    label: str
    value: float | None = Field(description="headline number, if the item has one")
    unit: str | None = Field(description="what value counts, e.g. '%' or 'items'")
    detail: str
    severity: str | None = Field(description="low | medium | high, where relevant")
    trend: list[float] = Field(description="oldest to newest, for a flat sparkline")
    classification: str
    compartments: list[str]
    unit_path: str
    unit_name: str = Field(description="readable name of the owning unit")


class DashboardTile(BaseModel):
    stub: bool = Field(description="true while the tile's data is placeholder fixtures")
    source: str
    title: str
    items: list[DashboardItem]


class DashboardTiles(BaseModel):
    readiness: DashboardTile
    maintenance_backlog: DashboardTile
    expiring_certifications: DashboardTile
    recent_findings: DashboardTile


class DashboardSummary(BaseModel):
    generated_at: str
    tiles: DashboardTiles


def _item(
    id: str,
    label: str,
    detail: str,
    classification: str,
    compartments: Sequence[str],
    unit_path: str,
    names: dict[str, str],
    *,
    value: float | None = None,
    unit: str | None = None,
    severity: str | None = None,
    trend: Sequence[float] = (),
) -> DashboardItem:
    return DashboardItem(
        id=id,
        label=label,
        value=value,
        unit=unit,
        detail=detail,
        severity=severity,
        trend=list(trend),
        classification=classification,
        compartments=list(compartments),
        unit_path=unit_path,
        unit_name=names.get(unit_path, unit_path),
    )


def _fixture_tile(
    ctx: AccessContext, tile: FixtureTile, labels: Labels, names: dict[str, str]
) -> DashboardTile:
    """A placeholder tile, every item run through the SPEC 7.1 rule first (stub=true)."""
    items = [
        _item(
            item.id,
            item.label,
            item.detail,
            item.classification,
            item.compartments,
            item.unit_path,
            names,
            value=item.value,
            unit=item.unit,
            severity=item.severity,
            trend=item.trend,
        )
        for item in tile.items
        # An unknown classification code has no rank: fail closed (never shown).
        if (rank := labels.rank(item.classification)) is not None
        and get_policy().item_visible(
            ctx,
            classification_rank=rank,
            compartments=item.compartments,
            unit_path=item.unit_path,
        )
    ]
    return DashboardTile(stub=True, source=tile.source, title=tile.title, items=items)


@dataclass(frozen=True, slots=True)
class ToolTile:
    """A tile counted from a typed tool's rows, one item per owning unit."""

    tool: str
    params: Mapping[str, Any]
    prefix: str
    label: str
    unit: str
    title: str


MAINTENANCE_BACKLOG = ToolTile(
    tool="equipment_due_for_maintenance",
    params={"within_days": 0},
    prefix="MNT",
    label="equipment overdue",
    unit="items",
    title="Maintenance backlog",
)
EXPIRED_CERTIFICATIONS = ToolTile(
    tool="expired_certifications",
    params={},
    prefix="CRT",
    label="certifications expired",
    unit="people",
    title="Certifications expired",
)


def _tool_tile(
    scope: Scope, spec: ToolTile, labels: Labels, names: dict[str, str]
) -> DashboardTile:
    """Group a typed tool's rows by owning unit, one item per unit (stub=false).

    The tool is audited (data_query) and already filtered by the adapter. Each
    item is a derived count, so it takes the highest classification and the
    union of compartments of the records behind it (AGENTS.md).
    """
    groups: dict[str, list[SourceRecord]] = {}
    for record in execute_tool(scope, spec.tool, spec.params).records:
        groups.setdefault(record.unit_path, []).append(record)
    items = []
    for unit_path in sorted(groups):
        members = groups[unit_path]
        label = labels.derive(members)
        items.append(
            _item(
                f"{spec.prefix}-{unit_slug(unit_path)}",
                f"{names.get(unit_path, unit_path)}: {spec.label}",
                ", ".join(sorted(r.source_ref for r in members)),
                label.code,
                label.compartments,
                unit_path,
                names,
                value=len(members),
                unit=spec.unit,
            )
        )
    return DashboardTile(
        stub=False,
        source=f"typed tool {spec.tool} via the demo reference adapter",
        title=spec.title,
        items=items,
    )


def _findings_tile(scope: Scope, names: dict[str, str]) -> DashboardTile:
    """Findings the caller may see (row filter + RLS inside the query)."""
    items = [
        _item(
            row.key,
            row.title,
            row.summary,
            row.classification_code,
            row.compartments,
            row.unit_path,
            names,
            severity=row.severity,
        )
        for row in list_findings(scope)
    ]
    return DashboardTile(
        stub=False,
        source="correlation job (rising_faults), run on demand by the group owner",
        title="Recent findings",
        items=items,
    )


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(ctx: CurrentContext, conn: ConnDep) -> DashboardSummary:
    with guarded(ctx, conn, "read", "dashboard") as scope:
        labels, names = Labels.load(conn), unit_names(conn)
        tiles = DashboardTiles(
            readiness=_fixture_tile(ctx, READINESS, labels, names),
            maintenance_backlog=_tool_tile(scope, MAINTENANCE_BACKLOG, labels, names),
            expiring_certifications=_tool_tile(scope, EXPIRED_CERTIFICATIONS, labels, names),
            recent_findings=_findings_tile(scope, names),
        )
        item_ids = [
            item.id
            for tile in (
                tiles.readiness,
                tiles.maintenance_backlog,
                tiles.expiring_certifications,
                tiles.recent_findings,
            )
            for item in tile.items
        ]
        scope.read("dashboard", len(item_ids), item_ids=item_ids)
    return DashboardSummary(generated_at=utc_now_iso(), tiles=tiles)

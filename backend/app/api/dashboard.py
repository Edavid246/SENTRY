"""Dashboard summary (SPEC 18 step 1): GET /api/v1/dashboard/summary.

Built from the caller's AccessContext. Authorization order matches every other
data endpoint: LocalPolicy.decide first (may this role read the dashboard at
all?), then every item is filtered through `LocalPolicy.item_visible`, the
SPEC 7.1 rule, before it is added to the response. Nothing the caller may not
see is ever put into a tile. Audited: a decide event and a query event with
the item ids returned.

TILE CONTRACT (Part D keeps this shape; only `stub` flips to false as tiles
become real). Each tile is `{stub, source, title, items[]}`; each item is
`{id, label, value, unit, detail, severity, trend, classification,
compartments, unit_path, unit_name}`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.deps import ConnDep, CurrentContext, audit_events
from app.audit.chain import utc_now_iso
from app.authz.context import AccessContext
from app.authz.policy import LocalPolicy
from app.dashboard.fixtures import TILES, FixtureTile

POLICY = LocalPolicy()

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


def _lookups(conn: Connection) -> tuple[dict[str, int], dict[str, str]]:
    ranks = {
        str(r["code"]): int(r["rank"])
        for r in conn.execute(text("SELECT code, rank FROM classification_levels")).mappings()
    }
    names = {
        str(r["path"]): str(r["name"])
        for r in conn.execute(text("SELECT path, name FROM units")).mappings()
    }
    return ranks, names


def _build_tile(
    ctx: AccessContext, tile: FixtureTile, ranks: dict[str, int], names: dict[str, str]
) -> DashboardTile:
    items = [
        DashboardItem(
            id=item.id,
            label=item.label,
            value=item.value,
            unit=item.unit,
            detail=item.detail,
            severity=item.severity,
            trend=list(item.trend),
            classification=item.classification,
            compartments=list(item.compartments),
            unit_path=item.unit_path,
            unit_name=names.get(item.unit_path, item.unit_path),
        )
        for item in tile.items
        # An unknown classification code has no rank: fail closed (never shown).
        if item.classification in ranks
        and POLICY.item_visible(
            ctx,
            classification_rank=ranks[item.classification],
            compartments=item.compartments,
            unit_path=item.unit_path,
        )
    ]
    return DashboardTile(stub=True, source=tile.source, title=tile.title, items=items)


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(ctx: CurrentContext, conn: ConnDep) -> DashboardSummary:
    decision = POLICY.decide(ctx, "read", "dashboard")
    decide_event = {
        "actor": ctx.username,
        "action": "decide",
        "resource": "dashboard",
        "requested": "read",
        "decision": "allow" if decision.allowed else "deny",
        "timestamp": utc_now_iso(),
    }
    if not decision.allowed:
        decide_event["reasons"] = list(decision.reasons)
        audit_events([decide_event])
        raise HTTPException(status_code=403, detail="forbidden")

    ranks, names = _lookups(conn)
    built = {tile.key: _build_tile(ctx, tile, ranks, names) for tile in TILES}
    item_ids = [item.id for tile in built.values() for item in tile.items]
    audit_events(
        [
            decide_event,
            {
                "actor": ctx.username,
                "action": "query",
                "resource": "dashboard",
                "decision": "allow",
                "rows": len(item_ids),
                "item_ids": item_ids,
                "timestamp": utc_now_iso(),
            },
        ]
    )
    return DashboardSummary(generated_at=utc_now_iso(), tiles=DashboardTiles(**built))

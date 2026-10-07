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
from app.correlation.store import list_findings
from app.dashboard.fixtures import TILES, FixtureTile
from app.data_queries.registry import execute_tool

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


# Tiles whose data now comes from the typed tools (stub=false). The rest stay fixtures.
_REAL_TILES: dict[str, dict[str, str]] = {
    "maintenance_backlog": {
        "tool": "equipment_due_for_maintenance",
        "params_within_days": "0",
        "prefix": "MNT",
        "label": "equipment overdue",
        "unit": "items",
        "title": "Maintenance backlog",
    },
    "expiring_certifications": {
        "tool": "expired_certifications",
        "prefix": "CRT",
        "label": "certifications expired",
        "unit": "people",
        "title": "Certifications expired",
    },
}


def _real_tile(
    ctx: AccessContext,
    conn: Connection,
    key: str,
    ranks: dict[str, int],
    names: dict[str, str],
) -> DashboardTile:
    """Group a typed tool's rows by owning unit, one item per unit.

    The tool is audited (data_query) and already filtered by the adapter. Each
    item is a derived count, so it takes the highest classification and the
    union of compartments of the records behind it (AGENTS.md).
    """
    spec = _REAL_TILES[key]
    params = (
        {"within_days": int(spec["params_within_days"])} if "params_within_days" in spec else {}
    )
    outcome = execute_tool(ctx, conn, spec["tool"], params)
    records = outcome.result.records if outcome.result else ()
    groups: dict[str, list] = {}
    for record in records:
        groups.setdefault(record.unit_path, []).append(record)
    items = []
    for unit_path in sorted(groups):
        members = groups[unit_path]
        top = max(members, key=lambda r: ranks.get(r.classification_code, 99))
        slug = unit_path.strip("/").split("/")[-1].upper()
        items.append(
            DashboardItem(
                id=f"{spec['prefix']}-{slug}",
                label=f"{names.get(unit_path, unit_path)}: {spec['label']}",
                value=len(members),
                unit=spec["unit"],
                detail=", ".join(sorted(r.source_ref for r in members)),
                severity=None,
                trend=[],
                classification=top.classification_code,
                compartments=sorted({c for r in members for c in r.compartments}),
                unit_path=unit_path,
                unit_name=names.get(unit_path, unit_path),
            )
        )
    return DashboardTile(
        stub=False,
        source=f"typed tool {spec['tool']} via the demo reference adapter",
        title=spec["title"],
        items=items,
    )


def _findings_tile(ctx: AccessContext, conn: Connection, names: dict[str, str]) -> DashboardTile:
    """Findings the caller may see (row filter + RLS inside the query)."""
    items = [
        DashboardItem(
            id=row.key,
            label=row.title,
            value=None,
            unit=None,
            detail=row.summary,
            severity=row.severity,
            trend=[],
            classification=row.classification_code,
            compartments=row.compartments,
            unit_path=row.unit_path,
            unit_name=names.get(row.unit_path, row.unit_path),
        )
        for row in list_findings(conn, ctx)
    ]
    return DashboardTile(
        stub=False,
        source="correlation job (rising_faults), run on demand by a commander",
        title="Recent findings",
        items=items,
    )


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
    fixtures = {tile.key: tile for tile in TILES}
    built = {
        key: (
            _real_tile(ctx, conn, key, ranks, names)
            if key in _REAL_TILES
            else _findings_tile(ctx, conn, names)
            if key == "recent_findings"
            else _build_tile(ctx, fixtures[key], ranks, names)
        )
        for key in DashboardTiles.model_fields
    }
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

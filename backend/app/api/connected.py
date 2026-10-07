"""Connected-technology map data (SPEC 10.5): GET /api/v1/connected/map.

Read-only GeoJSON over the synthetic surveillance and UAS records, for the MapLibre view
(no external tiles; AGENTS.md air-gap rules). Same order as every data endpoint: decide
first, then the adapter reads with the policy row filter + RLS inside the query, so a
feature the caller may not see is never read, let alone serialised. Audited: a decide
event and a query event listing the record ids returned.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import ConnDep, CurrentContext, audit_events
from app.audit.chain import utc_now_iso
from app.authz.policy import LocalPolicy
from app.clock import demo_now, demo_today
from app.connectors.base import RecordFilter, SourceRecord
from app.connectors.demo import DemoReferenceAdapter

POLICY = LocalPolicy()
ADAPTER = DemoReferenceAdapter()

router = APIRouter(prefix="/api/v1/connected", tags=["connected"])


def _properties(record: SourceRecord, kind: str, label: str, **extra: Any) -> dict[str, Any]:
    return {
        "ref": record.source_ref,
        "kind": kind,
        "label": label,
        "classification": record.classification_code,
        "compartments": list(record.compartments),
        "unit_path": record.unit_path,
        "source_system": record.source_system,
        **extra,
    }


def _point(record: SourceRecord, kind: str, label: str, **extra: Any) -> dict[str, Any]:
    data = record.data
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [data["lon"], data["lat"]]},
        "properties": _properties(record, kind, label, **extra),
    }


@router.get("/map")
def connected_map(
    ctx: CurrentContext,
    conn: ConnDep,
    hours: Annotated[int, Query(ge=1, le=720)] = 48,
    mission_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    """Sensors, recent detections and mission tracks the caller may see (never more)."""
    decision = POLICY.decide(ctx, "retrieve", "record")
    decide_event = {
        "actor": ctx.username,
        "action": "decide",
        "resource": "connected_map",
        "requested": "retrieve",
        "decision": "allow" if decision.allowed else "deny",
        "timestamp": utc_now_iso(),
    }
    if not decision.allowed:
        decide_event["reasons"] = list(decision.reasons)
        audit_events([decide_event])
        # Roles without data access get an empty map, not a hint about what exists.
        return {"type": "FeatureCollection", "features": [], "generated_at": utc_now_iso()}

    now = demo_now()
    start = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    mission_start = (demo_today() - timedelta(days=mission_days)).isoformat()

    features: list[dict[str, Any]] = []
    refs: list[str] = []
    for sensor in ADAPTER.search(conn, ctx, RecordFilter(entity_type="Sensor")):
        features.append(
            _point(
                sensor,
                "sensor",
                f"{sensor.data['sensor_id']} ({sensor.data['site']})",
                status=sensor.data.get("status"),
            )
        )
        refs.append(sensor.source_ref)
    detections = ADAPTER.search(conn, ctx, RecordFilter(entity_type="Detection"))
    for det in sorted(detections, key=lambda r: r.data["observed_at"]):
        if not start <= det.data["observed_at"] <= end:
            continue
        features.append(
            _point(
                det,
                "detection",
                f"{det.data['object_type']} at {det.data['site']}",
                observed_at=det.data["observed_at"],
                object_type=det.data["object_type"],
                confidence=det.data["confidence"],
                site=det.data["site"],
            )
        )
        refs.append(det.source_ref)
    missions = ADAPTER.search(
        conn,
        ctx,
        RecordFilter(
            entity_type="Mission",
            date_field="mission_date",
            on_or_before=demo_today(),
        ),
    )
    for msn in sorted(missions, key=lambda r: r.data["mission_date"]):
        if msn.data["mission_date"] < mission_start:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": msn.data["track"]},
                "properties": _properties(
                    msn,
                    "mission",
                    f"{msn.data['mission']} ({msn.data['status']})",
                    status=msn.data["status"],
                    mission_date=msn.data["mission_date"],
                    track_kind=msn.data["track_kind"],
                    area=msn.data["area"],
                    reason=msn.data["reason"],
                ),
            }
        )
        refs.append(msn.source_ref)

    audit_events(
        [
            decide_event,
            {
                "actor": ctx.username,
                "action": "query",
                "resource": "connected_map",
                "decision": "allow",
                "rows": len(refs),
                "record_ids": refs,
                "timestamp": utc_now_iso(),
            },
        ]
    )
    return {"type": "FeatureCollection", "features": features, "generated_at": utc_now_iso()}

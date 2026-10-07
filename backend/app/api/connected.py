"""Connected-technology map data (SPEC 10.5): GET /api/v1/connected/map.

Read-only GeoJSON over the synthetic surveillance and UAS records, for the MapLibre view
(no external tiles; AGENTS.md air-gap rules). Same order as every data endpoint: decide
first, then the adapter reads with the policy row filter + RLS inside the query, so a
feature the caller may not see is never read, let alone serialised. Audited: a decide
event and a query event listing the record ids returned.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import ConnDep, CurrentContext, audit_events, decide_event, query_event
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


def _detection_feature(det: SourceRecord) -> dict[str, Any]:
    return _point(
        det,
        "detection",
        f"{det.data['object_type']} at {det.data['site']}",
        observed_at=det.data["observed_at"],
        object_type=det.data["object_type"],
        confidence=det.data["confidence"],
        site=det.data["site"],
    )


_TS = "%Y-%m-%dT%H:%M:%SZ"


def _parse_ts(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be an ISO timestamp") from None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


@router.get("/replay")
def connected_replay(
    ctx: CurrentContext,
    after: Annotated[str | None, Query()] = None,
    upto: Annotated[str | None, Query()] = None,
    hours: Annotated[int, Query(ge=1, le=720)] = 48,
) -> dict[str, Any]:
    """STUB live feed: detections the caller may see, replayed in time order.

    The synthetic detections are the "stream"; the client drives a replay clock and polls
    with `after` (the last observed_at it has) and `upto` (the clock). Stateless: the
    server holds no cursor. Stream and policy row filter + RLS come from the adapter, so
    an event the caller may not see is never read. Only non-empty batches are audited,
    with the ids delivered.
    """
    now = demo_now()
    window_start = now - timedelta(hours=hours)
    since = _parse_ts(after, "after") if after else window_start - timedelta(seconds=1)
    limit = min(_parse_ts(upto, "upto"), now) if upto else now
    decision = POLICY.decide(ctx, "retrieve", "record")
    decision_event = decide_event(ctx, decision, resource="connected_replay", requested="retrieve")
    out: dict[str, Any] = {
        "window_start": window_start.strftime(_TS),
        "window_end": now.strftime(_TS),
        "events": [],
    }
    if not decision.allowed:
        audit_events([decision_event])
        return out
    events = [
        r
        for r in ADAPTER.stream(ctx, max(since, window_start - timedelta(seconds=1)))
        if r.data["observed_at"] <= limit.strftime(_TS)
    ]
    out["events"] = [_detection_feature(r) for r in events]
    if events:
        audit_events(
            [
                decision_event,
                query_event(
                    ctx,
                    "connected_replay",
                    len(events),
                    record_ids=[r.source_ref for r in events],
                ),
            ]
        )
    return out


@router.get("/map")
def connected_map(
    ctx: CurrentContext,
    conn: ConnDep,
    hours: Annotated[int, Query(ge=1, le=720)] = 48,
    mission_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    """Sensors, recent detections and mission tracks the caller may see (never more)."""
    decision = POLICY.decide(ctx, "retrieve", "record")
    decision_event = decide_event(ctx, decision, resource="connected_map", requested="retrieve")
    if not decision.allowed:
        audit_events([decision_event])
        # Roles without data access get an empty map, not a hint about what exists.
        return {"type": "FeatureCollection", "features": [], "generated_at": utc_now_iso()}

    now = demo_now()
    start = (now - timedelta(hours=hours)).strftime(_TS)
    end = now.strftime(_TS)
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
        features.append(_detection_feature(det))
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

    audit_events([decision_event, query_event(ctx, "connected_map", len(refs), record_ids=refs)])
    return {"type": "FeatureCollection", "features": features, "generated_at": utc_now_iso()}

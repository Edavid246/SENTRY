"""Connected technology: surveillance, UAS missions, sensors."""

from __future__ import annotations

import hashlib

from app.seed.records.common import _SITE4, _STRATOC, _days_from_today, _hours_from_now

# Connected-technology demo data (surveillance + UAS + forensics; docs/STUBS.md). Synthetic, shaped
# like ONVIF analytics events, MAVLink/MISB ST 0601 mission logs and CASE/UCO evidence records;
# the adapter's translation layer is the only place that shape matters (SPEC 11.2). Detection
# times are hour offsets from demo_now() (noon on the demo date); mission dates are day offsets.
# Coordinates are fictitious demo positions on open rural land (Niger State), chosen against the
# local OpenStreetMap extract: no buildings within ~1 km and no military or airfield features
# in the area, so no real place reads as a demo site (web/public/basemap/README.md).
# Visibility follows the SPEC 7.1 rule and is pinned in tests/authz/expected.py.
_SITES = {
    "DEP-B4": (5.460, 9.350),
    "DEP-B2": (5.400, 9.310),
    "UAS-HANGAR": (5.490, 9.390),
}
_CT = "connected-tech-demo"
_STATE = "Niger"  # every demo site is on fictitious rural land in Niger State
_UAS_WING = "/eib-group/briech/"


def _sensor(ref, classification, compartments, unit_path, sensor_id, site, status="online"):
    lon, lat = _SITES[site]
    data = {"sensor_id": sensor_id, "site": site, "kind": "camera", "status": status}
    data["state"] = _STATE
    data |= {"lon": lon, "lat": lat, "format": "ONVIF-style (synthetic)"}
    return (ref, "Sensor", _CT, classification, compartments, unit_path, data)


def _detection(
    ref, classification, compartments, unit_path, hours, sensor_id, site, kind, confidence, d=(0, 0)
):
    lon, lat = _SITES[site]
    data = {
        "sensor_id": sensor_id,
        "site": site,
        "state": _STATE,
        "object_type": kind,
        "confidence": confidence,
        "observed_at": _hours_from_now(hours),
        "lon": round(lon + d[0], 4),
        "lat": round(lat + d[1], 4),
        "format": "ONVIF-style analytics event (synthetic)",
    }
    return (ref, "Detection", _CT, classification, compartments, unit_path, data)


def _mission(ref, classification, offset, mission, platform, status, area, reason, route):
    data = {
        "mission": mission,
        "platform": platform,
        "status": status,
        "mission_date": _days_from_today(offset),
        "area": area,
        "state": _STATE,
        "reason": reason,
        "track_kind": "flown" if status == "completed" else "planned",
        "track": [list(point) for point in route],
        "format": "MAVLink/MISB ST 0601 style (synthetic)",
    }
    return (ref, "Mission", _CT, classification, ["UAS-OPS"], _UAS_WING, data)


_ROUTE_B4 = ((5.490, 9.390, 120), (5.475, 9.370, 150), (5.460, 9.350, 150), (5.450, 9.360, 130))
_ROUTE_B2 = ((5.490, 9.390, 120), (5.450, 9.350, 140), (5.400, 9.310, 140), (5.420, 9.330, 120))
RECORDS = [
    _sensor("REC-046", "restricted", [], _SITE4, "SEN-B4-01", "DEP-B4"),
    _sensor("REC-047", "restricted", [], _STRATOC, "SEN-B2-01", "DEP-B2"),
    _detection("REC-048", "restricted", [], _SITE4, -6, "SEN-B4-01", "DEP-B4", "person", 0.91),
    _detection("REC-049", "restricted", [], _SITE4, -20, "SEN-B4-01", "DEP-B4", "vehicle", 0.88),
    _detection("REC-050", "restricted", [], _SITE4, -70, "SEN-B4-01", "DEP-B4", "person", 0.79),
    _detection("REC-051", "restricted", [], _STRATOC, -10, "SEN-B2-01", "DEP-B2", "vehicle", 0.93),
    _detection("REC-052", "restricted", [], _STRATOC, -30, "SEN-B2-01", "DEP-B2", "person", 0.84),
    _detection(
        "REC-053",
        "confidential",
        ["UAS-OPS"],
        _UAS_WING,
        -5,
        "SEN-UW-01",
        "UAS-HANGAR",
        "small aircraft",
        0.72,
        d=(0.002, 0.001),
    ),  # fmt: skip
    _detection("REC-054", "confidential", [], _SITE4, -3, "SEN-B4-01", "DEP-B4", "vehicle", 0.95),
    _mission(
        "REC-055",
        "confidential",
        -9,
        "MSN-101",
        "UAS-14",
        "completed",
        "DEP-B4 perimeter",
        "Routine perimeter patrol flown as planned",
        _ROUTE_B4,
    ),  # fmt: skip
    _mission(
        "REC-056",
        "confidential",
        -5,
        "MSN-102",
        "UAS-14",
        "cancelled",
        "DEP-B4 perimeter",
        "Platform UAS-14 grounded: gimbal fault, spare part short",
        _ROUTE_B4,
    ),  # fmt: skip
    _mission(
        "REC-057",
        "confidential",
        -2,
        "MSN-103",
        "UAS-15",
        "cancelled",
        "DEP-B2 approach",
        "Crosswind above platform limit",
        _ROUTE_B2,
    ),  # fmt: skip
    _mission(
        "REC-058",
        "confidential",
        -1,
        "MSN-104",
        "UAS-15",
        "completed",
        "DEP-B2 approach",
        "Rescheduled patrol flown as planned",
        _ROUTE_B2,
    ),  # fmt: skip
    _mission(
        "REC-059",
        "confidential",
        -40,
        "MSN-105",
        "UAS-14",
        "cancelled",
        "DEP-B4 perimeter",
        "Airspace deconfliction conflict",
        _ROUTE_B4,
    ),  # fmt: skip
    _mission(
        "REC-060",
        "secret",
        -3,
        "MSN-106",
        "UAS-14",
        "cancelled",
        "Northern corridor",
        "Tasking withdrawn by Command",
        _ROUTE_B2,
    ),  # fmt: skip
    (
        "REC-061",
        "EvidenceItem",
        "forensics-demo",
        "secret",
        ["FORENSICS"],
        "/eib-group/giga/",
        {
            "evidence_ref": "EV-014-01",
            "case_ref": "FR-2026-014",
            "item": "Seized handset image",
            "kind": "mobile device",
            "status": "in analysis",
            "sha256": hashlib.sha256(b"EV-014-01").hexdigest(),
            "format": "CASE/UCO style (synthetic)",
        },
    ),  # fmt: skip
    (
        "REC-062",
        "CustodyEvent",
        "forensics-demo",
        "secret",
        ["FORENSICS"],
        "/eib-group/giga/",
        {
            "evidence_ref": "EV-014-01",
            "case_ref": "FR-2026-014",
            "action": "transferred to lab",
            "from_holder": "A. Danjuma",
            "to_holder": "Lab store LS-1",
            "event_date": "2026-06-04",
            "format": "CASE/UCO style (synthetic)",
        },
    ),  # fmt: skip
]

"""Seed the gateway database with the fictitious demo corpus (AGENTS.md).

Deterministic uuid5 ids plus a full delete-then-insert make the seed
idempotent: running it twice leaves identical row counts. The audit table is
never touched (append-only, SPEC 14.2). Demo data only — fictitious people,
units, documents and records.

Run:  uv run python -m app.seed            (main gateway DB, as owner)
Tests: app.seed.run(test_owner_database_url)
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from argon2 import PasswordHasher
from sqlalchemy import create_engine, delete

from app.audit.models import AuditEvent
from app.authz.models import (
    ClassificationLevel,
    Compartment,
    Unit,
    User,
    UserCompartment,
)
from app.clock import UTC_TS_FORMAT, demo_now, demo_today
from app.config import get_settings
from app.connectors.models import CanonicalRecord, SourceSystem
from app.correlation.models import Finding
from app.knowledge.models import Chunk, Conversation, Document, Message

DEMO_PASSWORD = "Demo!Gateway2026"

CLASSIFICATION_LEVELS = [
    {"code": "unclassified", "name": "Open", "rank": 0},
    {"code": "restricted", "name": "Internal", "rank": 1},
    {"code": "confidential", "name": "Confidential", "rank": 2},
    {"code": "secret", "name": "Government-sensitive", "rank": 3},
]

COMPARTMENTS = [
    {"code": "UAS-OPS", "name": "UAS Operations", "description": "Unmanned air systems"},
    {"code": "FORENSICS", "name": "Forensics", "description": "Digital forensics cases"},
    # Client separation: generic agency labels, no real agency names on demo data.
    {"code": "CLIENT-A", "name": "Client Agency A", "description": "Client Agency A contracts"},
    {"code": "CLIENT-B", "name": "Client Agency B", "description": "Client Agency B contracts"},
    {"code": "CLIENT-C", "name": "Client Agency C", "description": "Client Agency C contracts"},
    {"code": "CLIENT-D", "name": "Client Agency D", "description": "Client Agency D contracts"},
]

UNITS = [
    {"path": "/eib-group/", "name": "EIB Group", "parent": None, "depth": 0},
    {"path": "/eib-group/stratoc/", "name": "EIB Stratoc", "parent": "/eib-group/", "depth": 1},
    {
        "path": "/eib-group/stratoc/site-4/",
        "name": "Stratoc Site Team 4",
        "parent": "/eib-group/stratoc/",
        "depth": 2,
    },
    {"path": "/eib-group/briech/", "name": "Briech UAS", "parent": "/eib-group/", "depth": 1},
    {"path": "/eib-group/giga/", "name": "Giga Forensics", "parent": "/eib-group/", "depth": 1},
    {"path": "/eib-group/poctova/", "name": "Poctova", "parent": "/eib-group/", "depth": 1},
    {"path": "/group-it/", "name": "Group IT", "parent": None, "depth": 0},
    {"path": "/group-audit/", "name": "Group Audit", "parent": None, "depth": 0},
]

# SPEC 7.4 demo users; data_scope none/audit for sysadmin/auditor (SPEC 7.3).
USERS = [
    {
        "username": "owner",
        "display_name": "Group Owner",
        "role": "commander",
        "unit": "/eib-group/",
        "clearance": "secret",
        "compartments": [
            "UAS-OPS",
            "FORENSICS",
            "CLIENT-A",
            "CLIENT-B",
            "CLIENT-C",
            "CLIENT-D",
        ],
        "data_scope": "standard",
    },
]

# ARCHIVED accounts: not seeded, so they cannot log in. The authorization test matrix
# still needs them (tests seed with include_archived=True). To restore one for the
# product, move its entry back into USERS above and reseed.
ARCHIVED_USERS = [
    {
        "username": "logistics.head",
        "display_name": "Head of Production & Logistics",
        "role": "logistics",
        "unit": "/eib-group/stratoc/",
        "clearance": "confidential",
        "compartments": [],
        "data_scope": "standard",
    },
    {
        "username": "coo",
        "display_name": "Group COO (limited view)",
        "role": "training",
        "unit": "/eib-group/stratoc/site-4/",
        "clearance": "restricted",
        "compartments": [],
        "data_scope": "standard",
    },
    {
        "username": "briech.lead",
        "display_name": "Briech UAS Lead",
        "role": "uas_ops",
        "unit": "/eib-group/briech/",
        "clearance": "confidential",
        "compartments": ["UAS-OPS", "CLIENT-A"],
        "data_scope": "standard",
    },
    {
        "username": "group.it",
        "display_name": "Group IT",
        "role": "sysadmin",
        "unit": "/group-it/",
        "clearance": None,
        "compartments": [],
        "data_scope": "none",
    },
    {
        "username": "group.audit",
        "display_name": "Group Audit",
        "role": "auditor",
        "unit": "/group-audit/",
        "clearance": "restricted",
        "compartments": [],
        "data_scope": "audit",
    },
]


SOURCE_SYSTEMS = [
    {"name": "documents-ref", "adapter_type": "documents", "status": "connected"},
    {"name": "logistics-ref", "adapter_type": "logistics", "status": "connected"},
    {"name": "training-ref", "adapter_type": "training", "status": "connected"},
    {"name": "personnel-ref", "adapter_type": "personnel", "status": "connected"},
    {"name": "connected-tech-demo", "adapter_type": "connected-tech", "status": "connected"},
    {"name": "forensics-demo", "adapter_type": "forensics", "status": "connected"},
    {"name": "contracts-demo", "adapter_type": "contracts", "status": "connected"},
    {"name": "production-demo", "adapter_type": "production", "status": "connected"},
]

# (ref, title, classification, compartments, unit path)
DOCUMENTS = [
    ("DOC-001", "Vehicle Maintenance Policy", "restricted", [], "/eib-group/stratoc/"),
    (
        "DOC-002",
        "EIB Stratoc Fuel Consumption Report Q2",
        "confidential",
        [],
        "/eib-group/stratoc/",
    ),
    (
        "DOC-003",
        "Stratoc Site Team 4 Training Schedule August",
        "restricted",
        [],
        "/eib-group/stratoc/site-4/",
    ),
    (
        "DOC-004",
        "Operation Northern Star After-Action Review",
        "secret",
        ["UAS-OPS", "FORENSICS"],
        "/eib-group/",
    ),
    ("DOC-005", "UAS Contingency Deployment Plan", "secret", ["UAS-OPS"], "/eib-group/briech/"),
    ("DOC-006", "UAS Maintenance Schedule", "confidential", ["UAS-OPS"], "/eib-group/briech/"),
    (
        "DOC-007",
        "Digital Forensics Handling Procedure",
        "secret",
        ["FORENSICS"],
        "/eib-group/giga/",
    ),
    ("DOC-008", "EIB Group Quarterly Equipment Audit", "restricted", [], "/eib-group/"),
    ("DOC-009", "EIB Stratoc Ammunition Stocktake", "confidential", [], "/eib-group/stratoc/"),
    ("DOC-010", "EIB Group Duty Roster Template", "unclassified", [], "/eib-group/"),
    ("DOC-011", "Group IT Access Review Procedure", "restricted", [], "/group-it/"),
    ("DOC-012", "Inspectorate Visit Schedule 2026", "restricted", [], "/group-audit/"),
    ("DOC-013", "Spare Parts Ordering Guide", "unclassified", [], "/eib-group/stratoc/"),
    ("DOC-014", "EIB Group Contingency Order Delta", "secret", [], "/eib-group/"),
    (
        "DOC-015",
        "UAS Payload Calibration Notes",
        "confidential",
        ["UAS-OPS", "FORENSICS"],
        "/eib-group/briech/",
    ),
    ("DOC-016", "Training Readiness Summary Q3", "confidential", [], "/eib-group/stratoc/site-4/"),
]

# (ref, entity_type, source, classification, compartments, unit path, data)
RECORDS = [
    (
        "REC-001",
        "Equipment",
        "logistics-ref",
        "restricted",
        [],
        "/eib-group/stratoc/",
        {
            "equipment_id": "EQ-2201",
            "name": "Generator 15kW",
            "location": "EIB Stratoc depot",
            "service_due": "2026-11-01",
            "status": "in_service",
        },
    ),
    (
        "REC-002",
        "TrainingEvent",
        "training-ref",
        "restricted",
        [],
        "/eib-group/stratoc/site-4/",
        {
            "course": "Rifle Refresher",
            "start_date": "2026-08-11",
            "attendees": 24,
            "unit": "Stratoc Site Team 4",
        },
    ),
    (
        "REC-003",
        "WorkOrder",
        "logistics-ref",
        "confidential",
        [],
        "/eib-group/stratoc/site-4/",
        {
            "wo_ref": "WO-0455",
            "equipment": "Water Purifier WP-7",
            "state": "awaiting_parts",
            "raised": "2026-09-08",
        },
    ),
    (
        "REC-004",
        "Flight",
        "connected-tech-demo",
        "secret",
        ["UAS-OPS"],
        "/eib-group/briech/",
        {"tail": "UAS-14", "mission": "MSN-091", "duration_min": 47, "battery_pct_end": 61},
    ),
    (
        "REC-005",
        "StockItem",
        "logistics-ref",
        "restricted",
        [],
        "/eib-group/stratoc/",
        {"item": "Cold weather kit", "depot": "DEP-B2", "quantity": 320, "threshold": 150},
    ),
    (
        "REC-006",
        "Qualification",
        "personnel-ref",
        "restricted",
        [],
        "/eib-group/",
        {
            "person": "Sgt N. Yusuf",
            "qualification": "Armoured vehicle driver",
            "expires": "2027-02-28",
        },
    ),
    (
        "REC-007",
        "Case",
        "forensics-demo",
        "secret",
        ["FORENSICS"],
        "/eib-group/giga/",
        {"case_ref": "FR-2026-014", "opened": "2026-06-03", "items": 5, "state": "open"},
    ),
    (
        "REC-008",
        "WorkOrder",
        "logistics-ref",
        "restricted",
        [],
        "/group-it/",
        {
            "wo_ref": "WO-0461",
            "equipment": "Badge printer GRP-IT",
            "state": "closed",
            "raised": "2026-09-21",
        },
    ),
    (
        "REC-009",
        "Equipment",
        "connected-tech-demo",
        "confidential",
        ["UAS-OPS"],
        "/eib-group/briech/",
        {
            "equipment_id": "UAS-14",
            "name": "Raven-II UAS",
            "flight_hours": 142.5,
            "next_service": "2026-12-15",
        },
    ),
    (
        "REC-010",
        "StockItem",
        "logistics-ref",
        "restricted",
        [],
        "/eib-group/stratoc/",
        {"item": "Generator oil 5L", "depot": "DEP-B2", "quantity": 45, "threshold": 60},
    ),
]


def _days_from_today(offset: int) -> str:
    # DEMO_DATE (app.clock) pins this so a re-seed reproduces the same dates on any day.
    return (demo_today() + timedelta(days=offset)).isoformat()


# Data-pathway demo rows (Task 2). Dates are offsets from the seed date so
# "overdue" and "due in 15 days" stay true whenever the corpus is re-seeded;
# the offsets are the contract the tests rely on. Equipment carries
# `maintenance_due_date`, qualifications carry `expires` (the adapter maps
# both to the tool columns). REC-001/REC-009 keep their original field names
# and are deliberately not matched by the maintenance tool.
def _equipment(ref, source, classification, compartments, unit_path, offset, **fields):
    data = {**fields, "maintenance_due_date": _days_from_today(offset)}
    return (ref, "Equipment", source, classification, compartments, unit_path, data)


def _qualification(ref, classification, compartments, unit_path, offset, **fields):
    data = {**fields, "expires": _days_from_today(offset)}
    return (ref, "Qualification", "personnel-ref", classification, compartments, unit_path, data)


def _fault(ref, classification, unit_path, offset, equipment, description):
    data = {
        "equipment": equipment,
        "description": description,
        "reported_on": _days_from_today(offset),
    }
    return (ref, "FaultReport", "logistics-ref", classification, [], unit_path, data)


def _training(ref, classification, compartments, unit_path, offset, course, attendees, unit):
    data = {
        "course": course,
        "start_date": _days_from_today(offset),
        "attendees": attendees,
        "unit": unit,
    }
    return (ref, "TrainingEvent", "training-ref", classification, compartments, unit_path, data)


_SITE4 = "/eib-group/stratoc/site-4/"
_STRATOC = "/eib-group/stratoc/"
RECORDS += [
    _equipment(
        "REC-011",
        "logistics-ref",
        "restricted",
        [],
        _SITE4,
        -12,
        equipment_id="EQ-3101",
        name="Armoured Personnel Carrier APC-12",
        type="vehicle",
        status="in_service",
        location="Stratoc Site Team 4 motor pool",
    ),
    _equipment(
        "REC-012",
        "logistics-ref",
        "restricted",
        [],
        _SITE4,
        15,
        equipment_id="EQ-3102",
        name="Cargo Truck 5T",
        type="vehicle",
        status="in_service",
        location="Stratoc Site Team 4 motor pool",
    ),
    _equipment(
        "REC-013",
        "logistics-ref",
        "restricted",
        [],
        _STRATOC,
        10,
        equipment_id="EQ-3103",
        name="Field Radio Set FR-9",
        type="communications",
        status="in_service",
        location="EIB Stratoc signals store",
    ),
    _equipment(
        "REC-014",
        "logistics-ref",
        "confidential",
        [],
        _STRATOC,
        -3,
        equipment_id="EQ-3104",
        name="Generator 40kW",
        type="power",
        status="degraded",
        location="EIB Stratoc depot",
    ),
    _equipment(
        "REC-015",
        "logistics-ref",
        "confidential",
        [],
        _SITE4,
        20,
        equipment_id="EQ-3105",
        name="Water Purifier WP-7",
        type="utility",
        status="awaiting_parts",
        location="Stratoc Site Team 4 camp",
    ),
    _equipment(
        "REC-016",
        "logistics-ref",
        "restricted",
        [],
        "/eib-group/",
        15,
        equipment_id="EQ-3106",
        name="Recovery Vehicle RV-2",
        type="vehicle",
        status="in_service",
        location="EIB Group workshop",
    ),
    _equipment(
        "REC-017",
        "logistics-ref",
        "restricted",
        [],
        _SITE4,
        90,
        equipment_id="EQ-3107",
        name="Field Kitchen FK-3",
        type="catering",
        status="in_service",
        location="Stratoc Site Team 4 camp",
    ),
    _equipment(
        "REC-018",
        "connected-tech-demo",
        "secret",
        ["UAS-OPS"],
        "/eib-group/briech/",
        5,
        equipment_id="UAS-15",
        name="Raven-II UAS (tail 15)",
        type="uas",
        status="in_service",
        location="Briech UAS hangar",
    ),
    _qualification(
        "REC-019",
        "restricted",
        [],
        _SITE4,
        -30,
        name="Cpl B. Ibrahim",
        rank="Corporal",
        certification="First Aid",
    ),
    _qualification(
        "REC-020",
        "restricted",
        [],
        _SITE4,
        -10,
        name="Pte C. Nwosu",
        rank="Private",
        certification="Heavy Vehicle Driver",
    ),
    _qualification(
        "REC-021",
        "restricted",
        [],
        _STRATOC,
        -45,
        name="Sgt D. Okoye",
        rank="Sergeant",
        certification="Rifle Marksman",
    ),
    _qualification(
        "REC-022",
        "confidential",
        [],
        _STRATOC,
        -5,
        name="Capt E. Lawal",
        rank="Captain",
        certification="Signals Operator",
    ),
    _qualification(
        "REC-023",
        "secret",
        ["UAS-OPS"],
        "/eib-group/briech/",
        -20,
        name="Lt F. Garba",
        rank="Lieutenant",
        certification="UAS Pilot",
    ),
    _qualification(
        "REC-024",
        "restricted",
        [],
        "/eib-group/",
        -60,
        name="WO G. Abubakar",
        rank="Warrant Officer",
        certification="Armoured Vehicle Driver",
    ),
    _qualification(
        "REC-025",
        "restricted",
        [],
        _SITE4,
        200,
        name="Sgt H. Danladi",
        rank="Sergeant",
        certification="First Aid",
    ),
    # Stock rows for stock_below_threshold: one short and one healthy at Stratoc Site Team 4.
    (
        "REC-026",
        "StockItem",
        "logistics-ref",
        "restricted",
        [],
        _SITE4,
        {"item": "Water purifier filter", "depot": "DEP-B4", "quantity": 8, "threshold": 20},
    ),
    (
        "REC-027",
        "StockItem",
        "logistics-ref",
        "restricted",
        [],
        _SITE4,
        {"item": "Ration pack 24h", "depot": "DEP-B4", "quantity": 400, "threshold": 250},
    ),
    # Planted correlation pattern (Part D2): fault reports rise in Stratoc Site Team 4 while
    # its maintainers' certifications lapse (REC-041/042) and a spare-part line is
    # short (REC-026). EIB Stratoc's fault rate stays flat as the control. The newest
    # Site 4 report is Secret, so the derived finding inherits Secret (SPEC 7.2).
    # Windows are relative to the seed date: 42..22 days ago vs the last 21 days.
    _fault("REC-028", "restricted", _SITE4, -40, "APC-12", "Hydraulic leak, rear ramp"),
    _fault("REC-029", "restricted", _SITE4, -30, "Cargo Truck 5T", "Brake pressure warning"),
    _fault("REC-030", "restricted", _SITE4, -18, "APC-12", "Transmission slip under load"),
    _fault("REC-031", "restricted", _SITE4, -14, "Cargo Truck 5T", "Alternator failure"),
    _fault("REC-032", "restricted", _SITE4, -11, "Water Purifier WP-7", "Filter housing crack"),
    _fault("REC-033", "restricted", _SITE4, -8, "APC-12", "Coolant loss"),
    _fault("REC-034", "restricted", _SITE4, -5, "Cargo Truck 5T", "Steering play"),
    _fault("REC-035", "restricted", _SITE4, -3, "Water Purifier WP-7", "Pump seal failure"),
    _fault(
        "REC-036", "secret", _SITE4, -1, "Command vehicle secure radio", "Encryption module fault"
    ),
    _fault("REC-037", "restricted", _STRATOC, -38, "Generator 15kW", "Fuel pump fault"),
    _fault("REC-038", "restricted", _STRATOC, -28, "Generator 15kW", "Exhaust leak"),
    _fault("REC-039", "restricted", _STRATOC, -15, "Light Truck 2T", "Tyre wear"),
    _fault("REC-040", "restricted", _STRATOC, -6, "Light Truck 2T", "Clutch wear"),
    _qualification(
        "REC-041",
        "restricted",
        [],
        _SITE4,
        -18,
        name="Cpl J. Lawal",
        rank="Corporal",
        certification="Vehicle Maintainer",
    ),
    # training_activity data: REC-002 (fixed date) is the Site 4 baseline; these add a Stratoc
    # event, a Briech UAS event (Confidential, UAS-OPS) and one old Site 4 event outside a quarter.
    _training("REC-043", "restricted", [], _STRATOC, -35, "Vehicle Recovery", 18, "EIB Stratoc"),
    _training(
        "REC-044",
        "confidential",
        ["UAS-OPS"],
        "/eib-group/briech/",
        -20,
        "UAS Flight Qualification",
        6,
        "Briech UAS",
    ),
    _training(
        "REC-045", "restricted", [], _SITE4, -200, "Cold Weather Drills", 30, "Stratoc Site Team 4"
    ),
    _qualification(
        "REC-042",
        "restricted",
        [],
        _SITE4,
        -9,
        name="Pte S. Ogunleye",
        rank="Private",
        certification="Vehicle Maintainer",
    ),
]


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


def _hours_from_now(offset: int) -> str:
    return (demo_now() + timedelta(hours=offset)).strftime(UTC_TS_FORMAT)


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
RECORDS += [
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
            "case_ref": "FR-2026-014",
            "item": "Seized handset image",
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
            "case_ref": "FR-2026-014",
            "action": "transferred to lab",
            "format": "CASE/UCO style (synthetic)",
        },
    ),  # fmt: skip
]


# Contracts and deliveries (pivot Task 4). Fictitious, illustrative figures; the agencies are
# generic labels mapped to the CLIENT-A..D compartments (no real agency names). Due dates are
# offsets from the demo date so "overdue" stays true on any seed day. A delivery shares its
# contract's client, compartment and owning unit.
_CONTRACTS = "contracts-demo"
_BRIECH = "/eib-group/briech/"
_POCTOVA = "/eib-group/poctova/"
_GIGA = "/eib-group/giga/"
_CLIENT = {c: f"Client Agency {c}" for c in "ABCD"}


def _contract(ref, cid, client, subject, status, classification, unit_path, end_offset, value):
    data = {
        "contract_ref": cid,
        "client": _CLIENT[client],
        "subject": subject,
        "status": status,
        "end_date": _days_from_today(end_offset),
        "value_musd": value,
    }
    compartments = [f"CLIENT-{client}"] + (["FORENSICS"] if unit_path == _GIGA else [])
    return (ref, "Contract", _CONTRACTS, classification, compartments, unit_path, data)


def _delivery(ref, did, cid, client, item, qty, offset, status, classification, unit_path):
    data = {
        "delivery_ref": did,
        "contract_ref": cid,
        "client": _CLIENT[client],
        "item": item,
        "quantity": qty,
        "due_date": _days_from_today(offset),
        "status": status,
    }
    compartments = [f"CLIENT-{client}"] + (["FORENSICS"] if unit_path == _GIGA else [])
    return (ref, "Delivery", _CONTRACTS, classification, compartments, unit_path, data)


RECORDS += [
    _contract(
        "REC-063",
        "CT-101",
        "A",
        "Reconnaissance UAS fleet supply",
        "active",
        "confidential",
        _BRIECH,
        180,
        4.2,
    ),
    _contract(
        "REC-064",
        "CT-102",
        "A",
        "UAS spares and maintenance support",
        "at_risk",
        "confidential",
        _BRIECH,
        90,
        1.1,
    ),
    _contract(
        "REC-065",
        "CT-103",
        "B",
        "Payload integration trials",
        "active",
        "confidential",
        _BRIECH,
        120,
        0.8,
    ),
    _contract(
        "REC-066",
        "CT-201",
        "C",
        "Body armour plate supply",
        "active",
        "confidential",
        _POCTOVA,
        240,
        2.6,
    ),
    _contract(
        "REC-067",
        "CT-202",
        "D",
        "Uniform and kit lots",
        "completed",
        "restricted",
        _POCTOVA,
        -30,
        0.9,
    ),
    _contract(
        "REC-068",
        "CT-203",
        "C",
        "Helmet liner supply",
        "at_risk",
        "confidential",
        _POCTOVA,
        60,
        0.5,
    ),
    _contract(
        "REC-069",
        "CT-301",
        "B",
        "Perimeter surveillance service",
        "active",
        "secret",
        "/eib-group/stratoc/",
        300,
        3.4,
    ),
    _contract(
        "REC-070",
        "CT-302",
        "D",
        "Forensic laboratory analysis retainer",
        "active",
        "secret",
        _GIGA,
        200,
        0.7,
    ),
    _delivery(
        "REC-071",
        "DL-101",
        "CT-101",
        "A",
        "Reconnaissance UAS airframes",
        4,
        -10,
        "pending",
        "confidential",
        _BRIECH,
    ),
    _delivery(
        "REC-072",
        "DL-102",
        "CT-101",
        "A",
        "Ground control stations",
        2,
        -25,
        "delivered",
        "confidential",
        _BRIECH,
    ),
    _delivery(
        "REC-073",
        "DL-103",
        "CT-102",
        "A",
        "Gimbal spares kit",
        6,
        -3,
        "in_transit",
        "confidential",
        _BRIECH,
    ),
    _delivery(
        "REC-074",
        "DL-104",
        "CT-102",
        "A",
        "Battery packs",
        20,
        14,
        "pending",
        "confidential",
        _BRIECH,
    ),
    _delivery(
        "REC-075",
        "DL-105",
        "CT-103",
        "B",
        "Payload units",
        3,
        -7,
        "pending",
        "confidential",
        _BRIECH,
    ),
    _delivery(
        "REC-076",
        "DL-201",
        "CT-201",
        "C",
        "Armour plate set",
        500,
        -15,
        "pending",
        "confidential",
        _POCTOVA,
    ),
    _delivery(
        "REC-077",
        "DL-202",
        "CT-201",
        "C",
        "Armour plate set",
        500,
        20,
        "pending",
        "confidential",
        _POCTOVA,
    ),
    _delivery(
        "REC-078",
        "DL-203",
        "CT-202",
        "D",
        "Uniform lot",
        1200,
        -60,
        "delivered",
        "restricted",
        _POCTOVA,
    ),
    _delivery(
        "REC-079",
        "DL-204",
        "CT-203",
        "C",
        "Helmet liner lot",
        800,
        -2,
        "pending",
        "confidential",
        _POCTOVA,
    ),
    _delivery(
        "REC-080",
        "DL-205",
        "CT-203",
        "C",
        "Helmet liner lot",
        800,
        30,
        "pending",
        "confidential",
        _POCTOVA,
    ),
    _delivery(
        "REC-081",
        "DL-301",
        "CT-301",
        "B",
        "Camera mast kits",
        4,
        -5,
        "in_transit",
        "secret",
        "/eib-group/stratoc/",
    ),
    _delivery(
        "REC-082",
        "DL-401",
        "CT-302",
        "D",
        "Analysis workstation",
        1,
        -1,
        "pending",
        "secret",
        _GIGA,
    ),
]


# Manufacturing and serial traceability (pivot Task 5). Fictitious runs and serials. A serial
# delivered to a client carries that client's compartment; unassigned stock carries none.
_PRODUCTION = "production-demo"


def _run(ref, run, unit_path, product, qty, qc, reason):
    data = {
        "run_ref": run,
        "product": product,
        "quantity": qty,
        "qc_status": qc,
        "hold_reason": reason,
    }
    return (ref, "ProductionRun", _PRODUCTION, "confidential", [], unit_path, data)


def _serial(ref, serial, unit_path, run, product, qc, client, delivery):
    data = {
        "serial": serial,
        "run_ref": run,
        "product": product,
        "qc_status": qc,
        "delivered_to": _CLIENT[client] if client else None,
        "delivery_ref": delivery,
    }
    compartments = [f"CLIENT-{client}"] if client else []
    return (ref, "SerialUnit", _PRODUCTION, "confidential", compartments, unit_path, data)


_AIRFRAME = "Reconnaissance UAS airframe"
RECORDS += [
    _run("REC-083", "PR-BR-014", _BRIECH, _AIRFRAME, 6, "released", None),
    _run(
        "REC-084",
        "PR-BR-015",
        _BRIECH,
        _AIRFRAME,
        4,
        "hold",
        "gimbal bracket torque out of tolerance",
    ),
    _run("REC-085", "PR-PO-031", _POCTOVA, "Armour plate", 500, "released", None),
    _run(
        "REC-086",
        "PR-PO-032",
        _POCTOVA,
        "Helmet liner",
        800,
        "hold",
        "adhesive cure time below spec",
    ),
    _serial("REC-087", "BRC-0041", _BRIECH, "PR-BR-014", _AIRFRAME, "released", "A", "DL-101"),
    _serial("REC-088", "BRC-0042", _BRIECH, "PR-BR-014", _AIRFRAME, "released", "A", "DL-101"),
    _serial("REC-089", "BRC-0043", _BRIECH, "PR-BR-014", _AIRFRAME, "released", None, None),
    _serial("REC-090", "BRC-0051", _BRIECH, "PR-BR-015", _AIRFRAME, "hold", None, None),
    _serial(
        "REC-091", "PCT-ARM-0007", _POCTOVA, "PR-PO-031", "Armour plate", "released", "C", "DL-201"
    ),
    _serial("REC-092", "PCT-HLM-0112", _POCTOVA, "PR-PO-032", "Helmet liner", "hold", None, None),
]


# Group assets (pivot Task 6): seed-only, answered by the existing equipment and stock tools.
# The Briech rows (094-097) are Secret, so only the owner sees them.
RECORDS += [
    _equipment(
        "REC-093",
        "logistics-ref",
        "restricted",
        [],
        _STRATOC,
        12,
        equipment_id="EQ-3301",
        name="Command-and-control vehicle",
        type="vehicle",
        location="EIB Stratoc depot",
        status="in_service",
    ),
    _equipment(
        "REC-094",
        "logistics-ref",
        "secret",
        [],
        _BRIECH,
        -4,
        equipment_id="EQ-4401",
        name="Helipad lighting and fuel interlock",
        type="facility",
        location="Briech UAS airstrip",
        status="in_service",
    ),
    _equipment(
        "REC-095",
        "logistics-ref",
        "secret",
        [],
        _BRIECH,
        6,
        equipment_id="EQ-4402",
        name="UAS airframe BRC-0043 (492 of 500 flight hours to service)",
        type="airframe",
        location="Briech UAS hangar",
        status="in_service",
        flight_hours=492,
        service_interval_hours=500,
    ),
    (
        "REC-096",
        "StockItem",
        "logistics-ref",
        "secret",
        [],
        _BRIECH,
        {"item": "Jet A-1 fuel (litres)", "depot": "DEP-HELI", "quantity": 1800, "threshold": 5000},
    ),
    (
        "REC-097",
        "StockItem",
        "logistics-ref",
        "secret",
        [],
        _BRIECH,
        {"item": "Hydraulic oil (litres)", "depot": "DEP-HELI", "quantity": 200, "threshold": 50},
    ),
]


def _id(kind: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"defence-gateway:{kind}")


def _unit_id(path: str) -> UUID:
    return _id(f"unit:{path}")


def _source_id(name: str) -> UUID:
    return _id(f"source-system:{name}")


def _chunk_texts(doc_ref: str, title: str, unit_path: str) -> list[tuple[str, str, int]]:
    """Two chunks per document. Exactly one chunk of DOC-001/006/013 contains
    the keyword 'maintenance' (the retrieval demo's planted match); no other
    document's text contains it."""
    summary = f"{title} — reference copy held at {unit_path}."
    if doc_ref == "DOC-013":
        body = (
            "Section 2: ordering via maintenance stores requires unit approval."
            f" Reference {doc_ref}."
        )
        return [(summary, "Summary", 1), (body, "Section 2", 2)]
    body = f"Section 1: standard administrative content for demo purposes. Reference {doc_ref}."
    return [(summary, "Summary", 1), (body, "Section 1", 2)]


def _rows(include_archived: bool = False) -> dict[type, list[dict]]:
    unit_rows = [
        {
            "id": _unit_id(u["path"]),
            "name": u["name"],
            "parent_id": _unit_id(u["parent"]) if u["parent"] else None,
            "path": u["path"],
            "depth": u["depth"],
        }
        for u in UNITS
    ]

    hasher = PasswordHasher()
    user_rows = []
    user_compartment_rows = []
    for u in USERS + (ARCHIVED_USERS if include_archived else []):
        user_id = _id(f"user:{u['username']}")
        user_rows.append(
            {
                "id": user_id,
                "username": u["username"],
                "display_name": u["display_name"],
                "role": u["role"],
                "unit_id": _unit_id(u["unit"]),
                "clearance_code": u["clearance"],
                "keycloak_id": None,
                "data_scope": u["data_scope"],
                "is_active": True,
                "password_hash": hasher.hash(DEMO_PASSWORD),
            }
        )
        user_compartment_rows.extend(
            {"user_id": user_id, "compartment_code": code} for code in sorted(u["compartments"])
        )

    source_rows = [
        {
            "id": _source_id(s["name"]),
            "name": s["name"],
            "adapter_type": s["adapter_type"],
            "default_classification": "restricted",
            "status": s["status"],
        }
        for s in SOURCE_SYSTEMS
    ]

    document_rows = []
    chunk_rows = []
    for ref, title, classification, compartments, unit_path in DOCUMENTS:
        doc_id = _id(f"doc:{ref}")
        document_rows.append(
            {
                "id": doc_id,
                "title": title,
                "source_system_id": _source_id("documents-ref"),
                "source_ref": ref,
                "classification_code": classification,
                "compartments": compartments,
                "unit_id": _unit_id(unit_path),
                "content_hash": hashlib.sha256(
                    f"{ref}|{title}|{classification}|{unit_path}".encode()
                ).hexdigest(),
                "status": "published",
                "version": 1,
            }
        )
        for i, (text, section, page) in enumerate(_chunk_texts(ref, title, unit_path), start=1):
            chunk_rows.append(
                {
                    "id": _id(f"chunk:{ref}:{i}"),
                    "document_id": doc_id,
                    "text": text,
                    "embedding": None,
                    "page": page,
                    "section": section,
                    "classification_code": classification,
                    "compartments": compartments,
                    "unit_id": _unit_id(unit_path),
                }
            )

    base_time = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)
    record_rows = [
        {
            "id": _id(f"record:{ref}"),
            "entity_type": entity_type,
            "source_system_id": _source_id(source),
            "source_ref": ref,
            "data": data,
            "classification_code": classification,
            "compartments": compartments,
            "unit_id": _unit_id(unit_path),
            "retrieved_at": base_time + timedelta(minutes=i),
        }
        for i, (
            ref,
            entity_type,
            source,
            classification,
            compartments,
            unit_path,
            data,
        ) in enumerate(RECORDS)
    ]

    return {
        ClassificationLevel: CLASSIFICATION_LEVELS,
        Compartment: COMPARTMENTS,
        Unit: unit_rows,
        User: user_rows,
        UserCompartment: user_compartment_rows,
        SourceSystem: source_rows,
        Document: document_rows,
        Chunk: chunk_rows,
        CanonicalRecord: record_rows,
    }


# Children first, parents last (FK order). Conversation turns are user data
# that reference users, so a reseed clears them too. audit_events is never
# touched.
_DELETE_ORDER = (
    Finding,
    Message,
    Conversation,
    Chunk,
    Document,
    CanonicalRecord,
    UserCompartment,
    User,
    Unit,
    SourceSystem,
    Compartment,
    ClassificationLevel,
)


def run(url: str, include_archived: bool = False) -> None:
    """Replace the demo corpus atomically (idempotent; owner role required)."""
    engine = create_engine(url)
    try:
        rows = _rows(include_archived)
        with engine.begin() as conn:
            for table in _DELETE_ORDER:
                conn.execute(delete(table))
            for table in (
                ClassificationLevel,
                Compartment,
                Unit,
                User,
                UserCompartment,
                SourceSystem,
                Document,
                Chunk,
                CanonicalRecord,
            ):
                conn.execute(table.__table__.insert(), rows[table])
    finally:
        engine.dispose()


def main() -> None:
    run(get_settings().owner_database_url)
    counts = {t.__name__: len(r) for t, r in _rows().items()}
    print(f"seeded demo corpus: {counts}; audit_events untouched ({AuditEvent.__tablename__})")


if __name__ == "__main__":
    main()

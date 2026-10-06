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
from app.config import get_settings
from app.connectors.models import CanonicalRecord, SourceSystem
from app.knowledge.models import Chunk, Document

DEMO_PASSWORD = "Demo!Gateway2026"

CLASSIFICATION_LEVELS = [
    {"code": "unclassified", "name": "Unclassified", "rank": 0},
    {"code": "restricted", "name": "Restricted", "rank": 1},
    {"code": "confidential", "name": "Confidential", "rank": 2},
    {"code": "secret", "name": "Secret", "rank": 3},
]

COMPARTMENTS = [
    {"code": "UAS-OPS", "name": "UAS Operations", "description": "Unmanned air systems"},
    {"code": "FORENSICS", "name": "Forensics", "description": "Digital forensics cases"},
]

UNITS = [
    {"path": "/command-a/", "name": "Command A", "parent": None, "depth": 0},
    {"path": "/command-a/bde-2/", "name": "Brigade 2", "parent": "/command-a/", "depth": 1},
    {
        "path": "/command-a/bde-2/bn-4/",
        "name": "Battalion 4",
        "parent": "/command-a/bde-2/",
        "depth": 2,
    },
    {"path": "/command-a/uas-wing/", "name": "UAS Wing", "parent": "/command-a/", "depth": 1},
    {"path": "/hq-it/", "name": "HQ IT", "parent": None, "depth": 0},
    {"path": "/hq-inspectorate/", "name": "HQ Inspectorate", "parent": None, "depth": 0},
]

# SPEC 7.4 demo users; data_scope none/audit for sysadmin/auditor (SPEC 7.3).
USERS = [
    {
        "username": "a.bello",
        "display_name": "Lt Col A. Bello",
        "role": "commander",
        "unit": "/command-a/",
        "clearance": "secret",
        "compartments": ["UAS-OPS", "FORENSICS"],
        "data_scope": "standard",
    },
    {
        "username": "a.okafor",
        "display_name": "Maj. A. Okafor",
        "role": "logistics",
        "unit": "/command-a/bde-2/",
        "clearance": "confidential",
        "compartments": [],
        "data_scope": "standard",
    },
    {
        "username": "t.adeyemi",
        "display_name": "Capt. T. Adeyemi",
        "role": "training",
        "unit": "/command-a/bde-2/bn-4/",
        "clearance": "restricted",
        "compartments": [],
        "data_scope": "standard",
    },
    {
        "username": "k.musa",
        "display_name": "Lt. K. Musa",
        "role": "uas_ops",
        "unit": "/command-a/uas-wing/",
        "clearance": "confidential",
        "compartments": ["UAS-OPS"],
        "data_scope": "standard",
    },
    {
        "username": "s.eze",
        "display_name": "Mr. S. Eze",
        "role": "sysadmin",
        "unit": "/hq-it/",
        "clearance": None,
        "compartments": [],
        "data_scope": "none",
    },
    {
        "username": "f.danjuma",
        "display_name": "Mrs. F. Danjuma",
        "role": "auditor",
        "unit": "/hq-inspectorate/",
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
]

# (ref, title, classification, compartments, unit path)
DOCUMENTS = [
    ("DOC-001", "Vehicle Maintenance Policy", "restricted", [], "/command-a/bde-2/"),
    ("DOC-002", "Brigade 2 Fuel Consumption Report Q2", "confidential", [], "/command-a/bde-2/"),
    ("DOC-003", "Battalion 4 Training Schedule August", "restricted", [], "/command-a/bde-2/bn-4/"),
    (
        "DOC-004",
        "Operation Northern Star After-Action Review",
        "secret",
        ["UAS-OPS", "FORENSICS"],
        "/command-a/",
    ),
    ("DOC-005", "UAS Contingency Deployment Plan", "secret", ["UAS-OPS"], "/command-a/uas-wing/"),
    ("DOC-006", "UAS Maintenance Schedule", "confidential", ["UAS-OPS"], "/command-a/uas-wing/"),
    ("DOC-007", "Digital Forensics Handling Procedure", "secret", ["FORENSICS"], "/command-a/"),
    ("DOC-008", "Command A Quarterly Equipment Audit", "restricted", [], "/command-a/"),
    ("DOC-009", "Brigade 2 Ammunition Stocktake", "confidential", [], "/command-a/bde-2/"),
    ("DOC-010", "Command A Duty Roster Template", "unclassified", [], "/command-a/"),
    ("DOC-011", "HQ IT Access Review Procedure", "restricted", [], "/hq-it/"),
    ("DOC-012", "Inspectorate Visit Schedule 2026", "restricted", [], "/hq-inspectorate/"),
    ("DOC-013", "Spare Parts Ordering Guide", "unclassified", [], "/command-a/bde-2/"),
    ("DOC-014", "Command A Contingency Order Delta", "secret", [], "/command-a/"),
    (
        "DOC-015",
        "UAS Payload Calibration Notes",
        "confidential",
        ["UAS-OPS", "FORENSICS"],
        "/command-a/uas-wing/",
    ),
    ("DOC-016", "Training Readiness Summary Q3", "confidential", [], "/command-a/bde-2/bn-4/"),
]

# (ref, entity_type, source, classification, compartments, unit path, data)
RECORDS = [
    (
        "REC-001",
        "Equipment",
        "logistics-ref",
        "restricted",
        [],
        "/command-a/bde-2/",
        {
            "equipment_id": "EQ-2201",
            "name": "Generator 15kW",
            "location": "Brigade 2 depot",
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
        "/command-a/bde-2/bn-4/",
        {
            "course": "Rifle Refresher",
            "start_date": "2026-08-11",
            "attendees": 24,
            "unit": "Battalion 4",
        },
    ),
    (
        "REC-003",
        "WorkOrder",
        "logistics-ref",
        "confidential",
        [],
        "/command-a/bde-2/bn-4/",
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
        "/command-a/uas-wing/",
        {"tail": "UAS-14", "mission": "MSN-091", "duration_min": 47, "battery_pct_end": 61},
    ),
    (
        "REC-005",
        "StockItem",
        "logistics-ref",
        "restricted",
        [],
        "/command-a/bde-2/",
        {"item": "Cold weather kit", "depot": "DEP-B2", "quantity": 320, "threshold": 150},
    ),
    (
        "REC-006",
        "Qualification",
        "personnel-ref",
        "restricted",
        [],
        "/command-a/",
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
        "/command-a/",
        {"case_ref": "FR-2026-014", "opened": "2026-06-03", "items": 5, "state": "open"},
    ),
    (
        "REC-008",
        "WorkOrder",
        "logistics-ref",
        "restricted",
        [],
        "/hq-it/",
        {
            "wo_ref": "WO-0461",
            "equipment": "Badge printer HQ-IT",
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
        "/command-a/uas-wing/",
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
        "/command-a/bde-2/",
        {"item": "Generator oil 5L", "depot": "DEP-B2", "quantity": 45, "threshold": 60},
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


def _rows() -> dict[type, list[dict]]:
    unit_rows = []
    for u in UNITS:
        unit_rows.append(
            {
                "id": _unit_id(u["path"]),
                "name": u["name"],
                "parent_id": _unit_id(u["parent"]) if u["parent"] else None,
                "path": u["path"],
                "depth": u["depth"],
            }
        )

    hasher = PasswordHasher()
    user_rows = []
    user_compartment_rows = []
    for u in USERS:
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
        for code in sorted(u["compartments"]):
            user_compartment_rows.append({"user_id": user_id, "compartment_code": code})

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


# Children first, parents last (FK order). audit_events is never touched.
_DELETE_ORDER = (
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


def run(url: str) -> None:
    """Replace the demo corpus atomically (idempotent; owner role required)."""
    engine = create_engine(url)
    try:
        rows = _rows()
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

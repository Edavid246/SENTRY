"""Identity and reference data for the demo seed: levels, compartments, units, users, documents."""

from __future__ import annotations

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

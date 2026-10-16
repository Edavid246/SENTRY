"""Group assets answered by the equipment and stock tools."""

from __future__ import annotations

from app.seed.records.common import BRIECH, STRATOC, equipment_record

# Group assets (pivot Task 6): seed-only, answered by the existing equipment and stock tools.
# The Briech rows (094-097) are Secret, so only the owner sees them.
RECORDS = [
    equipment_record(
        "REC-093",
        "logistics-ref",
        "restricted",
        [],
        STRATOC,
        12,
        equipment_id="EQ-3301",
        name="Command-and-control vehicle",
        type="vehicle",
        location="EIB Stratoc depot",
        status="in_service",
    ),
    equipment_record(
        "REC-094",
        "logistics-ref",
        "secret",
        [],
        BRIECH,
        -4,
        equipment_id="EQ-4401",
        name="Helipad lighting and fuel interlock",
        type="facility",
        location="Briech UAS airstrip",
        status="in_service",
    ),
    equipment_record(
        "REC-095",
        "logistics-ref",
        "secret",
        [],
        BRIECH,
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
        BRIECH,
        {"item": "Jet A-1 fuel (litres)", "depot": "DEP-HELI", "quantity": 1800, "threshold": 5000},
    ),
    (
        "REC-097",
        "StockItem",
        "logistics-ref",
        "secret",
        [],
        BRIECH,
        {"item": "Hydraulic oil (litres)", "depot": "DEP-HELI", "quantity": 200, "threshold": 50},
    ),
]

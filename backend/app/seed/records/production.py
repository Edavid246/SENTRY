"""Manufacturing runs and serial traceability."""

from __future__ import annotations

from app.seed.records.common import _BRIECH, _CLIENT, _POCTOVA

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
RECORDS = [
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

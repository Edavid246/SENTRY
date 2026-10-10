"""What each division's dashboard shows: one `SectionSpec` per section (SPEC 8.2 typed tools).

Presentation only. A spec names the typed tool that produces the rows and how a row reads
(label, detail, whether it needs attention); the audit, authorization and labelling all happen
in `app.api.divisions`, which runs the specs. To add a division's dashboard, add its entry to
SECTIONS. Nothing else changes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.clock import demo_today

Row = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SectionSpec:
    key: str
    title: str
    tool: str
    empty_text: str
    label: Callable[[Row], str]
    detail: Callable[[Row], str]
    flagged: Callable[[Row], bool] = lambda row: True
    params: Mapping[str, Any] = field(default_factory=dict)
    meter: Callable[[Row], float | None] = lambda row: None
    href: Callable[[str], str] = lambda ref: f"/records/{ref}"
    row_href: Callable[[Row], str] | None = None  # when the link needs more than the ref
    scoped: bool = True  # False for tools that take no unit_path (the findings store)


def _run_detail(row: Row) -> str:
    text = f"{row['product']} · qty {row['quantity']} · QC {row['qc_status']}"
    text += f" · {row['serials_traced']} serials traced"
    return f"{text} · {row['hold_reason']}" if row.get("hold_reason") else text


COMPLIANCE = (
    SectionSpec(
        "maintenance",
        "Maintenance due within 30 days",
        "equipment_due_for_maintenance",
        "No equipment is due for maintenance.",
        lambda r: str(r["name"]),
        lambda r: f"{r['type']} · due {r['maintenance_due_date']} · {r['status']}",
        lambda r: str(r["maintenance_due_date"]) < demo_today().isoformat(),
        {"within_days": 30},
    ),
    SectionSpec(
        "certifications",
        "Expired certifications",
        "expired_certifications",
        "No certification has expired.",
        lambda r: str(r["name"]),
        lambda r: f"{r['certification']} · expired {r['expired_date']}",
    ),
)


_STOCK = SectionSpec(
    "stock",
    "Stock below threshold",
    "stock_below_threshold",
    "No stock line is short.",
    lambda r: str(r["item"]),
    lambda r: (
        f"{r['depot']} · {r['quantity']} on hand, threshold {r['threshold']} "
        f"(short by {r['shortfall']})"
    ),
)

_DELIVERIES = SectionSpec(
    "deliveries",
    "Overdue deliveries",
    "deliveries_overdue",
    "No delivery is overdue.",
    lambda r: f"{r['delivery_ref']} · {r['item']}",
    lambda r: (
        f"{r['client']} · qty {r['quantity']} · due {r['due_date']} "
        f"({r['days_overdue']} days overdue) · {r['status']}"
    ),
)


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _fleet_detail(row: Row) -> str:
    left = row["hours_to_service"]
    text = f"{row['flight_hours']:g} flight hours"
    if row.get("status"):
        text += f" · {str(row['status']).replace('_', ' ')}"
    if left is not None:
        return f"{text} · {left:g} h to service"
    return f"{text} · next service {row['next_service']}" if row.get("next_service") else text


def _fleet_meter(row: Row) -> float | None:
    interval = row["service_interval_hours"]
    return None if not interval else min(1.0, row["flight_hours"] / interval)


SECTIONS: dict[str, tuple[SectionSpec, ...]] = {
    "giga": (
        SectionSpec(
            "custody-breaks",
            "Custody breaks",
            "custody_gaps",
            "Every chain of custody is unbroken.",
            lambda r: f"{r['evidence_ref']} · {r['action']} on {r['event_date']}",
            lambda r: (
                f"Recorded as taken from {r['recorded_holder']}, "
                f"but the last holder was {r['expected_holder']}"
            ),
            row_href=lambda r: f"/cases/{r['case_ref']}",
        ),
        SectionSpec(
            "cases",
            "Cases",
            "forensic_cases",
            "No cases are visible to you.",
            lambda r: f"{r['case_ref']} · {r['title']}",
            lambda r: (
                f"{r['state']} · opened {r['opened']} · "
                f"{_count(r['evidence_items'], 'evidence item')}"
                + (
                    f" · {_count(r['custody_breaks'], 'custody break')}"
                    if r["custody_breaks"]
                    else ""
                )
            ),
            lambda r: r["custody_breaks"] > 0,
            row_href=lambda r: f"/cases/{r['case_ref']}",
        ),
        SectionSpec(
            "evidence",
            "Evidence items",
            "evidence_items",
            "No evidence items are visible to you.",
            lambda r: f"{r['evidence_ref']} · {r['item']}",
            lambda r: (
                f"{r['case_ref']} · {r['kind']} · {r['status']} · "
                f"{_count(r['custody_events'], 'custody event')}"
            ),
            lambda r: r["custody_breaks"] > 0,
        ),
        *COMPLIANCE,
    ),
    "field-ops": (
        SectionSpec(
            "personnel",
            "Personnel and certifications",
            "field_personnel",
            "No personnel are visible to you.",
            lambda r: str(r["name"]),
            lambda r: (
                f"{r['rank']} · {r['certification']} · "
                + ("expired " if r["status"] == "expired" else "valid until ")
                + str(r["expires"])
            ),
            lambda r: r["status"] == "expired",
        ),
        SectionSpec(
            "training",
            "Training, last 90 days",
            "training_activity",
            "No training in the last 90 days.",
            lambda r: str(r["course"]),
            lambda r: f"{r['start_date']} · {r['attendees']} attendees",
            lambda r: False,
        ),
        _STOCK,
        COMPLIANCE[0],
    ),
    "stratoc": (
        SectionSpec(
            "findings",
            "Correlation findings",
            "correlation_findings",
            "No findings yet. Run the correlation to look for patterns.",
            lambda r: str(r["title"]),
            lambda r: f"{r['severity']} severity · {r['summary']}",
            href=lambda ref: f"/findings/{ref}",
            scoped=False,
        ),
        SectionSpec(
            "detections",
            "Detections, last 48 hours",
            "detections_near_site",
            "No detections in the last 48 hours.",
            lambda r: f"{str(r['object_type']).capitalize()} at {r['site']}",
            lambda r: (
                f"{r['observed_at']} · {r['sensor_id']} · confidence {float(r['confidence']):.0%}"
            ),
            lambda r: False,
        ),
        SectionSpec(
            "sensors",
            "Sensors and sites",
            "sensors_status",
            "No sensors are visible to you.",
            lambda r: f"{r['sensor_id']} · {r['site']}",
            lambda r: f"{r['kind']} · {r['status']}",
            lambda r: r["status"] != "online",
        ),
        *COMPLIANCE,
    ),
    "briech": (
        SectionSpec(
            "fleet",
            "Aircraft and hours to service",
            "uas_fleet",
            "No aircraft are visible to you.",
            lambda r: str(r["name"]),
            _fleet_detail,
            lambda r: (
                r["status"] not in (None, "in_service")
                or (r["hours_to_service"] is not None and r["hours_to_service"] <= 25)
            ),
            meter=_fleet_meter,
        ),
        SectionSpec(
            "missions",
            "Missions, last 30 days",
            "uas_missions",
            "No missions in the last 30 days.",
            lambda r: f"{r['mission']} · {r['platform']}",
            lambda r: (
                f"{r['mission_date']} · {r['area']} · {r['status']}"
                + (f" · {r['reason']}" if r.get("reason") else "")
            ),
            lambda r: r["status"] == "cancelled",
        ),
        _DELIVERIES,
        SectionSpec(
            "contracts",
            "Contracts",
            "contracts_status",
            "No contracts are visible to you.",
            lambda r: f"{r['contract_ref']} · {r['subject']}",
            lambda r: f"{r['client']} · {r['status'].replace('_', ' ')} · ends {r['end_date']}",
            lambda r: r["status"] == "at_risk",
        ),
        *COMPLIANCE,
    ),
    "poctova": (
        SectionSpec(
            "qc-holds",
            "Production runs on QC hold",
            "production_qc_holds",
            "No production run is on hold.",
            lambda r: f"{r['run_ref']} · {r['product']}",
            lambda r: (
                f"qty {r['quantity']} · {r['serials_traced']} serials traced · {r['hold_reason']}"
            ),
        ),
        SectionSpec(
            "runs",
            "All production runs",
            "production_runs",
            "No production runs are visible to you.",
            lambda r: f"{r['run_ref']} · {r['product']}",
            _run_detail,
            lambda r: r["qc_status"] == "hold",
        ),
        _STOCK,
        _DELIVERIES,
        *COMPLIANCE,
    ),
}


def trace_spec(serial: str) -> SectionSpec:
    """One serial number's run, QC state and delivery (the trace endpoint's single section)."""
    return SectionSpec(
        "trace",
        f"Serial {serial}",
        "serial_trace",
        "No such serial number.",
        lambda r: f"{r['serial']} · {r['product']}",
        lambda r: (
            f"run {r['run_ref']} · QC {r['qc_status']} · "
            f"{('delivered to ' + r['delivered_to']) if r['delivered_to'] else 'in stock'}"
        ),
        lambda r: r["qc_status"] == "hold",
        {"serial": serial},
    )

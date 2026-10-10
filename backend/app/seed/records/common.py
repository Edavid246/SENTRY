"""Helpers shared by the record modules: dates are offsets from the demo clock."""

from __future__ import annotations

from datetime import timedelta

from app.clock import UTC_TS_FORMAT, demo_now, demo_today


def _days_from_today(offset: int) -> str:
    # DEMO_DATE (app.clock) pins this so a re-seed reproduces the same dates on any day.
    return (demo_today() + timedelta(days=offset)).isoformat()


def _hours_from_now(offset: int) -> str:
    return (demo_now() + timedelta(hours=offset)).strftime(UTC_TS_FORMAT)


# Owning units shared across the record modules.
_STRATOC = "/eib-group/stratoc/"
_SITE4 = "/eib-group/stratoc/site-4/"
_BRIECH = "/eib-group/briech/"
_POCTOVA = "/eib-group/poctova/"
_GIGA = "/eib-group/giga/"
_CLIENT = {c: f"Client Agency {c}" for c in "ABCD"}


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

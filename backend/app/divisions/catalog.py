"""The five divisions: the four businesses, and Field Operations (people and sites in the field)."""

from __future__ import annotations

from dataclasses import dataclass

from app.units import is_site, subsidiary_key


class DivisionNotFound(Exception):
    """No such division, or the caller cannot see it; the routes answer both with 404."""


@dataclass(frozen=True, slots=True)
class Division:
    key: str
    name: str
    tagline: str
    path: str | None  # the subsidiary's unit path; None for Field Operations


DIVISIONS = (
    Division("briech", "Briech UAS", "Drones and airborne surveillance", "/eib-group/briech/"),
    Division("stratoc", "EIB Stratoc", "Surveillance and intelligence", "/eib-group/stratoc/"),
    Division("giga", "Giga Forensics", "Digital forensics and evidence", "/eib-group/giga/"),
    Division("poctova", "Poctova", "Protective gear, made and traced", "/eib-group/poctova/"),
    Division("field-ops", "Field Operations", "Personnel and sites in the field", None),
)
FIELD_OPS = "field-ops"


def division_key(unit_path: str, *, finding: bool = False) -> str | None:
    """Which division a record counts toward. A site team (a unit below a subsidiary) belongs to
    Field Operations; a finding about a site stays with the subsidiary that raised it."""
    if is_site(unit_path) and not finding:
        return FIELD_OPS
    return subsidiary_key(unit_path)  # None for a group-level record: no division

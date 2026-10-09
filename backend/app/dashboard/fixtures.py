"""Placeholder dashboard data (Part C). Every figure here is fictitious.

Each item carries a classification, compartments and an owning unit, so the
summary service can run it through the same SPEC 7.1 rule as database rows
(`LocalPolicy.item_visible`). The fixtures are NOT an authorization shortcut:
they are filtered per caller before anything is returned.

Maintenance and certification tiles are typed-tool results and recent findings
come from the correlation store (`app.api.dashboard`); only readiness remains a
fixture. A tile's `stub` flag is false only when its data is real; the response
shape never changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FixtureItem:
    id: str
    label: str
    classification: str
    unit_path: str
    detail: str = ""
    value: float | None = None
    unit: str | None = None
    severity: str | None = None
    trend: tuple[float, ...] = ()
    compartments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class FixtureTile:
    title: str
    source: str
    items: tuple[FixtureItem, ...]


_CMD = "/eib-group/"
_STRATOC = "/eib-group/stratoc/"
_SITE4 = "/eib-group/stratoc/site-4/"
_UAS = "/eib-group/briech/"
_SOURCE = "placeholder fixtures (demo data, not yet connected)"

READINESS = FixtureTile(
    title="Readiness",
    source=_SOURCE,
    items=(
        FixtureItem(
            "RDY-CMD",
            "EIB Group overall",
            "restricted",
            _CMD,
            value=82,
            unit="%",
            trend=(78, 79, 80, 81, 81, 82),
        ),
        FixtureItem(
            "RDY-STRATOC",
            "EIB Stratoc",
            "restricted",
            _STRATOC,
            value=79,
            unit="%",
            trend=(80, 80, 79, 79, 78, 79),
        ),
        FixtureItem(
            "RDY-SITE4",
            "Stratoc Site Team 4",
            "restricted",
            _SITE4,
            value=68,
            unit="%",
            severity="medium",
            trend=(77, 75, 73, 71, 70, 68),
        ),
        FixtureItem(
            "RDY-UAS",
            "Briech UAS",
            "confidential",
            _UAS,
            value=88,
            unit="%",
            compartments=("UAS-OPS",),
            trend=(86, 87, 87, 88, 88, 88),
        ),
    ),
)

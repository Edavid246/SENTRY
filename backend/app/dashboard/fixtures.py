"""Placeholder dashboard data (Part C). Every figure here is fictitious.

Each item carries a classification, compartments and an owning unit, so the
summary service can run it through the same SPEC 7.1 rule as database rows
(`LocalPolicy.item_visible`). The fixtures are NOT an authorization shortcut:
they are filtered per caller before anything is returned.

Part D1/D2 replace tiles with real tool results one by one; each tile's
`stub` flag flips to false only when its data is real, and the response shape
stays identical (`app.api.dashboard` documents it in the OpenAPI schema).
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
    key: str
    title: str
    source: str
    items: tuple[FixtureItem, ...]


_CMD = "/command-a/"
_BDE2 = "/command-a/bde-2/"
_BN4 = "/command-a/bde-2/bn-4/"
_UAS = "/command-a/uas-wing/"
_SOURCE = "placeholder fixtures (demo data, not yet connected)"

TILES: tuple[FixtureTile, ...] = (
    FixtureTile(
        key="readiness",
        title="Readiness",
        source=_SOURCE,
        items=(
            FixtureItem(
                "RDY-CMD",
                "Command A overall",
                "restricted",
                _CMD,
                value=82,
                unit="%",
                trend=(78, 79, 80, 81, 81, 82),
            ),
            FixtureItem(
                "RDY-BDE2",
                "Brigade 2",
                "restricted",
                _BDE2,
                value=79,
                unit="%",
                trend=(80, 80, 79, 79, 78, 79),
            ),
            FixtureItem(
                "RDY-BN4",
                "Battalion 4",
                "restricted",
                _BN4,
                value=68,
                unit="%",
                severity="medium",
                trend=(77, 75, 73, 71, 70, 68),
            ),
            FixtureItem(
                "RDY-UAS",
                "UAS Wing",
                "confidential",
                _UAS,
                value=88,
                unit="%",
                compartments=("UAS-OPS",),
                trend=(86, 87, 87, 88, 88, 88),
            ),
        ),
    ),
    FixtureTile(
        key="maintenance_backlog",
        title="Maintenance backlog",
        source=_SOURCE,
        items=(
            FixtureItem(
                "MNT-BN4",
                "Battalion 4: equipment overdue",
                "restricted",
                _BN4,
                value=4,
                unit="items",
                severity="medium",
                trend=(1, 1, 2, 2, 3, 4),
            ),
            FixtureItem(
                "MNT-BDE2",
                "Brigade 2: equipment overdue",
                "restricted",
                _BDE2,
                value=7,
                unit="items",
                trend=(5, 5, 6, 6, 7, 7),
            ),
            FixtureItem(
                "MNT-UAS",
                "UAS Wing: airframes overdue",
                "confidential",
                _UAS,
                value=2,
                unit="items",
                compartments=("UAS-OPS",),
                trend=(1, 1, 1, 2, 2, 2),
            ),
        ),
    ),
    FixtureTile(
        key="expiring_certifications",
        title="Certifications expiring (30 days)",
        source=_SOURCE,
        items=(
            FixtureItem(
                "CRT-BN4",
                "Battalion 4",
                "restricted",
                _BN4,
                value=3,
                unit="people",
                trend=(1, 1, 2, 2, 3, 3),
            ),
            FixtureItem(
                "CRT-BDE2",
                "Brigade 2",
                "restricted",
                _BDE2,
                value=5,
                unit="people",
                trend=(3, 4, 4, 4, 5, 5),
            ),
            FixtureItem(
                "CRT-CMD",
                "Command A",
                "restricted",
                _CMD,
                value=9,
                unit="people",
                trend=(6, 7, 7, 8, 8, 9),
            ),
        ),
    ),
    FixtureTile(
        key="recent_findings",
        title="Recent findings",
        source=_SOURCE,
        items=(
            FixtureItem(
                "FND-ATT",
                "Rifle Refresher attendance below plan",
                "restricted",
                _BN4,
                detail="Attendance 71% against a plan of 90% over the last three sessions.",
                severity="low",
            ),
            FixtureItem(
                "FND-AMM",
                "Ammunition stocktake variance",
                "confidential",
                _BDE2,
                detail="Stocktake differs from the ledger by 3% for one calibre.",
                severity="medium",
            ),
            # Stand-in for the planted correlation finding (Part D2 replaces it with
            # a computed one). It is Secret, so Restricted callers never receive it.
            FixtureItem(
                "FND-CORR",
                "Rising faults in Battalion 4 linked to lapsed certifications and a parts shortage",
                "secret",
                _BN4,
                detail="Fault reports up 40% in six weeks; maintainer certifications lapsed and"
                " the water purifier filter stock is below threshold.",
                severity="high",
            ),
        ),
    ),
)

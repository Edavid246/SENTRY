"""What needs attention, per division: the counts behind the home cards.

The numbers come from audited typed tools (filtered inside the query for this caller) and the
findings store. A division is shown when the caller's unit covers it or anything in it is
visible; a hidden division is absent, never present-but-locked. A count is a derived item, so it
takes the highest classification and the union of compartments of what it counts.

Certifications are deliberately not counted: they are background compliance, shown on the
compliance views, not a reason to interrupt the owner on the landing screen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.authz.labels import Label
from app.authz.scope import Scope
from app.correlation.store import list_findings
from app.data_queries.registry import execute_tool
from app.divisions.catalog import DIVISIONS, Division, division_key
from app.units import covers, is_site, unit_names

# (tool, params, what it counts). Certifications are left out on purpose, see the module doc.
ATTENTION_TOOLS: tuple[tuple[str, Mapping[str, Any], str], ...] = (
    ("equipment_due_for_maintenance", {"within_days": 0}, "equipment overdue"),
    ("deliveries_overdue", {}, "deliveries overdue"),
    ("production_qc_holds", {}, "production runs on QC hold"),
    ("stock_below_threshold", {}, "stock lines short"),
    ("uas_missions", {"status": "cancelled"}, "UAS missions cancelled"),
    ("custody_gaps", {}, "custody breaks"),
)
FINDINGS_WHAT = "findings open"


@dataclass(frozen=True, slots=True)
class Attention:
    """One division the caller can see, and what in it needs attention."""

    division: Division
    parts: tuple[tuple[str, int], ...]  # (what is counted, how many), in counting order
    refs: tuple[str, ...]  # every record and finding counted
    label: Label | None  # derived from everything counted; None when nothing needs attention


def division_attention(scope: Scope) -> list[Attention]:
    """Every division the caller can see, in catalogue order, with its counts."""
    names = unit_names(scope.conn)
    counted: dict[str, dict[str, list[tuple[str, Label]]]] = {}  # key -> what -> (ref, label)

    def add(key: str | None, what: str, ref: str, label: Label) -> None:
        if key is not None:
            counted.setdefault(key, {}).setdefault(what, []).append((ref, label))

    for tool, params, what in ATTENTION_TOOLS:
        for record in execute_tool(scope, tool, params).records:
            add(
                division_key(record.unit_path),
                what,
                record.source_ref,
                Label(record.classification_code, tuple(record.compartments)),
            )
    for row in list_findings(scope):
        add(
            division_key(row.unit_path, finding=True),
            FINDINGS_WHAT,
            row.key,
            Label(row.classification_code, tuple(row.compartments)),
        )

    site_units = [p for p in names if is_site(p)]
    shown: list[Attention] = []
    for division in DIVISIONS:
        by_what = counted.get(division.key, {})
        if division.path is not None:
            covered = covers(scope.ctx.unit_path, division.path)
        else:
            covered = any(covers(scope.ctx.unit_path, p) for p in site_units)
        if not covered and not by_what:
            continue
        members = [m for found in by_what.values() for m in found]
        shown.append(
            Attention(
                division=division,
                parts=tuple((what, len(found)) for what, found in by_what.items()),
                refs=tuple(ref for ref, _ in members),
                label=scope.labels.derive(m for _, m in members) if members else None,
            )
        )
    return shown

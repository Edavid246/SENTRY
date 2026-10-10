"""Correlation: the same hand-over appears in custody breaks in more than one case.

Rule, on what the caller may see: a custody break is a transfer whose recorded holder is not
whoever last received the item (the `custody_gaps` tool). When the same recorded holder is the
unrecorded source in breaks in at least MIN_CASES different cases, one case's slip is no longer
the likeliest explanation: the pattern points at that hand-over, not at the paperwork of a
single case. Evidence is the broken events and the evidence items they belong to, all from the
audited typed tools, so the finding inherits the highest classification and the union of
compartments of exactly what the runner could see.

The summary is deterministic text built from the numbers; no model writes it.
"""

from __future__ import annotations

import re

from app.authz.labels import Labels
from app.authz.scope import Scope
from app.clock import demo_today
from app.connectors.base import SourceRecord
from app.correlation.types import FindingDraft
from app.data_queries.registry import execute_tool

ANALYSIS = "repeated_custody_gaps"
MIN_CASES = 2


def _slug(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", text.upper()).strip("-")


def run_repeated_custody_gaps(
    scope: Scope, labels: Labels, names: dict[str, str]
) -> list[FindingDraft]:
    root = scope.ctx.unit_path
    by_holder: dict[tuple[str, str], list[SourceRecord]] = {}
    for event in execute_tool(scope, "custody_gaps", {"unit_path": root}).records:
        by_holder.setdefault((event.unit_path, str(event.data["from_holder"])), []).append(event)

    drafts: list[FindingDraft] = []
    for (unit_path, holder), events in sorted(by_holder.items()):
        cases = sorted({str(e.data["case_ref"]) for e in events})
        if len(cases) < MIN_CASES:
            continue
        items = {str(e.data["evidence_ref"]) for e in events}
        item_records = [
            r
            for r in execute_tool(scope, "evidence_items", {"unit_path": unit_path}).records
            if r.data["evidence_ref"] in items
        ]
        evidence = [*events, *item_records]
        label = labels.derive(evidence)
        unit_name = names.get(unit_path, unit_path)
        drafts.append(
            FindingDraft(
                key=f"FND-REPEATED-CUSTODY-GAPS-{_slug(holder)}",
                analysis=ANALYSIS,
                title=f"Repeated custody gaps at {unit_name} involving {holder}",
                summary=(
                    f"{holder} is recorded as handing over evidence in {len(events)} custody "
                    f"breaks across {len(cases)} cases ({', '.join(cases)}). In each, the item "
                    "was last received by someone else, so the hand-over is undocumented. "
                    "Review these transfers together rather than case by case."
                ),
                severity="high",
                classification_code=label.code,
                compartments=list(label.compartments),
                unit_path=unit_path,
                evidence_ids=sorted(r.source_ref for r in evidence),
                details={
                    "rule": (
                        "custody breaks with the same recorded holder in at least "
                        f"{MIN_CASES} different cases"
                    ),
                    "as_of": demo_today().isoformat(),
                    "recorded_holder": holder,
                    "cases": cases,
                    "broken_events": sorted(e.source_ref for e in events),
                    "evidence_items": sorted(items),
                    "tools": ["custody_gaps", "evidence_items"],
                },
            )
        )
    return drafts

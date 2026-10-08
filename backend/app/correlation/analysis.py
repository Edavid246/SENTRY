"""The planted correlation (SPEC 10.6, demo step 18.6): rising faults.

Rule, per unit the caller can see: fault reports in the last WINDOW_DAYS are at
least double the previous WINDOW_DAYS and at least three more, AND the same unit
has lapsed maintainer certifications AND stock lines below threshold. The
certification and stock evidence comes from the audited typed tools; faults come
from the adapter. Everything is computed on rows the caller is cleared for, so a
finding can only be built from inputs its runner could see (derived items
inherit the highest classification and union of compartments of those inputs).

The summary is deterministic text built from the numbers; no model writes it.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.engine import Connection

from app.authz.context import AccessContext
from app.authz.labels import Labels
from app.clock import demo_today
from app.connectors.base import RecordFilter, SourceRecord
from app.connectors.demo import DemoReferenceAdapter
from app.correlation.types import FindingDraft
from app.data_queries.registry import execute_tool

ANALYSIS = "rising_faults"
WINDOW_DAYS = 21
MIN_INCREASE = 3
MAINTAINER = "maintainer"
ADAPTER = DemoReferenceAdapter()


def _reported(record: SourceRecord) -> date | None:
    raw = record.data.get("reported_on")
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _tool_records(ctx, conn, tool: str, unit_path: str) -> tuple[SourceRecord, ...]:
    outcome = execute_tool(ctx, conn, tool, {"unit_path": unit_path})
    return outcome.result.records if outcome.result else ()


def run_rising_faults(
    ctx: AccessContext, conn: Connection, labels: Labels, names: dict[str, str]
) -> list[FindingDraft]:
    today = demo_today()
    recent_start = today - timedelta(days=WINDOW_DAYS)
    prior_start = today - timedelta(days=2 * WINDOW_DAYS)

    by_unit: dict[str, list[SourceRecord]] = {}
    for record in ADAPTER.search(conn, ctx, RecordFilter(entity_type="FaultReport")):
        by_unit.setdefault(record.unit_path, []).append(record)

    drafts: list[FindingDraft] = []
    for unit_path in sorted(by_unit):
        recent = [
            r for r in by_unit[unit_path] if (d := _reported(r)) and recent_start < d <= today
        ]
        prior = [
            r for r in by_unit[unit_path] if (d := _reported(r)) and prior_start < d <= recent_start
        ]
        if len(recent) < 2 * len(prior) or len(recent) - len(prior) < MIN_INCREASE:
            continue
        certs = [
            r
            for r in _tool_records(ctx, conn, "expired_certifications", unit_path)
            if MAINTAINER in str(r.data.get("certification", "")).lower()
        ]
        stock = list(_tool_records(ctx, conn, "stock_below_threshold", unit_path))
        if not certs or not stock:
            continue  # a fault rise alone is not the correlation this job looks for

        evidence = [*recent, *certs, *stock]
        label = labels.derive(evidence)
        unit_name = names.get(unit_path, unit_path)
        slug = unit_path.strip("/").split("/")[-1].upper()
        drafts.append(
            FindingDraft(
                key=f"FND-RISING-FAULTS-{slug}",
                analysis=ANALYSIS,
                title=f"Rising faults in {unit_name} linked to lapsed maintainer "
                "certifications and a spare-part shortage",
                summary=(
                    f"Fault reports in {unit_name} rose from {len(prior)} to {len(recent)} over "
                    f"the last {WINDOW_DAYS} days against the {WINDOW_DAYS} before. "
                    f"{len(certs)} maintainer certification(s) have lapsed and "
                    f"{len(stock)} stock line(s) are below threshold in the same unit."
                ),
                severity="high",
                classification_code=label.code,
                compartments=list(label.compartments),
                unit_path=unit_path,
                evidence_ids=sorted(r.source_ref for r in evidence),
                details={
                    "rule": (
                        f"faults in last {WINDOW_DAYS} days >= 2 x previous {WINDOW_DAYS} days "
                        f"and >= {MIN_INCREASE} more; lapsed '{MAINTAINER}' certifications and "
                        "stock below threshold in the same unit"
                    ),
                    "as_of": today.isoformat(),
                    "window_days": WINDOW_DAYS,
                    "prior_faults": len(prior),
                    "recent_faults": len(recent),
                    "lapsed_maintainer_certifications": sorted(r.source_ref for r in certs),
                    "stock_below_threshold": sorted(r.source_ref for r in stock),
                    "tools": ["expired_certifications", "stock_below_threshold"],
                },
            )
        )
    return drafts

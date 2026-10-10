"""Forensic tools: cases, evidence items and chains of custody."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.authz.scope import Scope
from app.connectors.base import SourceRecord
from app.data_queries.errors import ToolParamError
from app.data_queries.tools.base import Table, column, columns, given, matching, search, tool

_CASE_RE = re.compile(r"^FR-\d{4}-\d{3}$")
_EVIDENCE_RE = re.compile(r"^EV-\d{3}-\d{2}$")
_CASE_MESSAGE = "case_ref must look like FR-2026-014"

# One custody event, with the holder it should have been taken from when the record says otherwise.
Chain = list[tuple[SourceRecord, str | None]]


def _custody_chains(events: list[SourceRecord]) -> dict[str, Chain]:
    """Each evidence item's visible custody events in date order, each with the holder it should
    have been taken from (the previous event's `to_holder`) when the record says otherwise.

    A break is a transfer whose `from_holder` is not whoever last received the item. Worked out
    from the events the caller can see: a trail with a hidden event in the middle would read as
    broken, so the forensic records of one case share one label (checked by a test).
    """
    by_item: dict[str, list[SourceRecord]] = {}
    for event in events:
        by_item.setdefault(str(event.data["evidence_ref"]), []).append(event)
    chains: dict[str, Chain] = {}
    for evidence_ref, items in by_item.items():
        items.sort(key=lambda e: (e.data["event_date"], e.source_ref))
        chain: Chain = []
        previous: SourceRecord | None = None
        for event in items:
            expected = None
            if previous is not None and event.data["from_holder"] != previous.data["to_holder"]:
                expected = str(previous.data["to_holder"])
            chain.append((event, expected))
            previous = event
        chains[evidence_ref] = chain
    return chains


def _forensics(scope: Scope, unit_path: str) -> tuple[list[SourceRecord], dict[str, Chain]]:
    evidence = search(scope, "EvidenceItem", unit_path)
    return evidence, _custody_chains(search(scope, "CustodyEvent", unit_path))


@tool("case_ref")
def forensic_cases(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Forensic cases, with how many evidence items and custody breaks the caller can see."""
    case_ref = matching(params.get("case_ref"), _CASE_RE, _CASE_MESSAGE)
    cases = [
        c
        for c in search(scope, "Case", unit_path)
        if case_ref is None or c.data["case_ref"] == case_ref
    ]
    evidence, chains = _forensics(scope, unit_path)
    cases.sort(key=lambda r: (r.data["state"] != "open", r.data["case_ref"]))
    items = {c.data["case_ref"]: 0 for c in cases}
    breaks = dict(items)
    for item in evidence:
        if item.data["case_ref"] in items:
            items[item.data["case_ref"]] += 1
    for chain in chains.values():
        for event, expected in chain:
            if expected is not None and event.data["case_ref"] in breaks:
                breaks[event.data["case_ref"]] += 1
    return Table(
        cases,
        {
            **columns("case_ref", "title", "state", "opened", "lead_examiner"),
            "evidence_items": lambda r: items[r.data["case_ref"]],
            "custody_breaks": lambda r: breaks[r.data["case_ref"]],
        },
        given(case_ref=case_ref),
    )


@tool("case_ref")
def evidence_items(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Evidence items, with how many custody events and breaks each has."""
    case_ref = matching(params.get("case_ref"), _CASE_RE, _CASE_MESSAGE)
    evidence, chains = _forensics(scope, unit_path)
    records = [e for e in evidence if case_ref is None or e.data["case_ref"] == case_ref]
    records.sort(key=lambda r: r.data["evidence_ref"])

    def chain(record: SourceRecord) -> Chain:
        return chains.get(record.data["evidence_ref"], [])

    return Table(
        records,
        {
            **columns("evidence_ref", "case_ref", "item", "kind", "status"),
            "sha256": lambda r: str(r.data["sha256"])[:16],
            "custody_events": lambda r: len(chain(r)),
            "custody_breaks": lambda r: sum(1 for _e, expected in chain(r) if expected),
        },
        given(case_ref=case_ref),
    )


@tool()
def custody_gaps(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """Custody events whose recorded holder is not whoever last received the item."""
    _evidence, chains = _forensics(scope, unit_path)
    broken = [
        (event, expected)
        for chain in chains.values()
        for event, expected in chain
        if expected is not None
    ]
    broken.sort(key=lambda pair: (pair[0].data["event_date"], pair[0].source_ref))
    expected_by_ref = {event.source_ref: expected for event, expected in broken}
    return Table(
        [event for event, _ in broken],
        {
            **columns("evidence_ref", "case_ref", "action", "event_date"),
            "recorded_holder": column("from_holder"),
            "expected_holder": lambda r: expected_by_ref[r.source_ref],
        },
    )


@tool("evidence_ref")
def custody_trail(scope: Scope, params: Mapping[str, Any], unit_path: str) -> Table:
    """One evidence item's chain of custody, oldest first, with any break marked."""
    evidence_ref = params.get("evidence_ref")
    if not isinstance(evidence_ref, str) or not _EVIDENCE_RE.match(evidence_ref):
        raise ToolParamError("evidence_ref must look like EV-014-01")
    _evidence, chains = _forensics(scope, unit_path)
    chain = chains.get(evidence_ref, [])
    expected_by_ref = {event.source_ref: expected for event, expected in chain}
    return Table(
        [event for event, _ in chain],
        {
            **columns("evidence_ref", "action", "event_date", "from_holder", "to_holder"),
            "break": lambda r: expected_by_ref[r.source_ref] is not None,
            "expected_holder": lambda r: expected_by_ref[r.source_ref],
        },
        {"evidence_ref": evidence_ref},
    )

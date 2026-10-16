"""Value types shared by the correlation job and the findings store."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.authz.labels import Labels
from app.clock import demo_today
from app.connectors.base import SourceRecord


@dataclass(frozen=True, slots=True)
class FindingDraft:
    key: str
    analysis: str
    title: str
    summary: str
    severity: str
    classification_code: str
    compartments: list[str]
    unit_path: str
    evidence_ids: list[str]
    details: dict[str, Any]


def draft_finding(
    labels: Labels,
    *,
    key: str,
    analysis: str,
    title: str,
    summary: str,
    unit_path: str,
    evidence: Sequence[SourceRecord],
    rule: str,
    facts: Mapping[str, Any],
    tools: Sequence[str],
    as_of: date | None = None,
) -> FindingDraft:
    """A finding built from `evidence`: it takes their derived label (highest classification,
    union of compartments) and cites exactly them. `details` reads rule, as_of, the analysis's
    own facts, then the typed tools it ran."""
    label = labels.derive(evidence)
    return FindingDraft(
        key=key,
        analysis=analysis,
        title=title,
        summary=summary,
        severity="high",
        classification_code=label.code,
        compartments=list(label.compartments),
        unit_path=unit_path,
        evidence_ids=sorted(r.source_ref for r in evidence),
        details={
            "rule": rule,
            "as_of": (as_of or demo_today()).isoformat(),
            **facts,
            "tools": list(tools),
        },
    )

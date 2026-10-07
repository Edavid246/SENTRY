"""Value types shared by the correlation job and the findings store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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

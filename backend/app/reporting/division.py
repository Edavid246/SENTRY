"""Division status report: the same rows as the division dashboard, set out as a document.

Everything in it is deterministic. The rows are the output of audited typed tools (already
filtered by the policy and RLS for this caller); nothing here calls a model, so nothing in it can
be invented. What carries authority is added here and never left to a renderer:

  * the DRAFT banner (a person reviews it; the assistant informs, humans decide),
  * the derived marking: the highest classification of every row behind the report and the union
    of their compartments (AGENTS.md "derived items"), repeated on every page of an export,
  * the source list (every record reference used).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.authz.labels import Label
from app.reporting.training import DRAFT_BANNER

DEMO_NOTICE = "All data is fictitious demo data. This report informs; people decide."


@dataclass(frozen=True, slots=True)
class ReportRow:
    label: str
    detail: str
    ref: str
    flagged: bool


@dataclass(frozen=True, slots=True)
class ReportSection:
    title: str
    empty_text: str
    flagged: int
    marking: str | None  # None when the section has no rows
    rows: tuple[ReportRow, ...]


@dataclass(frozen=True, slots=True)
class DivisionReport:
    division: str
    title: str
    tagline: str
    generated_at: str
    prepared_for: str
    banner: str
    marking: str
    classification: str
    compartments: tuple[str, ...]
    facts: tuple[tuple[str, str], ...]
    summary: tuple[str, ...]
    sections: tuple[ReportSection, ...]
    refs: tuple[str, ...]
    notice: str


def marking(name: str, compartments: tuple[str, ...] | list[str]) -> str:
    """The marking line: CLASSIFICATION (COMPARTMENT, COMPARTMENT), the level as the UI names it."""
    return name.upper() + (f" ({', '.join(compartments)})" if compartments else "")


def _summary(sections: tuple[ReportSection, ...]) -> tuple[str, ...]:
    total = sum(s.flagged for s in sections)
    if total == 0:
        return ("Nothing needs attention.",)
    noun = "item needs" if total == 1 else "items need"
    lines = [f"{total} {noun} attention."]
    lines += [
        f"{s.title}: {s.flagged} of {len(s.rows)} need attention." for s in sections if s.flagged
    ]
    return tuple(lines)


def build_division_report(
    *,
    division: str,
    name: str,
    tagline: str,
    generated_at: str,
    prepared_for: str,
    facts: tuple[tuple[str, str], ...],
    sections: tuple[ReportSection, ...],
    label: Label,
    label_name: str,
) -> DivisionReport:
    refs = tuple(sorted({row.ref for s in sections for row in s.rows}))
    return DivisionReport(
        division=division,
        title=f"{name} status report",
        tagline=tagline,
        generated_at=generated_at,
        prepared_for=prepared_for,
        banner=DRAFT_BANNER,
        marking=marking(label_name, label.compartments),
        classification=label.code,
        compartments=label.compartments,
        facts=facts,
        summary=_summary(sections),
        sections=sections,
        refs=refs,
        notice=DEMO_NOTICE,
    )

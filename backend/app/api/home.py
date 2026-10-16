"""Group home summary: GET /api/v1/home/summary.

One card per business the caller can see (Briech UAS, EIB Stratoc, Giga Forensics, Poctova)
plus Field Operations, the people and sites out in the field. A card carries an alert only
when something genuinely needs attention; a quiet division has no alert at all.

Same rules as every other data endpoint: a guarded read, so the policy decides first. The counts
and which divisions are shown come from `app.divisions.attention`.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.clock import utc_now_iso
from app.divisions.attention import Attention, division_attention

router = APIRouter(prefix="/api/v1/home", tags=["home"])


class AlertPart(BaseModel):
    what: str = Field(description="what is counted, e.g. 'deliveries overdue'")
    count: int


class HomeAlert(BaseModel):
    count: int = Field(description="everything in this division that needs attention")
    parts: list[AlertPart]
    classification: str
    compartments: list[str]


class HomeDivision(BaseModel):
    key: str
    name: str
    tagline: str
    alert: HomeAlert | None = Field(description="null when nothing needs attention")


class HomeSummary(BaseModel):
    generated_at: str
    divisions: list[HomeDivision]


def _card(attention: Attention) -> HomeDivision:
    division, label = attention.division, attention.label
    alert = None
    if label is not None:
        alert = HomeAlert(
            count=len(attention.refs),
            parts=[AlertPart(what=what, count=count) for what, count in attention.parts],
            classification=label.code,
            compartments=list(label.compartments),
        )
    return HomeDivision(key=division.key, name=division.name, tagline=division.tagline, alert=alert)


@router.get("/summary", response_model=HomeSummary)
def home_summary(ctx: CurrentContext, conn: ConnDep) -> HomeSummary:
    with guarded(ctx, conn, "read", "dashboard") as scope:
        shown = division_attention(scope)
        item_ids = [ref for attention in shown for ref in attention.refs]
        scope.read("dashboard", len(item_ids), item_ids=item_ids)
    return HomeSummary(generated_at=utc_now_iso(), divisions=[_card(a) for a in shown])

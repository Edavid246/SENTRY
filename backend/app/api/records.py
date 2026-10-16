"""Source records: GET /api/v1/records and /api/v1/records/{source_ref}.

Read through the adapter interface (read-only) inside `guarded`: the policy decides first, the
row filter and RLS apply inside the query, and the read is audited. A record that is not
visible answers 404, never 403.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import ConnDep, CurrentContext
from app.api.guard import guarded
from app.connectors import get_adapter
from app.connectors.base import RecordFilter

router = APIRouter(prefix="/api/v1/records", tags=["data"])


class RecordSummary(BaseModel):
    source_ref: str
    entity_type: str
    classification_code: str


class RecordDetail(BaseModel):
    source_ref: str
    entity_type: str
    source_system: str
    classification_code: str
    compartments: list[str]
    unit_path: str
    retrieved_at: str
    data: dict[str, Any]


@router.get("", response_model=list[RecordSummary])
def list_records(ctx: CurrentContext, conn: ConnDep) -> list[RecordSummary]:
    with guarded(ctx, conn, "retrieve", "record") as scope:
        records = get_adapter().search(scope, RecordFilter())
        scope.read("record", len(records))
    return [
        RecordSummary(
            source_ref=record.source_ref,
            entity_type=record.entity_type,
            classification_code=record.classification_code,
        )
        for record in records
    ]


@router.get("/{source_ref}", response_model=RecordDetail)
def get_record(source_ref: str, ctx: CurrentContext, conn: ConnDep) -> RecordDetail:
    """One record, through the adapter (policy row filter + RLS). 404 when not visible."""
    with guarded(ctx, conn, "retrieve", "record", on_deny="not_found") as scope:
        record = get_adapter().get(scope, source_ref)
        scope.read("record", 0 if record is None else 1)
    if record is None:
        raise HTTPException(status_code=404, detail="not found")
    return RecordDetail(
        source_ref=record.source_ref,
        entity_type=record.entity_type,
        source_system=record.source_system,
        classification_code=record.classification_code,
        compartments=list(record.compartments),
        unit_path=record.unit_path,
        retrieved_at=record.retrieved_at.isoformat(),
        data=record.data,
    )

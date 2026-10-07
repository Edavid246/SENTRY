"""Demo reference adapter: the only code that reads canonical_records.

It stands in for the client's logistics / personnel systems (SPEC 11.4). Every
read applies LocalPolicy.row_filter(ctx, "record") inside the SQL, together
with the Postgres RLS context, which the adapter sets itself so it cannot be
called without one. Read-only: no statement here writes.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.authz.context import AccessContext
from app.authz.policy import LocalPolicy
from app.clock import demo_now
from app.connectors.base import AdapterDescription, RecordFilter, SourceRecord
from app.db import get_engine, set_rls_context_for

POLICY = LocalPolicy()

# Record fields a search may compare as an ISO date. The name is a bound
# parameter, never interpolated; the allow-list keeps the surface explicit.
DATE_FIELDS: frozenset[str] = frozenset({"maintenance_due_date", "expires", "mission_date"})
ENTITY_TYPES: tuple[str, ...] = (
    "Equipment",
    "Qualification",
    "StockItem",
    "FaultReport",
    "TrainingEvent",
    "Sensor",
    "Detection",
    "Mission",
    "EvidenceItem",
    "CustodyEvent",
)

_SELECT = (
    "SELECT canonical_records.source_ref, canonical_records.entity_type,"
    " source_systems.name AS source_system, canonical_records.data,"
    " canonical_records.classification_code, canonical_records.compartments,"
    " units.path AS unit_path, canonical_records.retrieved_at"
    " FROM canonical_records"
    " JOIN source_systems ON source_systems.id = canonical_records.source_system_id"
    " JOIN units ON units.id = canonical_records.unit_id"
)
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_ISO_DATE = r"'^\d{4}-\d{2}-\d{2}$'"


def _record(row) -> SourceRecord:
    return SourceRecord(
        source_ref=str(row["source_ref"]),
        entity_type=str(row["entity_type"]),
        source_system=str(row["source_system"]),
        data=dict(row["data"]),
        classification_code=str(row["classification_code"]),
        compartments=tuple(str(code) for code in (row["compartments"] or [])),
        unit_path=str(row["unit_path"]),
        retrieved_at=row["retrieved_at"],
    )


class DemoReferenceAdapter:
    name = "demo-reference"

    def describe(self) -> AdapterDescription:
        return AdapterDescription(
            name=self.name,
            entity_types=ENTITY_TYPES,
            notes=("demo stand-in for the client's logistics and personnel systems",),
        )

    def search(
        self, conn: Connection, ctx: AccessContext, record_filter: RecordFilter
    ) -> list[SourceRecord]:
        set_rls_context_for(conn, ctx)
        row_filter = POLICY.row_filter(ctx, "record")
        clauses = [row_filter.where_sql, "canonical_records.entity_type = :entity_type"]
        params: dict[str, object] = {**row_filter.params, "entity_type": record_filter.entity_type}
        if record_filter.unit_path is not None:
            clauses.append("starts_with(units.path, :filter_unit_path)")
            params["filter_unit_path"] = record_filter.unit_path
        if record_filter.date_field is not None:
            if record_filter.date_field not in DATE_FIELDS:
                raise ValueError(f"date field '{record_filter.date_field}' is not searchable")
            if record_filter.on_or_before is None:
                raise ValueError("date_field requires on_or_before")
            # ISO dates compare correctly as text; the regex guard skips rows whose
            # field is absent or malformed instead of erroring on them.
            clauses.append(
                f"(canonical_records.data->>:date_field ~ {_ISO_DATE}"
                " AND canonical_records.data->>:date_field <= :on_or_before)"
            )
            params["date_field"] = record_filter.date_field
            params["on_or_before"] = record_filter.on_or_before.isoformat()
        rows = (
            conn.execute(
                text(
                    _SELECT
                    + " WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY canonical_records.source_ref"
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [_record(row) for row in rows]

    def get(self, conn: Connection, ctx: AccessContext, source_ref: str) -> SourceRecord | None:
        set_rls_context_for(conn, ctx)
        row_filter = POLICY.row_filter(ctx, "record")
        row = (
            conn.execute(
                text(
                    _SELECT
                    + " WHERE canonical_records.source_ref = :source_ref"
                    + f" AND {row_filter.where_sql}"
                ),
                {"source_ref": source_ref, **row_filter.params},
            )
            .mappings()
            .first()
        )
        return None if row is None else _record(row)

    def stream(self, ctx: AccessContext, since: datetime) -> Iterator[SourceRecord]:
        """STUB live feed (docs/STUBS.md): replay the seeded detections in time order.

        Yields the Detection records the caller may see (same policy row filter + RLS as
        search) with observed_at after `since` and not after the demo "now". Timing is
        the caller's job: the replay endpoint decides how fast the clock advances.
        """
        cutoff = since.astimezone(UTC).strftime(_TS_FORMAT)
        end = demo_now().strftime(_TS_FORMAT)
        with get_engine().connect() as conn:
            records = self.search(conn, ctx, RecordFilter(entity_type="Detection"))
        fresh = [r for r in records if cutoff < str(r.data["observed_at"]) <= end]
        yield from sorted(fresh, key=lambda r: (r.data["observed_at"], r.source_ref))

    def sync(self, ctx: AccessContext) -> int:
        return 0  # nothing to refresh: the demo data is the source of truth

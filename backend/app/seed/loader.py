"""Seed the gateway database with the fictitious demo corpus (AGENTS.md).

Deterministic uuid5 ids plus a full delete-then-insert make the seed
idempotent: running it twice leaves identical row counts. The audit table is
never touched (append-only, SPEC 14.2). Demo data only — fictitious people,
units, documents and records.

Run:  uv run python -m app.seed            (main gateway DB, as owner)
Tests: app.seed.run(test_owner_database_url)
"""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from sqlalchemy import create_engine, delete

from app.audit.models import AuditEvent
from app.authz.models import (
    ClassificationLevel,
    Compartment,
    Unit,
    User,
    UserCompartment,
)
from app.config import get_settings
from app.connectors.models import CanonicalRecord, SourceSystem
from app.correlation.models import Finding
from app.ids import entity_id, source_id, unit_id
from app.knowledge.models import Chunk, Conversation, Document, Message
from app.seed.identity import (
    ARCHIVED_USERS,
    CLASSIFICATION_LEVELS,
    COMPARTMENTS,
    DEMO_PASSWORD,
    DOCUMENTS,
    SOURCE_SYSTEMS,
    UNITS,
    USERS,
)
from app.seed.records import RECORDS


def _chunk_texts(doc_ref: str, title: str, unit_path: str) -> list[tuple[str, str, int]]:
    """Two chunks per document. Exactly one chunk of DOC-001/006/013 contains
    the keyword 'maintenance' (the retrieval demo's planted match); no other
    document's text contains it."""
    summary = f"{title} — reference copy held at {unit_path}."
    if doc_ref == "DOC-013":
        body = (
            "Section 2: ordering via maintenance stores requires unit approval."
            f" Reference {doc_ref}."
        )
        return [(summary, "Summary", 1), (body, "Section 2", 2)]
    body = f"Section 1: standard administrative content for demo purposes. Reference {doc_ref}."
    return [(summary, "Summary", 1), (body, "Section 1", 2)]


def _rows(include_archived: bool = False) -> dict[type, list[dict]]:
    unit_rows = [
        {
            "id": unit_id(u["path"]),
            "name": u["name"],
            "parent_id": unit_id(u["parent"]) if u["parent"] else None,
            "path": u["path"],
            "depth": u["depth"],
        }
        for u in UNITS
    ]

    hasher = PasswordHasher()
    user_rows = []
    user_compartment_rows = []
    for u in USERS + (ARCHIVED_USERS if include_archived else []):
        user_id = entity_id(f"user:{u['username']}")
        user_rows.append(
            {
                "id": user_id,
                "username": u["username"],
                "display_name": u["display_name"],
                "role": u["role"],
                "unit_id": unit_id(u["unit"]),
                "clearance_code": u["clearance"],
                "keycloak_id": None,
                "data_scope": u["data_scope"],
                "is_active": True,
                "password_hash": hasher.hash(DEMO_PASSWORD),
            }
        )
        user_compartment_rows.extend(
            {"user_id": user_id, "compartment_code": code} for code in sorted(u["compartments"])
        )

    source_rows = [
        {
            "id": source_id(s["name"]),
            "name": s["name"],
            "adapter_type": s["adapter_type"],
            "default_classification": "restricted",
            "status": s["status"],
        }
        for s in SOURCE_SYSTEMS
    ]

    document_rows = []
    chunk_rows = []
    for ref, title, classification, compartments, unit_path in DOCUMENTS:
        doc_id = entity_id(f"doc:{ref}")
        document_rows.append(
            {
                "id": doc_id,
                "title": title,
                "source_system_id": source_id("documents-ref"),
                "source_ref": ref,
                "classification_code": classification,
                "compartments": compartments,
                "unit_id": unit_id(unit_path),
                "content_hash": hashlib.sha256(
                    f"{ref}|{title}|{classification}|{unit_path}".encode()
                ).hexdigest(),
                "status": "published",
                "version": 1,
            }
        )
        for i, (text, section, page) in enumerate(_chunk_texts(ref, title, unit_path), start=1):
            chunk_rows.append(
                {
                    "id": entity_id(f"chunk:{ref}:{i}"),
                    "document_id": doc_id,
                    "text": text,
                    "embedding": None,
                    "page": page,
                    "section": section,
                    "classification_code": classification,
                    "compartments": compartments,
                    "unit_id": unit_id(unit_path),
                }
            )

    base_time = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)
    record_rows = [
        {
            "id": entity_id(f"record:{ref}"),
            "entity_type": entity_type,
            "source_system_id": source_id(source),
            "source_ref": ref,
            "data": data,
            "classification_code": classification,
            "compartments": compartments,
            "unit_id": unit_id(unit_path),
            "retrieved_at": base_time + timedelta(minutes=i),
        }
        for i, (
            ref,
            entity_type,
            source,
            classification,
            compartments,
            unit_path,
            data,
        ) in enumerate(RECORDS)
    ]

    return {
        ClassificationLevel: CLASSIFICATION_LEVELS,
        Compartment: COMPARTMENTS,
        Unit: unit_rows,
        User: user_rows,
        UserCompartment: user_compartment_rows,
        SourceSystem: source_rows,
        Document: document_rows,
        Chunk: chunk_rows,
        CanonicalRecord: record_rows,
    }


# Children first, parents last (FK order). Conversation turns are user data
# that reference users, so a reseed clears them too. audit_events is never
# touched.
_DELETE_ORDER = (
    Finding,
    Message,
    Conversation,
    Chunk,
    Document,
    CanonicalRecord,
    UserCompartment,
    User,
    Unit,
    SourceSystem,
    Compartment,
    ClassificationLevel,
)


def run(url: str, include_archived: bool = False) -> None:
    """Replace the demo corpus atomically (idempotent; owner role required)."""
    engine = create_engine(url)
    try:
        rows = _rows(include_archived)
        with engine.begin() as conn:
            for table in _DELETE_ORDER:
                conn.execute(delete(table))
            for table in (
                ClassificationLevel,
                Compartment,
                Unit,
                User,
                UserCompartment,
                SourceSystem,
                Document,
                Chunk,
                CanonicalRecord,
            ):
                conn.execute(table.__table__.insert(), rows[table])
    finally:
        engine.dispose()


def main() -> None:
    # --include-archived also seeds the archived restricted accounts, for restricted-view
    # demos and the web smoke test. The product seed (no flag) has the owner only.
    include_archived = "--include-archived" in sys.argv[1:]
    run(get_settings().owner_database_url, include_archived)
    counts = {t.__name__: len(r) for t, r in _rows(include_archived).items()}
    print(f"seeded demo corpus: {counts}; audit_events untouched ({AuditEvent.__tablename__})")


if __name__ == "__main__":
    main()

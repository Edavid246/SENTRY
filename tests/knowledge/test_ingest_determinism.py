"""Re-ingest determinism: the demo cache keys embed chunk ids and chunk text, so a
plain re-ingest of the same corpus must reproduce them exactly."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.knowledge.ingest import ingest_documents
from sqlalchemy import text
from sqlalchemy.engine import Engine

DOCS_DIR = Path(__file__).resolve().parents[2] / "data" / "documents"


def _snapshot(engine: Engine) -> list[tuple]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.id, d.source_ref, c.page, c.section, c.text FROM chunks c"
                " JOIN documents d ON d.id = c.document_id"
                " WHERE d.source_ref LIKE 'DOC-2%' ORDER BY d.source_ref, c.id"
            )
        ).all()
    return [
        (str(r.id), r.source_ref, r.page, r.section, hashlib.sha256(r.text.encode()).hexdigest())
        for r in rows
    ]


def test_reingest_gives_identical_chunk_ids_and_text(
    ingested: dict[str, int], owner_engine: Engine
) -> None:
    first = _snapshot(owner_engine)
    assert first
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM chunks WHERE document_id IN"
                " (SELECT id FROM documents WHERE source_ref LIKE 'DOC-2%')"
            )
        )
        conn.execute(text("DELETE FROM documents WHERE source_ref LIKE 'DOC-2%'"))
    assert _snapshot(owner_engine) == []
    ingest_documents(owner_engine, DOCS_DIR)
    assert _snapshot(owner_engine) == first

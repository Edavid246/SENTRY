"""Ingestion worker: the demo corpus becomes classified, searchable chunks.

Proves the pipeline end to end at the schema level: documents/chunks created,
chunks inherit the document's classification/compartments/unit, the
full-text index is populated by the trigger (no caller action), and a second
run is a no-op (idempotent)."""

from __future__ import annotations

from app.ids import entity_id as _id
from sqlalchemy import text
from sqlalchemy.engine import Engine

EXPECTED_REFS = {"DOC-201", "DOC-202", "DOC-203", "DOC-204"}


def test_ingest_creates_classified_documents_and_chunks(
    ingested: dict[str, int], owner_engine: Engine
) -> None:
    assert ingested["documents"] == 4
    assert ingested["chunks"] > 0
    with owner_engine.connect() as conn:
        refs = set(
            conn.execute(
                text("SELECT source_ref FROM documents WHERE source_ref LIKE 'DOC-2%'")
            ).scalars()
        )
        assert refs == EXPECTED_REFS
        # Every ingested chunk inherits its document's markings.
        violations = conn.execute(
            text(
                "SELECT count(*) FROM chunks ch JOIN documents d ON d.id = ch.document_id "
                "WHERE ch.classification_code IS DISTINCT FROM d.classification_code "
                "OR ch.unit_id IS DISTINCT FROM d.unit_id "
                "OR ch.compartments IS DISTINCT FROM d.compartments"
            )
        ).scalar()
        assert violations == 0


def test_search_vector_is_populated_by_trigger(
    ingested: dict[str, int], owner_engine: Engine
) -> None:
    with owner_engine.connect() as conn:
        null_vectors = conn.execute(
            text("SELECT count(*) FROM chunks WHERE search_vector IS NULL")
        ).scalar()
        matches = conn.execute(
            text(
                "SELECT count(*) FROM chunks ch JOIN documents d ON d.id = ch.document_id "
                "WHERE d.source_ref = 'DOC-201' AND ch.search_vector"
                " @@ to_tsquery('english','maintenance')"
            )
        ).scalar()
    assert null_vectors == 0
    assert matches >= 1


def test_reingest_is_idempotent(ingested: dict[str, int], owner_engine: Engine) -> None:
    from pathlib import Path

    from app.knowledge.ingest import ingest_documents

    docs_dir = Path(__file__).resolve().parents[2] / "data" / "documents"
    with owner_engine.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM chunks")).scalar()
    ingest_documents(owner_engine, docs_dir)
    with owner_engine.connect() as conn:
        after = conn.execute(text("SELECT count(*) FROM chunks")).scalar()
    assert after == before


def test_chunk_ids_are_deterministic(ingested: dict[str, int], owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        chunk_ids = set(
            conn.execute(
                text(
                    "SELECT ch.id FROM chunks ch JOIN documents d ON d.id = ch.document_id "
                    "WHERE d.source_ref = 'DOC-201'"
                )
            ).scalars()
        )
    assert _id("chunk:DOC-201:1") in chunk_ids
    assert chunk_ids == {_id(f"chunk:DOC-201:{index}") for index in range(1, len(chunk_ids) + 1)}


def test_backfill_embeds_only_null_chunks_and_is_idempotent(
    migrated: None, seeded: None, owner_engine: Engine, monkeypatch
) -> None:
    """Seeded chunks (no source file) get embedded in place; a rerun is a no-op."""
    from app.config import get_settings
    from app.knowledge.ingest import backfill_embeddings

    dim = get_settings().embedding_dim
    monkeypatch.setattr("app.knowledge.ingest._embed", lambda texts: [[0.5] * dim for _ in texts])
    try:
        with owner_engine.connect() as conn:
            missing = conn.execute(
                text("SELECT count(*) FROM chunks WHERE embedding IS NULL")
            ).scalar()
        assert missing, "seed should leave chunks unembedded"
        assert backfill_embeddings(owner_engine) == missing
        with owner_engine.connect() as conn:
            assert (
                conn.execute(text("SELECT count(*) FROM chunks WHERE embedding IS NULL")).scalar()
                == 0
            )
        assert backfill_embeddings(owner_engine) == 0
    finally:
        with owner_engine.begin() as conn:
            conn.execute(text("UPDATE chunks SET embedding = NULL"))

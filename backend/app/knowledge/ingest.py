"""Document ingestion worker (SPEC §9.1).

Reads the demo document corpus (data/documents/ + manifest.json), parses each
PDF/DOCX into section/paragraph chunks, embeds every chunk with the local
embedder (SPEC 8.1 — embeddings never leave the machine) and stores documents
and chunks with the classification/compartments/unit carried by the manifest.
Chunks inherit the document's classification and compartments.

Runs as the database owner (ingestion is a privileged background job; the
runtime role has SELECT-only grants on documents/chunks). Idempotent: a
document whose content hash is unchanged and whose chunks are all present and
embedded is left untouched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import delete, text
from sqlalchemy.engine import Engine

from app.knowledge.models import Chunk, Document
from app.knowledge.parse import parse_document

MANIFEST_NAME = "manifest.json"
SKIPPED_FILES = {MANIFEST_NAME, ".DS_Store"}


def _id(kind: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"defence-gateway:{kind}")


def _unit_id(path: str) -> UUID:
    return _id(f"unit:{path}")


def _source_id(name: str) -> UUID:
    return _id(f"source-system:{name}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(docs_dir: Path) -> list[dict]:
    manifest_path = docs_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing ingestion manifest: {manifest_path}")
    entries = json.loads(manifest_path.read_text())
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"manifest must be a non-empty list: {manifest_path}")
    return entries


def _embed(texts: list[str]) -> list[list[float] | None]:
    """Embed chunk texts locally; embeddings are optional (FTS-only fallback).

    If the local embedder is unavailable in this environment (weights not
    present) ingestion still succeeds and stores NULL embeddings, and hybrid
    retrieval degrades to full-text search only. The demo profile ships the
    weights, so this is a defensive path, not the normal one.
    """
    if not texts:
        return []
    try:
        from app.ai_gateway.embeddings import get_embedder

        return [list(vector) for vector in get_embedder().embed(texts)]
    except Exception:  # noqa: BLE001 - degrade to FTS-only rather than fail ingestion
        return [None] * len(texts)


def ingest_documents(engine: Engine, docs_dir: Path) -> dict[str, int]:
    """Ingest every manifest document; returns counts for the report."""
    entries = load_manifest(docs_dir)
    summary = {"documents": 0, "chunks": 0, "skipped": 0, "embedded": 0}
    with engine.begin() as conn:
        for entry in sorted(entries, key=lambda e: str(e["source_ref"])):
            ref = str(entry["source_ref"])
            path = docs_dir / str(entry["file"])
            if not path.exists():
                raise FileNotFoundError(f"manifest references missing file: {path}")
            content_hash = _sha256(path)
            doc_id = _id(f"doc:{ref}")
            existing = conn.execute(
                text("SELECT content_hash FROM documents WHERE id = :id"),
                {"id": doc_id},
            ).first()
            if existing is not None and existing.content_hash == content_hash:
                missing_embeddings = conn.execute(
                    text(
                        "SELECT count(*) FROM chunks WHERE document_id = :id AND embedding IS NULL"
                    ),
                    {"id": doc_id},
                ).scalar()
                chunk_count = conn.execute(
                    text("SELECT count(*) FROM chunks WHERE document_id = :id"),
                    {"id": doc_id},
                ).scalar()
                if chunk_count and not missing_embeddings:
                    summary["skipped"] += 1
                    continue

            parsed = parse_document(path)
            vectors = _embed([chunk.text for chunk in parsed])

            conn.execute(delete(Chunk).where(Chunk.document_id == doc_id))
            conn.execute(delete(Document).where(Document.id == doc_id))
            conn.execute(
                Document.__table__.insert(),
                {
                    "id": doc_id,
                    "title": str(entry["title"]),
                    "source_system_id": _source_id("documents-ref"),
                    "source_ref": ref,
                    "classification_code": str(entry["classification"]),
                    "compartments": list(entry["compartments"]),
                    "unit_id": _unit_id(str(entry["unit_path"])),
                    "content_hash": content_hash,
                    "status": "published",
                    "version": 1,
                },
            )
            chunk_rows = []
            for index, chunk in enumerate(parsed, start=1):
                vector = vectors[index - 1]
                if vector is not None:
                    summary["embedded"] += 1
                chunk_rows.append(
                    {
                        "id": _id(f"chunk:{ref}:{index}"),
                        "document_id": doc_id,
                        "text": chunk.text,
                        "embedding": vector,
                        "page": chunk.page,
                        "section": chunk.section,
                        "classification_code": str(entry["classification"]),
                        "compartments": list(entry["compartments"]),
                        "unit_id": _unit_id(str(entry["unit_path"])),
                    }
                )
            conn.execute(Chunk.__table__.insert(), chunk_rows)
            summary["documents"] += 1
            summary["chunks"] += len(chunk_rows)
    return summary


def backfill_embeddings(engine: Engine, batch_size: int = 16) -> int:
    """Embed every chunk whose embedding is NULL; returns the number embedded.

    Covers seeded chunks that have no source file to ingest. Runs as the
    owner (chunks are SELECT-only for the runtime role). Idempotent, and a
    no-op when the embedder is unavailable (retrieval stays FTS-only).
    """
    done = 0
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, text FROM chunks WHERE embedding IS NULL ORDER BY id")
        ).all()
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            vectors = _embed([row.text for row in batch])
            for row, vector in zip(batch, vectors, strict=True):
                if vector is None:
                    return done
                conn.execute(
                    text("UPDATE chunks SET embedding = CAST(:v AS vector) WHERE id = :id"),
                    {"v": "[" + ",".join(f"{x:.7f}" for x in vector) + "]", "id": row.id},
                )
                done += 1
    return done

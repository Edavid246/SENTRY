"""Document and passage reads for the knowledge pathway (SPEC 9.2, 10.1).

Every read runs on an authorized Scope (app.authz.scope) and puts the scope's
row filter inside the SQL, so a document or passage the caller may not see is
never read. Anything not visible, or a malformed id, comes back as None/absent;
the routes turn that into a 404.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from app.authz.scope import Scope
from app.db import format_array

_PASSAGE_SELECT = (
    "SELECT chunks.id AS chunk_id, documents.id AS document_id, documents.source_ref,"
    " documents.title, chunks.text, chunks.page, chunks.section,"
    " chunks.classification_code, chunks.compartments"
    " FROM chunks JOIN documents ON documents.id = chunks.document_id"
)


@dataclass(frozen=True, slots=True)
class DocumentRow:
    source_ref: str
    title: str
    classification_code: str


@dataclass(frozen=True, slots=True)
class Passage:
    """One chunk with the document it belongs to (what a citation opens)."""

    chunk_id: str
    document_id: str
    document_ref: str
    document_title: str
    text: str
    page: int | None
    section: str | None
    classification_code: str
    compartments: tuple[str, ...]


def _passage(row) -> Passage:
    return Passage(
        chunk_id=str(row["chunk_id"]),
        document_id=str(row["document_id"]),
        document_ref=str(row["source_ref"] or ""),
        document_title=str(row["title"]),
        text=str(row["text"]),
        page=row["page"],
        section=row["section"],
        classification_code=str(row["classification_code"]),
        compartments=tuple(str(code) for code in (row["compartments"] or [])),
    )


def _uuid(value: str) -> str | None:
    try:
        return str(UUID(value))
    except ValueError:
        return None


def list_documents(scope: Scope, source_ref: str | None = None) -> list[DocumentRow]:
    """The documents the caller may see, by source_ref (or just the one named)."""
    row_filter = scope.filter("document")
    where, params = row_filter.where_sql, dict(row_filter.params)
    if source_ref is not None:
        where += " AND source_ref = :source_ref"
        params["source_ref"] = source_ref
    rows = scope.conn.execute(
        text(
            "SELECT source_ref, title, classification_code FROM documents"
            f" WHERE {where} ORDER BY source_ref"
        ),
        params,
    ).all()
    return [DocumentRow(str(r.source_ref), str(r.title), str(r.classification_code)) for r in rows]


def visible_passage(scope: Scope, document_id: str, chunk_id: str) -> Passage | None:
    """The passage, if visible; `document_id` is a source_ref or the document's uuid."""
    chunk_key = _uuid(chunk_id)
    if chunk_key is None:
        return None
    document_key = _uuid(document_id)
    document_where = (
        "documents.id = :document_id" if document_key else "documents.source_ref = :document_id"
    )
    row_filter = scope.filter("chunk")
    row = (
        scope.conn.execute(
            text(
                f"{_PASSAGE_SELECT} WHERE chunks.id = :chunk_id AND {document_where}"
                f" AND {row_filter.where_sql}"
            ),
            {
                "chunk_id": chunk_key,
                "document_id": document_key or document_id,
                **row_filter.params,
            },
        )
        .mappings()
        .first()
    )
    return None if row is None else _passage(row)


def visible_passages(scope: Scope, chunk_ids: list[str]) -> dict[str, Passage]:
    """The named passages the caller may still see, by chunk id; the rest drop out."""
    if not chunk_ids:
        return {}
    row_filter = scope.filter("chunk")
    rows = (
        scope.conn.execute(
            text(
                f"{_PASSAGE_SELECT} WHERE chunks.id = ANY(CAST(:ids AS uuid[]))"
                f" AND {row_filter.where_sql}"
            ),
            {"ids": format_array(chunk_ids), **row_filter.params},
        )
        .mappings()
        .all()
    )
    return {passage.chunk_id: passage for passage in map(_passage, rows)}

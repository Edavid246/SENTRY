"""Permission-aware hybrid retrieval (SPEC §8.2, §9).

Vector similarity (pgvector, exact search) fused with PostgreSQL full-text
search by reciprocal rank fusion (RRF). The authorization filter is applied
INSIDE the SQL query — bound parameters only, from the same LocalPolicy
row_filter the other endpoints use — so unauthorized chunks are never
retrieved (Principle Zero: authorization before retrieval, enforced in the
database, not by filtering results afterwards). The caller also sets the RLS
context, so both layers agree; docs/PRODUCTION_DEBT.md records the RRF choice
over a neural reranker (reranker is DEMO CUT).

A chunk is a candidate if it matches the full-text query OR its vector
similarity clears the configured floor. With no embedder available the query
degrades to full-text only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.authz.context import AccessContext
from app.authz.policy import LocalPolicy
from app.config import get_settings

POLICY = LocalPolicy()
RRF_K = 60.0


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_title: str
    document_ref: str
    text: str
    page: int | None
    section: str | None
    classification_code: str
    compartments: tuple[str, ...]
    vector_similarity: float | None
    keyword_rank: float | None
    rrf_score: float

    @property
    def source(self) -> str:
        if self.vector_similarity is not None and self.keyword_rank is not None:
            return "hybrid"
        if self.vector_similarity is not None:
            return "vector"
        return "fts"


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.7f}" for value in vector) + "]"


def _query_embedding(question: str) -> list[float] | None:
    try:
        from app.ai_gateway.embeddings import get_embedder

        return list(get_embedder().embed([question])[0])
    except Exception:  # noqa: BLE001 - degrade to full-text search
        return None


def retrieve_chunks(
    conn: Connection,
    ctx: AccessContext,
    question: str,
    *,
    top_k: int | None = None,
    min_similarity: float | None = None,
    query_vector: list[float] | None = None,
) -> list[RetrievedChunk]:
    """Return the authorized chunks most relevant to the question, best first."""
    settings = get_settings()
    limit = top_k if top_k is not None else settings.retrieval_top_k
    floor = min_similarity if min_similarity is not None else settings.retrieval_min_similarity
    vector = query_vector if query_vector is not None else _query_embedding(question)
    row_filter = POLICY.row_filter(ctx, "chunk")
    params: dict[str, Any] = {
        **row_filter.params,
        "question": question,
        "has_vector": vector is not None,
        "query_vector": _vector_literal(vector) if vector is not None else None,
        "min_similarity": float(floor),
        "rrf_k": RRF_K,
        "top_k": int(limit),
    }
    sql = f"""
        WITH parsed AS (
            SELECT websearch_to_tsquery('english', :question) AS tsq
        ),
        scored AS (
            SELECT
                chunks.id AS chunk_id,
                chunks.document_id,
                chunks.text,
                chunks.page,
                chunks.section,
                chunks.classification_code,
                chunks.compartments,
                documents.title AS document_title,
                documents.source_ref,
                CASE
                    WHEN :has_vector AND chunks.embedding IS NOT NULL
                    THEN 1 - (chunks.embedding <=> CAST(:query_vector AS vector))
                END AS vector_similarity,
                CASE
                    WHEN chunks.search_vector @@ parsed.tsq
                    THEN ts_rank_cd(chunks.search_vector, parsed.tsq, 32)
                END AS keyword_rank
            FROM chunks
            JOIN documents ON documents.id = chunks.document_id
            CROSS JOIN parsed
            WHERE {row_filter.where_sql}
        ),
        fused AS (
            SELECT *,
                CASE WHEN vector_similarity IS NOT NULL THEN
                    1.0 / (
                        :rrf_k
                        + row_number() OVER (ORDER BY vector_similarity DESC NULLS LAST)
                    )
                ELSE 0 END
                + CASE WHEN keyword_rank IS NOT NULL THEN
                    1.0 / (:rrf_k + row_number() OVER (ORDER BY keyword_rank DESC NULLS LAST))
                ELSE 0 END AS rrf_score
            FROM scored
        )
        SELECT * FROM fused
        WHERE vector_similarity >= :min_similarity OR keyword_rank IS NOT NULL
        ORDER BY rrf_score DESC, vector_similarity DESC NULLS LAST, chunk_id
        LIMIT :top_k
    """
    rows = conn.execute(text(sql), params).mappings().all()
    return [
        RetrievedChunk(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            document_title=str(row["document_title"]),
            document_ref=str(row["source_ref"] or ""),
            text=str(row["text"]),
            page=row["page"],
            section=row["section"],
            classification_code=str(row["classification_code"]),
            compartments=tuple(str(compartment) for compartment in (row["compartments"] or [])),
            vector_similarity=(
                float(row["vector_similarity"]) if row["vector_similarity"] is not None else None
            ),
            keyword_rank=(float(row["keyword_rank"]) if row["keyword_rank"] is not None else None),
            rrf_score=float(row["rrf_score"]),
        )
        for row in rows
    ]

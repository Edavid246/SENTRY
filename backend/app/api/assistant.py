"""Assistant endpoints (SPEC §8.2, §9.2, §10.1).

POST /api/v1/assistant/query maps HTTP onto `app.assistant.service.answer`,
which owns the authorization order, the pathways (knowledge, data, report),
labelling, conversation storage and the audit trail. This module only turns
requests into calls and outcomes into responses: AssistantForbidden -> 403,
ConversationNotFound -> 404, ModelUnavailable -> 503.

Conversation reads (GET /conversations, GET /conversations/{id}) resolve the
caller's own threads only, under the same decide + row filter + RLS order,
and are audited like every other read. Citations for a stored turn are
resolved from its inline citation markers, chunk by chunk, through the chunk
row filter — a passage that is no longer visible simply drops out.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import (
    ConnDep,
    CurrentContext,
    ModelsDep,
    audit_events,
    decide_event,
    query_event,
)
from app.assistant.conversations import ConversationNotFound
from app.assistant.service import AssistantForbidden, ModelUnavailable, answer
from app.authz.context import AccessContext
from app.authz.policy import LocalPolicy
from app.db import format_array, set_rls_context_for
from app.knowledge.answer import parse_cited_chunk_ids
from app.knowledge.retrieve import RetrievedChunk

POLICY = LocalPolicy()
router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

MAX_QUESTION_CHARS = 2000


class AssistantQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    conversation_id: UUID | None = None


class CitationOut(BaseModel):
    chunk_id: str
    document_title: str
    document_ref: str
    page: int | None
    section: str | None
    classification_code: str


class ResultTable(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]


class ReportInfo(BaseModel):
    draft: bool = True
    classification_code: str
    compartments: list[str]
    record_ids: list[str]
    document_refs: list[str]


class AssistantQueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    found: bool = Field(
        description="false when nothing was found in approved sources, or a refusal"
    )
    degraded: bool = Field(description="true when retrieval ran keyword-only (FTS only)")
    refused: bool = Field(
        description=(
            "true for permission-manipulation attempts, blocked answers and safe tool refusals"
        )
    )
    result_table: ResultTable | None = Field(
        default=None, description="deterministic tool output of the data pathway, else null"
    )
    report: ReportInfo | None = Field(
        default=None, description="set for a drafted report: draft flag and derived label"
    )
    conversation_id: str
    audit_event_id: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    classification_code: str
    compartments: list[str]
    created_at: str
    updated_at: str


class TurnOut(BaseModel):
    role: str
    content: str
    created_at: str
    citations: list[CitationOut] = Field(default_factory=list)


class ConversationDetail(ConversationSummary):
    turns: list[TurnOut]


@router.post("/query", response_model=AssistantQueryResponse)
def query_assistant(
    body: AssistantQueryRequest,
    ctx: CurrentContext,
    conn: ConnDep,
    models: ModelsDep,
) -> AssistantQueryResponse:
    try:
        outcome = answer(ctx, conn, body.question, body.conversation_id, models=models)
    except AssistantForbidden:
        raise HTTPException(status_code=403, detail="forbidden") from None
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="not found") from None
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from exc
    table, report = outcome.table, outcome.report
    return AssistantQueryResponse(
        answer=outcome.answer,
        citations=[_citation_from_chunk(chunk) for chunk in outcome.citations],
        found=outcome.found,
        degraded=outcome.degraded,
        refused=outcome.refused,
        result_table=(ResultTable(columns=list(table.columns), rows=table.rows) if table else None),
        report=(
            ReportInfo(
                classification_code=report.classification_code,
                compartments=list(report.compartments),
                record_ids=list(report.record_ids),
                document_refs=list(report.document_refs),
            )
            if report
            else None
        ),
        conversation_id=outcome.conversation_id,
        audit_event_id=outcome.audit_event_id,
    )


def _citation_from_chunk(chunk: RetrievedChunk) -> CitationOut:
    return CitationOut(
        chunk_id=chunk.chunk_id,
        document_title=chunk.document_title,
        document_ref=chunk.document_ref,
        page=chunk.page,
        section=chunk.section,
        classification_code=chunk.classification_code,
    )


def _citation_from_row(row) -> CitationOut:
    return CitationOut(
        chunk_id=str(row["id"]),
        document_title=str(row["title"]),
        document_ref=str(row["source_ref"] or ""),
        page=row["page"],
        section=row["section"],
        classification_code=str(row["classification_code"]),
    )


def _visible_citations(conn, ctx: AccessContext, chunk_ids: list[str]) -> dict[str, CitationOut]:
    """Resolve stored citation markers to the chunks the caller may still see.

    Same policy row filter as retrieval: a passage whose classification,
    compartments or unit no longer line up with the caller simply drops out.
    """
    if not chunk_ids:
        return {}
    chunk_filter = POLICY.row_filter(ctx, "chunk")
    rows = (
        conn.execute(
            text(
                "SELECT chunks.id, documents.source_ref, documents.title, chunks.page,"
                " chunks.section, chunks.classification_code"
                " FROM chunks"
                " JOIN documents ON documents.id = chunks.document_id"
                " WHERE chunks.id::text = ANY(CAST(:ids AS text[]))"
                f" AND {chunk_filter.where_sql}"
            ),
            {"ids": format_array(chunk_ids), **chunk_filter.params},
        )
        .mappings()
        .all()
    )
    return {str(row["id"]): _citation_from_row(row) for row in rows}


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    ctx: CurrentContext,
    conn: ConnDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConversationSummary]:
    """The caller's own conversations, newest first (SPEC §10.1).

    Another user's conversations are never in scope: the ownership predicate
    is part of the SQL, alongside the policy row filter and RLS.
    """
    decision = POLICY.decide(ctx, "read", "conversation")
    if not decision.allowed:
        audit_events([decide_event(ctx, decision, resource="conversation", requested="read")])
        raise HTTPException(status_code=403, detail="forbidden")
    set_rls_context_for(conn, ctx)
    row_filter = POLICY.row_filter(ctx, "conversation")
    rows = (
        conn.execute(
            text(
                "SELECT id, title, classification_code, compartments, created_at, updated_at"
                " FROM conversations"
                " WHERE user_id = :user_id"
                f" AND {row_filter.where_sql}"
                " ORDER BY updated_at DESC, id DESC LIMIT :limit"
            ),
            {"user_id": ctx.user_id, "limit": limit, **row_filter.params},
        )
        .mappings()
        .all()
    )
    results = [
        ConversationSummary(
            id=str(row["id"]),
            title=str(row["title"]),
            classification_code=str(row["classification_code"]),
            compartments=[str(code) for code in (row["compartments"] or [])],
            created_at=row["created_at"].isoformat(),
            updated_at=row["updated_at"].isoformat(),
        )
        for row in rows
    ]
    audit_events(
        [
            decide_event(ctx, decision, resource="conversation", requested="read"),
            query_event(ctx, "conversations", len(results)),
        ]
    )
    return results


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: UUID, ctx: CurrentContext, conn: ConnDep
) -> ConversationDetail:
    """One of the caller's conversations with its turns and resolved citations.

    A conversation owned by anyone else — or one the caller's action is not
    allowed to read — answers 404, exactly like the POST that appends to it,
    so an id can never be probed for existence.
    """
    decision = POLICY.decide(ctx, "read", "conversation")
    if not decision.allowed:
        audit_events([decide_event(ctx, decision, resource="conversation", requested="read")])
        raise HTTPException(status_code=404, detail="not found")
    set_rls_context_for(conn, ctx)
    conversation_filter = POLICY.row_filter(ctx, "conversation")
    row = (
        conn.execute(
            text(
                "SELECT id, title, classification_code, compartments, created_at, updated_at"
                " FROM conversations"
                " WHERE id = :id AND user_id = :user_id"
                f" AND {conversation_filter.where_sql}"
            ),
            {"id": conversation_id, "user_id": ctx.user_id, **conversation_filter.params},
        )
        .mappings()
        .first()
    )
    if row is None:
        audit_events(
            [
                decide_event(ctx, decision, resource="conversation", requested="read"),
                query_event(ctx, "conversations", 0),
            ]
        )
        raise HTTPException(status_code=404, detail="not found")

    message_filter = POLICY.row_filter(ctx, "message")
    messages = (
        conn.execute(
            text(
                "SELECT role, content, created_at FROM messages"
                " WHERE conversation_id = :id"
                f" AND {message_filter.where_sql}"
                " ORDER BY created_at, CASE role WHEN 'user' THEN 0 ELSE 1 END, id"
            ),
            {"id": conversation_id, **message_filter.params},
        )
        .mappings()
        .all()
    )

    wanted: list[str] = []
    for message in messages:
        if str(message["role"]) == "assistant":
            wanted.extend(parse_cited_chunk_ids(str(message["content"])))
    citations = _visible_citations(conn, ctx, list(dict.fromkeys(wanted)))

    turns = [
        TurnOut(
            role=str(message["role"]),
            content=str(message["content"]),
            created_at=message["created_at"].isoformat(),
            citations=[
                citations[chunk_id]
                for chunk_id in parse_cited_chunk_ids(str(message["content"]))
                if chunk_id in citations
            ],
        )
        for message in messages
    ]
    audit_events(
        [
            decide_event(ctx, decision, resource="conversation", requested="read"),
            query_event(ctx, "messages", len(turns)),
        ]
    )
    return ConversationDetail(
        id=str(row["id"]),
        title=str(row["title"]),
        classification_code=str(row["classification_code"]),
        compartments=[str(code) for code in (row["compartments"] or [])],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
        turns=turns,
    )

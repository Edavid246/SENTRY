"""Assistant endpoints (SPEC §8.2, §9.2, §10.1).

POST /api/v1/assistant/query maps HTTP onto `app.assistant.service.answer`,
which owns the authorization order, the pathways (knowledge, data, report),
labelling, conversation storage and the audit trail. This module only turns
requests into calls and outcomes into responses: Forbidden -> 403,
ConversationNotFound -> 404, ModelUnavailable -> 503.

Conversation reads (GET /conversations, GET /conversations/{id}) resolve the
caller's own threads only, as guarded reads (app.api.guard) over
app.assistant.conversations. Citations for a stored turn are resolved from its
inline citation markers through the chunk row filter
(app.knowledge.passages) — a passage that is no longer visible simply drops out.
"""

from __future__ import annotations

from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import ConnDep, CurrentContext, ModelsDep
from app.api.guard import guarded
from app.assistant import conversations
from app.assistant.conversations import Conversation, ConversationNotFound
from app.assistant.service import ModelUnavailable, answer
from app.authz.scope import Forbidden
from app.knowledge.answer import parse_cited_chunk_ids
from app.knowledge.passages import visible_passages

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
    except Forbidden:
        raise HTTPException(status_code=403, detail="forbidden") from None
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="not found") from None
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from exc
    table, report = outcome.table, outcome.report
    return AssistantQueryResponse(
        answer=outcome.answer,
        citations=[_citation(chunk) for chunk in outcome.citations],
        found=outcome.found,
        degraded=outcome.degraded,
        refused=outcome.refused,
        result_table=(ResultTable(columns=list(table.columns), rows=table.rows) if table else None),
        report=(
            ReportInfo(
                classification_code=report.label.code,
                compartments=list(report.label.compartments),
                record_ids=list(report.record_ids),
                document_refs=list(report.document_refs),
            )
            if report
            else None
        ),
        conversation_id=outcome.conversation_id,
        audit_event_id=outcome.audit_event_id,
    )


class _Cited(Protocol):
    chunk_id: str
    document_title: str
    document_ref: str
    page: int | None
    section: str | None
    classification_code: str


def _citation(chunk: _Cited) -> CitationOut:
    return CitationOut(
        chunk_id=chunk.chunk_id,
        document_title=chunk.document_title,
        document_ref=chunk.document_ref,
        page=chunk.page,
        section=chunk.section,
        classification_code=chunk.classification_code,
    )


def _summary(conversation: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        classification_code=conversation.classification_code,
        compartments=list(conversation.compartments),
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    ctx: CurrentContext,
    conn: ConnDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConversationSummary]:
    """The caller's own conversations, newest first (SPEC §10.1)."""
    with guarded(ctx, conn, "read", "conversation") as scope:
        found = conversations.list_conversations(scope, limit=limit)
        scope.read("conversation", len(found))
    return [_summary(conversation) for conversation in found]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: UUID, ctx: CurrentContext, conn: ConnDep
) -> ConversationDetail:
    """One of the caller's conversations with its turns and resolved citations.

    A conversation owned by anyone else — or one the caller's action is not
    allowed to read — answers 404, exactly like the POST that appends to it,
    so an id can never be probed for existence.
    """
    with guarded(ctx, conn, "read", "conversation", on_deny="not_found") as scope:
        found = conversations.list_conversations(scope, limit=1, conversation_id=conversation_id)
        if not found:
            scope.read("conversation", 0)
            raise HTTPException(status_code=404, detail="not found")
        messages = conversations.list_messages(scope, conversation_id)
        scope.read("message", len(messages))
        cited = [
            parse_cited_chunk_ids(message.content) if message.role == "assistant" else []
            for message in messages
        ]
        passages = visible_passages(scope, list(dict.fromkeys(i for ids in cited for i in ids)))

    turns = [
        TurnOut(
            role=message.role,
            content=message.content,
            created_at=message.created_at.isoformat(),
            citations=[_citation(passages[i]) for i in chunk_ids if i in passages],
        )
        for message, chunk_ids in zip(messages, cited, strict=True)
    ]
    return ConversationDetail(**_summary(found[0]).model_dump(), turns=turns)

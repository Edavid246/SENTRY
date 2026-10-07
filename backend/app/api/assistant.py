"""Assistant endpoint (SPEC §8.2, §9.2): POST /api/v1/assistant/query.

Authorization order is fixed and identical to the other data endpoints:
LocalPolicy.decide first (may this user ask at all?), then set_rls_context +
the policy row filter inside the retrieval SQL (which chunks?). Only the
authorized chunks reach the model, so content inside a document (including a
prompt-injection attempt) can never change access — access was decided before
the model ran (SPEC §8.3, Principle Zero).

Audit (SPEC §14): a decide event, a retrieval event carrying the authorized
row count and chunk ids, an optional notable event for a manipulation-style
question (SPEC §8.3), and an answer event with citation ids and gateway
provenance; the answer event id is returned. Conversation turns are stored
per user; a conversation id owned by another user answers 404. Derived
conversation content inherits the highest classification and union of
compartments of its input chunks (AGENTS.md).
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.ai_gateway.base import ChatMessage
from app.api.deps import ConnDep, CurrentContext, audit_events
from app.audit.chain import utc_now_iso
from app.authz.context import AccessContext
from app.authz.policy import Decision, LocalPolicy
from app.db import set_rls_context
from app.knowledge.answer import CitedAnswer, generate_answer
from app.knowledge.retrieve import RetrievedChunk, retrieve_chunks

POLICY = LocalPolicy()
router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

MAX_QUESTION_CHARS = 2000
HISTORY_TURNS = 6
AUDIT_TEXT_LIMIT = 300

# SPEC §8.3: requests to ignore permissions, reveal restricted sources or act
# as another user have no effect on retrieval and are logged as notable events.
_MANIPULATION_PATTERNS = (
    r"ignore (all |your |the )?(previous |prior )?(instructions?|permissions?)",
    r"disregard (the |all )?(classification|restriction|permission)",
    r"reveal (the |all )?(secret|restricted|classified)",
    r"show me (the |all )?(secret|restricted|classified)",
    r"act as (a |another |the )?(user|admin|commander)",
    r"pretend (you are|to be)",
    r"bypass (the |all )?(rule|restriction|permission|control)",
    r"system notice",
    r"you are now",
)
_MANIPULATION_RE = re.compile("|".join(_MANIPULATION_PATTERNS), re.IGNORECASE)


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


class AssistantQueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    conversation_id: str
    audit_event_id: str


def _decide_event(ctx: AccessContext, decision: Decision) -> dict[str, object]:
    payload: dict[str, object] = {
        "actor": ctx.username,
        "action": "decide",
        "resource": "assistant",
        "requested": "answer",
        "decision": "allow" if decision.allowed else "deny",
        "timestamp": utc_now_iso(),
    }
    if not decision.allowed:
        payload["reasons"] = list(decision.reasons)
    return payload


def _retrieval_event(ctx: AccessContext, question: str, chunks: list[RetrievedChunk]) -> dict:
    return {
        "actor": ctx.username,
        "action": "retrieve",
        "resource": "chunk",
        "decision": "allow",
        "question": question[:AUDIT_TEXT_LIMIT],
        "rows": len(chunks),
        "chunk_ids": [chunk.chunk_id for chunk in chunks],
        "timestamp": utc_now_iso(),
    }


def _notable_event(ctx: AccessContext, question: str) -> dict:
    return {
        "actor": ctx.username,
        "action": "notable",
        "resource": "assistant",
        "decision": "deny",
        "reasons": ["manipulation-style request; access unchanged"],
        "question": question[:AUDIT_TEXT_LIMIT],
        "timestamp": utc_now_iso(),
    }


def _answer_event(
    ctx: AccessContext, question: str, conversation_id: str, cited: CitedAnswer
) -> dict:
    return {
        "actor": ctx.username,
        "action": "answer",
        "resource": "assistant",
        "decision": "deny" if cited.blocked else "allow",
        "conversation_id": conversation_id,
        "question": question[:AUDIT_TEXT_LIMIT],
        "found": cited.found,
        "blocked": cited.blocked,
        "citations": [chunk.chunk_id for chunk in cited.citations],
        "provider": cited.provider,
        "model": cited.model,
        "cached": cited.cached,
        "timestamp": utc_now_iso(),
    }


def _rank_map(conn) -> dict[str, int]:
    rows = conn.execute(text("SELECT code, rank FROM classification_levels")).all()
    return {str(row.code): int(row.rank) for row in rows}


def _derived_classification(chunks: list[RetrievedChunk], ranks: dict[str, int]) -> str:
    if not chunks:
        return "unclassified"
    return max(
        (chunk.classification_code for chunk in chunks),
        key=lambda code: ranks.get(code, 0),
    )


def _derived_compartments(chunks: list[RetrievedChunk]) -> list[str]:
    merged: set[str] = set()
    for chunk in chunks:
        merged.update(chunk.compartments)
    return sorted(merged)


def _resolve_conversation(conn, ctx: AccessContext, requested: UUID) -> str:
    row = conn.execute(
        text("SELECT id FROM conversations WHERE id = :id AND user_id = :user_id"),
        {"id": requested, "user_id": ctx.user_id},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return str(row.id)


def _load_history(conn, conversation_id: UUID) -> tuple[ChatMessage, ...]:
    rows = conn.execute(
        text(
            "SELECT role, content FROM messages"
            " WHERE conversation_id = :id"
            " ORDER BY created_at DESC, id DESC LIMIT :limit"
        ),
        {"id": conversation_id, "limit": HISTORY_TURNS},
    ).all()
    return tuple(ChatMessage(role=str(row.role), text=str(row.content)) for row in reversed(rows))


def _store_turn(
    conn,
    ctx: AccessContext,
    conversation_id: UUID,
    question: str,
    answer: str,
    chunks: list[RetrievedChunk],
    ranks: dict[str, int],
    *,
    new_conversation: bool,
) -> None:
    classification = _derived_classification(chunks, ranks)
    compartments = _derived_compartments(chunks)
    common = {
        "classification": classification,
        "compartments": compartments,
        "unit_id": ctx.unit_id,
    }
    if new_conversation:
        conn.execute(
            text(
                "INSERT INTO conversations"
                " (id, user_id, title, classification_code, compartments, unit_id)"
                " VALUES (:id, :user_id, :title, :classification, :compartments, :unit_id)"
            ),
            {"id": conversation_id, "user_id": ctx.user_id, "title": question[:120], **common},
        )
    conn.execute(
        text(
            "INSERT INTO messages"
            " (id, conversation_id, role, content, classification_code, compartments, unit_id)"
            " VALUES (:id, :conversation_id, :role, :content, :classification, :compartments,"
            " :unit_id)"
        ),
        [
            {
                "id": uuid4(),
                "conversation_id": conversation_id,
                "role": "user",
                "content": question,
                **common,
            },
            {
                "id": uuid4(),
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": answer,
                **common,
            },
        ],
    )


@router.post("/query", response_model=AssistantQueryResponse)
def query_assistant(
    body: AssistantQueryRequest,
    ctx: CurrentContext,
    conn: ConnDep,
) -> AssistantQueryResponse:
    decision = POLICY.decide(ctx, "answer", "assistant")
    if not decision.allowed:
        audit_events([_decide_event(ctx, decision)])
        raise HTTPException(status_code=403, detail="forbidden")

    set_rls_context(
        conn,
        user_id=ctx.user_id,
        clearance_rank=ctx.clearance_rank,
        compartments=ctx.compartments,
        unit_path=ctx.unit_path,
        data_scope=ctx.data_scope,
        session_id=ctx.session_id,
    )
    new_conversation = body.conversation_id is None
    if new_conversation:
        conversation_id = uuid4()
        history = ()
    else:
        conversation_id = body.conversation_id
        _resolve_conversation(conn, ctx, conversation_id)
        history = _load_history(conn, conversation_id)

    chunks = retrieve_chunks(conn, ctx, body.question)
    cited = generate_answer(body.question, chunks, history=history)
    ranks = _rank_map(conn)
    _store_turn(
        conn,
        ctx,
        conversation_id,
        body.question,
        cited.answer,
        chunks,
        ranks,
        new_conversation=new_conversation,
    )
    conn.commit()

    events: list[dict] = [
        _decide_event(ctx, decision),
        _retrieval_event(ctx, body.question, chunks),
    ]
    if _MANIPULATION_RE.search(body.question):
        events.append(_notable_event(ctx, body.question))
    events.append(_answer_event(ctx, body.question, str(conversation_id), cited))
    written = audit_events(events)

    return AssistantQueryResponse(
        answer=cited.answer,
        citations=[
            CitationOut(
                chunk_id=chunk.chunk_id,
                document_title=chunk.document_title,
                document_ref=chunk.document_ref,
                page=chunk.page,
                section=chunk.section,
                classification_code=chunk.classification_code,
            )
            for chunk in cited.citations
        ],
        conversation_id=str(conversation_id),
        audit_event_id=str(written[-1]["event_id"]),
    )

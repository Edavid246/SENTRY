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
per user; a conversation id owned by another user answers 404, on the read
routes as well as the write. Derived conversation content inherits the
highest classification and union of compartments of its input chunks
(AGENTS.md).

Conversation reads (GET /conversations, GET /conversations/{id}) resolve the
caller's own threads only, under the same decide + row filter + RLS order,
and are audited like every other read. Citations for a stored turn are
resolved from its inline citation markers, chunk by chunk, through the chunk
row filter — a passage that is no longer visible simply drops out.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Annotated, Any, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.ai_gateway.base import ChatMessage, ProviderError, ProviderNotConfiguredError
from app.api.deps import ConnDep, CurrentContext, audit_events
from app.audit.chain import utc_now_iso
from app.authz.context import AccessContext
from app.authz.policy import Decision, LocalPolicy
from app.data_queries.explain import explain_result
from app.data_queries.registry import ToolOutcome, execute_tool
from app.data_queries.routing import RoutedReport, RoutedTool, route_question, route_report
from app.db import format_array, set_rls_context
from app.knowledge.answer import CitedAnswer, generate_answer, parse_cited_chunk_ids
from app.knowledge.retrieve import (
    RetrievedChunk,
    embed_question,
    is_fts_only,
    retrieve_chunks,
)
from app.reporting.training import DOCUMENT_QUERY, DraftReport, generate_training_report

POLICY = LocalPolicy()
router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

MAX_QUESTION_CHARS = 2000
HISTORY_TURNS = 6
AUDIT_TEXT_LIMIT = 300

# SPEC §8.3: requests to ignore permissions, reveal restricted sources or act
# as another user have no effect on retrieval and are logged as notable events.
_MANIPULATION_PATTERNS = (
    r"ignore (all |your |my |the )?(previous |prior )?(instructions?|permissions?)",
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


def _decide_event(
    ctx: AccessContext,
    decision: Decision,
    *,
    resource: str = "assistant",
    requested: str = "answer",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "actor": ctx.username,
        "action": "decide",
        "resource": resource,
        "requested": requested,
        "decision": "allow" if decision.allowed else "deny",
        "timestamp": utc_now_iso(),
    }
    if not decision.allowed:
        payload["reasons"] = list(decision.reasons)
    return payload


def _query_event(ctx: AccessContext, resource: str, rows: int) -> dict[str, object]:
    return {
        "actor": ctx.username,
        "action": "query",
        "resource": resource,
        "decision": "allow",
        "rows": int(rows),
        "timestamp": utc_now_iso(),
    }


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
    ctx: AccessContext, question: str, conversation_id: str, cited: CitedAnswer, degraded: bool
) -> dict:
    return {
        "actor": ctx.username,
        "action": "answer",
        "resource": "assistant",
        "decision": "deny" if cited.blocked else "allow",
        "conversation_id": conversation_id,
        "question": question[:AUDIT_TEXT_LIMIT],
        "found": cited.found,
        "degraded": degraded,
        "blocked": cited.blocked,
        "citations": [chunk.chunk_id for chunk in cited.citations],
        "provider": cited.provider,
        "model": cited.model,
        "cached": cited.cached,
        "timestamp": utc_now_iso(),
    }


def _data_answer_event(
    ctx: AccessContext,
    question: str,
    conversation_id: str,
    outcome: ToolOutcome,
    *,
    provider: str,
    model: str,
    cached: bool,
) -> dict:
    return {
        "actor": ctx.username,
        "action": "answer",
        "resource": "assistant",
        "pathway": "data",
        "decision": "deny" if outcome.refused else "allow",
        "conversation_id": conversation_id,
        "question": question[:AUDIT_TEXT_LIMIT],
        "tool": outcome.tool[:64],
        "found": bool(outcome.result and outcome.result.rows),
        "refused": outcome.refused,
        "rows": len(outcome.result.rows) if outcome.result else 0,
        "provider": provider,
        "model": model,
        "cached": cached,
        "timestamp": utc_now_iso(),
    }


def _report_answer_event(
    ctx: AccessContext,
    question: str,
    conversation_id: str,
    report: DraftReport | None,
    tool_result: ToolOutcome,
    chunk_ids: list[str],
) -> dict:
    return {
        "actor": ctx.username,
        "action": "answer",
        "resource": "assistant",
        "pathway": "report",
        "decision": "deny" if (report is None or report.blocked) else "allow",
        "conversation_id": conversation_id,
        "question": question[:AUDIT_TEXT_LIMIT],
        "tool": tool_result.tool[:64],
        "record_ids": list(report.record_ids) if report else [],
        "chunk_ids": chunk_ids,
        "citations": [c.chunk_id for c in report.citations] if report else [],
        "classification": report.classification_code if report else None,
        "compartments": list(report.compartments) if report else [],
        "found": bool(report and report.found),
        "blocked": bool(report and report.blocked),
        "provider": report.provider if report else "",
        "model": report.model if report else "",
        "cached": bool(report and report.cached),
        "timestamp": utc_now_iso(),
    }


def _set_context(conn, ctx: AccessContext) -> None:
    set_rls_context(
        conn,
        user_id=ctx.user_id,
        clearance_rank=ctx.clearance_rank,
        compartments=ctx.compartments,
        unit_path=ctx.unit_path,
        data_scope=ctx.data_scope,
        session_id=ctx.session_id,
    )


def _rank_map(conn) -> dict[str, int]:
    rows = conn.execute(text("SELECT code, rank FROM classification_levels")).all()
    return {str(row.code): int(row.rank) for row in rows}


class _Labelled(Protocol):
    """Anything that carries a classification and compartments (chunks, records)."""

    classification_code: str
    compartments: Any


def _derived_classification(chunks: Sequence[_Labelled], ranks: dict[str, int]) -> str:
    if not chunks:
        return "unclassified"
    return max(
        (chunk.classification_code for chunk in chunks),
        key=lambda code: ranks.get(code, 0),
    )


def _derived_compartments(chunks: Sequence[_Labelled]) -> list[str]:
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
    chunks: Sequence[_Labelled],
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


def _query_data(
    body: AssistantQueryRequest,
    ctx: AccessContext,
    conn,
    answer_decision: Decision,
    routed: RoutedTool,
) -> AssistantQueryResponse:
    """Data pathway (SPEC 8.2): typed tool -> authorized adapter query -> explanation.

    The tool and the adapter run under the caller's row filter + RLS before the
    model sees anything; the model only explains rows already returned, and the
    table in the response is the deterministic tool output.
    """
    record_decision = POLICY.decide(ctx, "query", "record")
    decisions = [
        _decide_event(ctx, answer_decision),
        _decide_event(ctx, record_decision, resource="record", requested="query"),
    ]
    if not record_decision.allowed:
        audit_events(decisions)
        raise HTTPException(status_code=403, detail="forbidden")

    new_conversation = body.conversation_id is None
    if new_conversation:
        conversation_id = uuid4()
    else:
        conversation_id = body.conversation_id
        _set_context(conn, ctx)
        _resolve_conversation(conn, ctx, conversation_id)

    audit_events(decisions)
    outcome = execute_tool(ctx, conn, routed.tool, routed.params)

    result = outcome.result
    provider = model = ""
    cached = False
    if result is None:
        answer = f"That request was refused: {outcome.refusal}. No data was retrieved."
    else:
        try:
            explanation = explain_result(body.question, result)
        except ProviderError as exc:
            # The tool ran and was audited; only the explanation is unavailable.
            if isinstance(exc, ProviderNotConfiguredError):
                detail = "the answer model is not configured on this server"
            else:
                detail = "the answer model is currently unavailable; retry later"
            raise HTTPException(status_code=503, detail=detail) from exc
        answer = explanation.text
        provider, model, cached = explanation.provider, explanation.model, explanation.cached

    # Derived turn inherits the highest classification and union of compartments
    # of the records behind it (AGENTS.md); a refusal retrieved nothing.
    _set_context(conn, ctx)
    _store_turn(
        conn,
        ctx,
        conversation_id,
        body.question,
        answer,
        result.records if result else (),
        _rank_map(conn),
        new_conversation=new_conversation,
    )
    conn.commit()
    written = audit_events(
        [
            _data_answer_event(
                ctx,
                body.question,
                str(conversation_id),
                outcome,
                provider=provider,
                model=model,
                cached=cached,
            )
        ]
    )
    return AssistantQueryResponse(
        answer=answer,
        citations=[],
        found=bool(result and result.rows),
        degraded=False,
        refused=outcome.refused,
        result_table=(
            ResultTable(columns=list(result.columns), rows=result.rows) if result else None
        ),
        conversation_id=str(conversation_id),
        audit_event_id=str(written[-1]["event_id"]),
    )


def _query_report(
    body: AssistantQueryRequest,
    ctx: AccessContext,
    conn,
    answer_decision: Decision,
    routed: RoutedReport,
) -> AssistantQueryResponse:
    """Reporting pathway (SPEC 8.2 "Draft report"): records + documents -> marked draft.

    Same order as the other pathways: decisions first, then the typed tool and the
    chunk retrieval each run under the caller's row filter + RLS; the model only drafts
    over what came back. The draft carries the highest classification and union of
    compartments of every input, and is stored, audited and returned as a DRAFT.
    """
    record_decision = POLICY.decide(ctx, "query", "record")
    decisions = [
        _decide_event(ctx, answer_decision),
        _decide_event(ctx, record_decision, resource="record", requested="query"),
    ]
    if not record_decision.allowed:
        audit_events(decisions)
        raise HTTPException(status_code=403, detail="forbidden")

    new_conversation = body.conversation_id is None
    if new_conversation:
        conversation_id = uuid4()
    else:
        conversation_id = body.conversation_id
        _set_context(conn, ctx)
        _resolve_conversation(conn, ctx, conversation_id)

    audit_events(decisions)
    outcome = execute_tool(ctx, conn, "training_activity", routed.params)
    result = outcome.result
    chunks: list[RetrievedChunk] = []
    report: DraftReport | None = None
    if result is None:
        answer = f"That request was refused: {outcome.refusal}. No data was retrieved."
    else:
        _set_context(conn, ctx)
        chunks = retrieve_chunks(conn, ctx, DOCUMENT_QUERY)
        ranks = _rank_map(conn)
        try:
            report = generate_training_report(body.question, result, chunks, ranks)
        except ProviderError as exc:
            audit_events([_retrieval_event(ctx, DOCUMENT_QUERY, chunks)])
            if isinstance(exc, ProviderNotConfiguredError):
                detail = "the answer model is not configured on this server"
            else:
                detail = "the answer model is currently unavailable; retry later"
            raise HTTPException(status_code=503, detail=detail) from exc
        answer = report.text

    _set_context(conn, ctx)
    inputs = [*(result.records if result else ()), *chunks]
    _store_turn(
        conn,
        ctx,
        conversation_id,
        body.question,
        answer,
        inputs,
        _rank_map(conn),
        new_conversation=new_conversation,
    )
    conn.commit()
    written = audit_events(
        [
            _retrieval_event(ctx, DOCUMENT_QUERY, chunks),
            _report_answer_event(
                ctx,
                body.question,
                str(conversation_id),
                report,
                outcome,
                [c.chunk_id for c in chunks],
            ),
        ]
    )
    return AssistantQueryResponse(
        answer=answer,
        citations=[
            CitationOut(
                chunk_id=c.chunk_id,
                document_title=c.document_title,
                document_ref=c.document_ref,
                page=c.page,
                section=c.section,
                classification_code=c.classification_code,
            )
            for c in (report.citations if report else ())
        ],
        found=bool(report and report.found),
        degraded=False,
        refused=outcome.refused or bool(report and report.blocked),
        result_table=(
            ResultTable(columns=list(result.columns), rows=result.rows) if result else None
        ),
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
        conversation_id=str(conversation_id),
        audit_event_id=str(written[-1]["event_id"]),
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

    manipulation = bool(_MANIPULATION_RE.search(body.question))
    # A manipulation-style request never reaches a data tool: it stays on the
    # knowledge pathway, where it is logged and changes nothing (SPEC 8.3).
    report_routed = None if manipulation else route_report(body.question)
    if report_routed is not None:
        return _query_report(body, ctx, conn, decision, report_routed)
    routed = None if manipulation else route_question(body.question)
    if routed is not None:
        return _query_data(body, ctx, conn, decision, routed)

    _set_context(conn, ctx)
    new_conversation = body.conversation_id is None
    if new_conversation:
        conversation_id = uuid4()
        history = ()
    else:
        conversation_id = body.conversation_id
        _resolve_conversation(conn, ctx, conversation_id)
        history = _load_history(conn, conversation_id)

    query_vector = embed_question(body.question)
    chunks = retrieve_chunks(conn, ctx, body.question, query_vector=query_vector)
    degraded = is_fts_only(query_vector, chunks)
    try:
        cited = generate_answer(body.question, chunks, history=history)
    except ProviderError as exc:
        # Retrieval already happened: audit the decision and retrieval, then fail cleanly.
        failed: list[dict] = [
            _decide_event(ctx, decision),
            _retrieval_event(ctx, body.question, chunks),
        ]
        if manipulation:
            failed.append(_notable_event(ctx, body.question))
        audit_events(failed)
        if isinstance(exc, ProviderNotConfiguredError):
            detail = "the answer model is not configured on this server"
        else:
            detail = "the answer model is currently unavailable; retry later"
        raise HTTPException(status_code=503, detail=detail) from exc
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
    if manipulation:
        events.append(_notable_event(ctx, body.question))
    events.append(_answer_event(ctx, body.question, str(conversation_id), cited, degraded))
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
        found=cited.found,
        degraded=degraded,
        refused=manipulation or cited.blocked,
        result_table=None,
        conversation_id=str(conversation_id),
        audit_event_id=str(written[-1]["event_id"]),
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
        audit_events([_decide_event(ctx, decision, resource="conversation", requested="read")])
        raise HTTPException(status_code=403, detail="forbidden")
    _set_context(conn, ctx)
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
            _decide_event(ctx, decision, resource="conversation", requested="read"),
            _query_event(ctx, "conversations", len(results)),
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
        audit_events([_decide_event(ctx, decision, resource="conversation", requested="read")])
        raise HTTPException(status_code=404, detail="not found")
    _set_context(conn, ctx)
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
                _decide_event(ctx, decision, resource="conversation", requested="read"),
                _query_event(ctx, "conversations", 0),
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
            _decide_event(ctx, decision, resource="conversation", requested="read"),
            _query_event(ctx, "messages", len(turns)),
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

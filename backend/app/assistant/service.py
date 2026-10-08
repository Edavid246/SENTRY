"""The assistant: one question in, one audited, labelled, stored answer out (SPEC 8.2, 9.2).

`answer()` owns everything the pathways have in common, in a fixed order:

  1. policy decisions (may this user ask at all, and may this pathway read its
     source?); a deny is audited and raised as AssistantForbidden;
  2. the caller's conversation is opened (someone else's id is
     ConversationNotFound), and the decisions are audited BEFORE anything is
     retrieved (Principle Zero: authorization before retrieval);
  3. the pathway runs: retrieval and typed tools under the caller's row
     filter + RLS, then the model through the ModelPort. Audit events the
     pathway produces on the way (retrieval, notable) go on a trail;
  4. a model failure flushes the trail (what was retrieved stays audited) and
     raises ModelUnavailable;
  5. the turn is stored under the label derived from the pathway's inputs
     (highest classification, union of compartments), committed, and the
     trail plus the answer event are audited; the answer event id is returned.

Pathways only say which source they read and what they produced:

  * knowledge: hybrid retrieval over chunks -> cited answer;
  * data: typed tool -> deterministic table + model explanation;
  * report: training_activity tool + training documents -> DRAFT report.

A manipulation-style question never reaches a data tool: it stays on the
knowledge pathway, where it is logged as a notable event and changes nothing
(SPEC 8.3).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.engine import Connection

from app.ai_gateway.base import ChatMessage, ProviderError, ProviderNotConfiguredError
from app.ai_gateway.port import ModelPort
from app.api.deps import audit_events, decide_event
from app.assistant.conversations import load_history, open_conversation, store_turn
from app.audit.chain import utc_now_iso
from app.authz.context import AccessContext
from app.authz.labels import Labelled, Labels
from app.authz.policy import Decision, LocalPolicy
from app.data_queries.explain import explain_result
from app.data_queries.registry import execute_tool
from app.data_queries.routing import RoutedReport, RoutedTool, route_question, route_report
from app.data_queries.tools import ToolResult
from app.db import set_rls_context_for
from app.knowledge.answer import generate_answer
from app.knowledge.retrieve import RetrievedChunk, is_fts_only, retrieve_chunks
from app.reporting.training import DOCUMENT_QUERY, DraftReport, generate_training_report

POLICY = LocalPolicy()
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


class AssistantForbidden(Exception):
    """A policy decision denied the question (already audited)."""


class ModelUnavailable(Exception):
    """The model could not answer; what ran before it is already audited."""

    def __init__(self, cause: ProviderError) -> None:
        if isinstance(cause, ProviderNotConfiguredError):
            detail = "the answer model is not configured on this server"
        else:
            detail = "the answer model is currently unavailable; retry later"
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class AnswerOutcome:
    answer: str
    citations: tuple[RetrievedChunk, ...]
    found: bool
    degraded: bool
    refused: bool
    table: ToolResult | None
    report: DraftReport | None
    conversation_id: str
    audit_event_id: str


@dataclass(slots=True)
class _Turn:
    """What the orchestrator hands a pathway."""

    ctx: AccessContext
    conn: Connection
    question: str
    models: ModelPort
    conversation_id: UUID
    new_conversation: bool
    trail: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Produced:
    """What a pathway hands back."""

    answer: str
    inputs: Sequence[Labelled]  # everything the answer was built from (for its label)
    answer_event: dict[str, Any]  # pathway-specific fields of the audit answer event
    citations: tuple[RetrievedChunk, ...] = ()
    found: bool = False
    degraded: bool = False
    refused: bool = False
    table: ToolResult | None = None
    report: DraftReport | None = None


class _Pathway(Protocol):
    sources: tuple[tuple[str, str], ...]  # (action, resource) decisions beyond "answer"

    def run(self, turn: _Turn) -> _Produced: ...


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


def _refusal_text(refusal: str | None) -> str:
    return f"That request was refused: {refusal}. No data was retrieved."


@dataclass(frozen=True, slots=True)
class _Knowledge:
    manipulation: bool
    sources: tuple[tuple[str, str], ...] = ()

    def run(self, turn: _Turn) -> _Produced:
        history: tuple[ChatMessage, ...] = ()
        if not turn.new_conversation:
            history = load_history(turn.conn, turn.ctx, turn.conversation_id)
        query_vector = turn.models.embed_query(turn.question)
        chunks = retrieve_chunks(turn.conn, turn.ctx, turn.question, query_vector=query_vector)
        degraded = is_fts_only(query_vector, chunks)
        turn.trail.append(_retrieval_event(turn.ctx, turn.question, chunks))
        if self.manipulation:
            turn.trail.append(_notable_event(turn.ctx, turn.question))
        cited = generate_answer(turn.question, chunks, gateway=turn.models, history=history)
        return _Produced(
            answer=cited.answer,
            inputs=chunks,
            citations=cited.citations,
            found=cited.found,
            degraded=degraded,
            refused=self.manipulation or cited.blocked,
            answer_event={
                "decision": "deny" if cited.blocked else "allow",
                "found": cited.found,
                "degraded": degraded,
                "blocked": cited.blocked,
                "citations": [chunk.chunk_id for chunk in cited.citations],
                "provider": cited.provider,
                "model": cited.model,
                "cached": cited.cached,
            },
        )


@dataclass(frozen=True, slots=True)
class _Data:
    """Typed tool -> authorized adapter query -> explanation of the rows returned."""

    routed: RoutedTool
    sources: tuple[tuple[str, str], ...] = (("query", "record"),)

    def run(self, turn: _Turn) -> _Produced:
        outcome = execute_tool(turn.ctx, turn.conn, self.routed.tool, self.routed.params)
        result = outcome.result
        provider = model = ""
        cached = False
        if result is None:
            answer = _refusal_text(outcome.refusal)
        else:
            explanation = explain_result(turn.question, result, gateway=turn.models)
            answer = explanation.text
            provider, model, cached = explanation.provider, explanation.model, explanation.cached
        return _Produced(
            answer=answer,
            inputs=result.records if result else (),
            found=bool(result and result.rows),
            refused=outcome.refused,
            table=result,
            answer_event={
                "pathway": "data",
                "decision": "deny" if outcome.refused else "allow",
                "tool": outcome.tool[:64],
                "found": bool(result and result.rows),
                "refused": outcome.refused,
                "rows": len(result.rows) if result else 0,
                "provider": provider,
                "model": model,
                "cached": cached,
            },
        )


@dataclass(frozen=True, slots=True)
class _Report:
    """Records + documents -> marked DRAFT carrying the derived label of every input."""

    routed: RoutedReport
    sources: tuple[tuple[str, str], ...] = (("query", "record"),)

    def run(self, turn: _Turn) -> _Produced:
        outcome = execute_tool(turn.ctx, turn.conn, "training_activity", self.routed.params)
        result = outcome.result
        chunks: list[RetrievedChunk] = []
        report: DraftReport | None = None
        if result is not None:
            query_vector = turn.models.embed_query(DOCUMENT_QUERY)
            chunks = retrieve_chunks(turn.conn, turn.ctx, DOCUMENT_QUERY, query_vector=query_vector)
        turn.trail.append(_retrieval_event(turn.ctx, DOCUMENT_QUERY, chunks))
        if result is None:
            answer = _refusal_text(outcome.refusal)
        else:
            report = generate_training_report(
                turn.question, result, chunks, Labels.load(turn.conn), gateway=turn.models
            )
            answer = report.text
        return _Produced(
            answer=answer,
            inputs=[*(result.records if result else ()), *chunks],
            citations=report.citations if report else (),
            found=bool(report and report.found),
            refused=outcome.refused or bool(report and report.blocked),
            table=result,
            report=report,
            answer_event={
                "pathway": "report",
                "decision": "deny" if (report is None or report.blocked) else "allow",
                "tool": outcome.tool[:64],
                "record_ids": list(report.record_ids) if report else [],
                "chunk_ids": [c.chunk_id for c in chunks],
                "citations": [c.chunk_id for c in report.citations] if report else [],
                "classification": report.classification_code if report else None,
                "compartments": list(report.compartments) if report else [],
                "found": bool(report and report.found),
                "blocked": bool(report and report.blocked),
                "provider": report.provider if report else "",
                "model": report.model if report else "",
                "cached": bool(report and report.cached),
            },
        )


def _choose(question: str) -> _Pathway:
    manipulation = bool(_MANIPULATION_RE.search(question))
    if not manipulation:
        if (report := route_report(question)) is not None:
            return _Report(report)
        if (routed := route_question(question)) is not None:
            return _Data(routed)
    return _Knowledge(manipulation)


def answer(
    ctx: AccessContext,
    conn: Connection,
    question: str,
    conversation_id: UUID | None,
    *,
    models: ModelPort,
) -> AnswerOutcome:
    """Answer one question for `ctx`; see the module docstring for the order."""
    pathway = _choose(question)
    decisions: list[tuple[Decision, str, str]] = [
        (POLICY.decide(ctx, "answer", "assistant"), "assistant", "answer")
    ]
    if decisions[0][0].allowed:
        decisions += [(POLICY.decide(ctx, a, r), r, a) for a, r in pathway.sources]
    decision_events = [
        decide_event(ctx, decision, resource=resource, requested=action)
        for decision, resource, action in decisions
    ]
    if not all(decision.allowed for decision, _, _ in decisions):
        audit_events(decision_events)
        raise AssistantForbidden

    conv_id, new_conversation = open_conversation(conn, ctx, conversation_id)
    audit_events(decision_events)

    set_rls_context_for(conn, ctx)
    turn = _Turn(ctx, conn, question, models, conv_id, new_conversation)
    try:
        produced = pathway.run(turn)
    except ProviderError as exc:
        audit_events(turn.trail)
        raise ModelUnavailable(exc) from exc

    label = Labels.load(conn).derive(produced.inputs, empty_ok=True)
    store_turn(
        conn, ctx, conv_id, question, produced.answer, label, new_conversation=new_conversation
    )
    conn.commit()
    answer_event = {
        "actor": ctx.username,
        "action": "answer",
        "resource": "assistant",
        **produced.answer_event,
        "conversation_id": str(conv_id),
        "question": question[:AUDIT_TEXT_LIMIT],
        "timestamp": utc_now_iso(),
    }
    written = audit_events([*turn.trail, answer_event])
    return AnswerOutcome(
        answer=produced.answer,
        citations=produced.citations,
        found=produced.found,
        degraded=produced.degraded,
        refused=produced.refused,
        table=produced.table,
        report=produced.report,
        conversation_id=str(conv_id),
        audit_event_id=str(written[-1]["event_id"]),
    )

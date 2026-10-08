"""The assistant: one question in, one audited, labelled, stored answer out (SPEC 8.2, 9.2).

`answer()` runs the one authorization sequence every read uses
(app.authz.scope.authorized), so its order is the same as every route's:

  1. policy decisions (may this user ask at all, and may this pathway read its
     source?); a deny is audited and raised as Forbidden before anything runs;
  2. the caller's conversation is opened (someone else's id is
     ConversationNotFound), on a connection scoped to the caller (RLS set);
  3. the pathway runs: retrieval and typed tools under the caller's row
     filter + RLS, then the model through the ModelPort. Everything it reads
     is recorded on the scope (retrieval, data_query, notable events);
  4. a model failure is raised as ModelUnavailable; what ran before it is
     still audited when the scope closes, and nothing is stored;
  5. the turn is stored under the label derived from the pathway's inputs
     (highest classification, union of compartments) and the answer event is
     recorded. The scope writes the whole audit batch, in order, and only then
     commits the turn. The answer event id is returned.

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
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.engine import Connection

from app.ai_gateway.base import ChatMessage, LLMResult, ProviderError, ProviderNotConfiguredError
from app.ai_gateway.port import ModelPort
from app.assistant.conversations import load_history, open_conversation, store_turn
from app.audit.events import AUDIT_TEXT_LIMIT, event
from app.authz.context import AccessContext
from app.authz.labels import Label, Labelled, Labels
from app.authz.scope import Requirement, Scope, authorized
from app.data_queries.explain import explain_result
from app.data_queries.registry import ToolOutcome, execute_tool
from app.data_queries.routing import RoutedTool, route_question, route_report
from app.data_queries.tools import ToolResult
from app.knowledge.answer import generate_answer
from app.knowledge.retrieve import RetrievedChunk, is_fts_only, retrieve_chunks
from app.reporting.training import DOCUMENT_QUERY, DraftReport, generate_training_report

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


@dataclass(frozen=True, slots=True)
class _Turn:
    """What the orchestrator hands a pathway."""

    scope: Scope
    question: str
    models: ModelPort
    conversation_id: UUID
    new_conversation: bool

    def label(self, inputs: Sequence[Labelled]) -> Label:
        """The derived label of everything the answer was built from."""
        return Labels.load(self.scope.conn).derive(inputs, empty_ok=True)

    def retrieve(self, query: str) -> tuple[list[RetrievedChunk], list[float] | None]:
        """Authorized chunks for `query`, recorded on the scope as a retrieve event."""
        query_vector = self.models.embed_query(query)
        chunks = retrieve_chunks(self.scope, query, query_vector=query_vector)
        self.scope.record(
            event(
                self.scope.ctx.username,
                "retrieve",
                "chunk",
                "allow",
                question=query[:AUDIT_TEXT_LIMIT],
                rows=len(chunks),
                chunk_ids=[chunk.chunk_id for chunk in chunks],
            )
        )
        return chunks, query_vector


@dataclass(frozen=True, slots=True)
class _Produced:
    """What a pathway hands back."""

    answer: str
    label: Label
    answer_event: dict[str, Any]  # pathway-specific fields of the audit answer event
    citations: tuple[RetrievedChunk, ...] = ()
    found: bool = False
    degraded: bool = False
    refused: bool = False
    table: ToolResult | None = None
    report: DraftReport | None = None


class _Pathway(Protocol):
    sources: tuple[Requirement, ...]  # (action, resource) decisions beyond "answer"

    def run(self, turn: _Turn) -> _Produced: ...


def _model_use(llm: LLMResult | None) -> dict[str, Any]:
    """The audit fields that say which model call (if any) produced an answer."""
    if llm is None:
        return {"provider": "", "model": "", "cached": False}
    return {"provider": llm.provider, "model": llm.model, "cached": llm.cached}


def _refused(turn: _Turn, pathway: str, outcome: ToolOutcome) -> _Produced:
    """A tool call refused before any SQL ran: nothing read, nothing for the model."""
    return _Produced(
        answer=f"That request was refused: {outcome.refusal}. No data was retrieved.",
        label=turn.label(()),
        refused=True,
        answer_event={
            "pathway": pathway,
            "decision": "deny",
            "tool": outcome.tool[:64],
            "found": False,
            "refused": True,
            "rows": 0,
            **_model_use(None),
        },
    )


@dataclass(frozen=True, slots=True)
class _Knowledge:
    manipulation: bool
    sources: tuple[Requirement, ...] = ()

    def run(self, turn: _Turn) -> _Produced:
        history: tuple[ChatMessage, ...] = ()
        if not turn.new_conversation:
            history = load_history(turn.scope, turn.conversation_id)
        chunks, query_vector = turn.retrieve(turn.question)
        degraded = is_fts_only(query_vector, chunks)
        if self.manipulation:
            turn.scope.record(
                event(
                    turn.scope.ctx.username,
                    "notable",
                    "assistant",
                    "deny",
                    reasons=["manipulation-style request; access unchanged"],
                    question=turn.question[:AUDIT_TEXT_LIMIT],
                )
            )
        cited = generate_answer(turn.question, chunks, gateway=turn.models, history=history)
        return _Produced(
            answer=cited.answer,
            label=turn.label(chunks),
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
                **_model_use(cited.llm),
            },
        )


@dataclass(frozen=True, slots=True)
class _Data:
    """Typed tool -> authorized adapter query -> explanation of the rows returned."""

    routed: RoutedTool
    sources: tuple[Requirement, ...] = (("query", "record"),)

    def run(self, turn: _Turn) -> _Produced:
        outcome = execute_tool(turn.scope, self.routed.tool, self.routed.params)
        result = outcome.result
        if result is None:
            return _refused(turn, "data", outcome)
        explanation = explain_result(turn.question, result, gateway=turn.models)
        return _Produced(
            answer=explanation.text,
            label=turn.label(result.records),
            found=bool(result.rows),
            table=result,
            answer_event={
                "pathway": "data",
                "decision": "allow",
                "tool": outcome.tool[:64],
                "found": bool(result.rows),
                "refused": False,
                "rows": len(result.rows),
                **_model_use(explanation.llm),
            },
        )


@dataclass(frozen=True, slots=True)
class _Report:
    """Records + documents -> marked DRAFT carrying the derived label of every input."""

    routed: RoutedTool
    sources: tuple[Requirement, ...] = (("query", "record"),)

    def run(self, turn: _Turn) -> _Produced:
        outcome = execute_tool(turn.scope, self.routed.tool, self.routed.params)
        result = outcome.result
        if result is None:
            return _refused(turn, "report", outcome)
        chunks, _ = turn.retrieve(DOCUMENT_QUERY)
        label = turn.label([*result.records, *chunks])
        report = generate_training_report(turn.question, result, chunks, label, gateway=turn.models)
        return _Produced(
            answer=report.text,
            label=label,
            citations=report.citations,
            found=report.found,
            refused=report.blocked,
            table=result,
            report=report,
            answer_event={
                "pathway": "report",
                "decision": "deny" if report.blocked else "allow",
                "tool": outcome.tool[:64],
                "record_ids": list(report.record_ids),
                "chunk_ids": [c.chunk_id for c in chunks],
                "citations": [c.chunk_id for c in report.citations],
                "classification": label.code,
                "compartments": list(label.compartments),
                "found": report.found,
                "blocked": report.blocked,
                **_model_use(report.llm),
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
    with authorized(ctx, conn, [("answer", "assistant"), *pathway.sources]) as scope:
        conv_id, new_conversation = open_conversation(scope, conversation_id)
        turn = _Turn(scope, question, models, conv_id, new_conversation)
        try:
            produced = pathway.run(turn)
        except ProviderError as exc:
            raise ModelUnavailable(exc) from exc
        store_turn(
            scope,
            conv_id,
            question,
            produced.answer,
            produced.label,
            new_conversation=new_conversation,
        )
        scope.record(
            event(
                ctx.username,
                "answer",
                "assistant",
                **produced.answer_event,
                conversation_id=str(conv_id),
                question=question[:AUDIT_TEXT_LIMIT],
            )
        )
    return AnswerOutcome(
        answer=produced.answer,
        citations=produced.citations,
        found=produced.found,
        degraded=produced.degraded,
        refused=produced.refused,
        table=produced.table,
        report=produced.report,
        conversation_id=str(conv_id),
        audit_event_id=str(scope.written[-1]["event_id"]),
    )

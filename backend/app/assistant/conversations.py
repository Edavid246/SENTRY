"""Conversation storage for the assistant (SPEC 10.1).

Conversations are per user: an id owned by anyone else is reported as
missing, never as forbidden, so ids cannot be probed. Every stored turn
carries the derived label it was given (highest classification and union of
compartments of its inputs, from `app.authz.labels`), and the conversation
carries the derived label of all its turns. Every function runs on
an authorized Scope (app.authz.scope), so none of them can run without the
caller's RLS context; the reads also put the policy row filter in the SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import text

from app.ai_gateway.base import ChatMessage
from app.authz.labels import Label, Labels
from app.authz.scope import Scope

HISTORY_TURNS = 6
TITLE_CHARS = 120


class ConversationNotFound(Exception):
    """The id does not name one of the caller's conversations."""


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    title: str
    classification_code: str
    compartments: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str
    created_at: datetime


def _conversation(row) -> Conversation:
    return Conversation(
        id=str(row["id"]),
        title=str(row["title"]),
        classification_code=str(row["classification_code"]),
        compartments=tuple(str(code) for code in (row["compartments"] or [])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_conversations(
    scope: Scope, *, limit: int, conversation_id: UUID | None = None
) -> list[Conversation]:
    """The caller's own conversations, newest first (or just the one named).

    The ownership predicate is part of the SQL, alongside the row filter and RLS.
    """
    row_filter = scope.filter("conversation")
    where = f"user_id = :user_id AND {row_filter.where_sql}"
    params = {"user_id": scope.ctx.user_id, "limit": limit, **row_filter.params}
    if conversation_id is not None:
        where += " AND id = :id"
        params["id"] = conversation_id
    rows = (
        scope.conn.execute(
            text(
                "SELECT id, title, classification_code, compartments, created_at, updated_at"
                f" FROM conversations WHERE {where}"
                " ORDER BY updated_at DESC, id DESC LIMIT :limit"
            ),
            params,
        )
        .mappings()
        .all()
    )
    return [_conversation(row) for row in rows]


def list_messages(scope: Scope, conversation_id: UUID) -> list[Message]:
    """A conversation's turns the caller may see, oldest first (question before answer)."""
    row_filter = scope.filter("message")
    rows = scope.conn.execute(
        text(
            "SELECT role, content, created_at FROM messages"
            f" WHERE conversation_id = :id AND {row_filter.where_sql}"
            " ORDER BY created_at, CASE role WHEN 'user' THEN 0 ELSE 1 END, id"
        ),
        {"id": conversation_id, **row_filter.params},
    ).all()
    return [Message(str(r.role), str(r.content), r.created_at) for r in rows]


def open_conversation(scope: Scope, requested: UUID | None) -> tuple[UUID, bool]:
    """(conversation id, is_new); an id owned by anyone else raises ConversationNotFound."""
    if requested is None:
        return uuid4(), True
    row = scope.conn.execute(
        text("SELECT id FROM conversations WHERE id = :id AND user_id = :user_id"),
        {"id": requested, "user_id": scope.ctx.user_id},
    ).first()
    if row is None:
        raise ConversationNotFound(str(requested))
    return requested, False


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    """An earlier turn sent back to the model, with the label it was stored under.

    It is an input to the next answer, so that answer's derived label includes it.
    """

    role: str
    text: str
    classification_code: str
    compartments: tuple[str, ...]

    def chat(self) -> ChatMessage:
        return ChatMessage(role=self.role, text=self.text)


def load_history(scope: Scope, conversation_id: UUID) -> tuple[HistoryMessage, ...]:
    """The last HISTORY_TURNS messages the caller may see, oldest first."""
    row_filter = scope.filter("message")
    rows = scope.conn.execute(
        text(
            "SELECT role, content, classification_code, compartments FROM messages"
            f" WHERE conversation_id = :id AND {row_filter.where_sql}"
            " ORDER BY created_at DESC, id DESC LIMIT :limit"
        ),
        {"id": conversation_id, "limit": HISTORY_TURNS, **row_filter.params},
    ).all()
    return tuple(
        HistoryMessage(
            role=str(row.role),
            text=str(row.content),
            classification_code=str(row.classification_code),
            compartments=tuple(str(code) for code in (row.compartments or [])),
        )
        for row in reversed(rows)
    )


@dataclass(frozen=True, slots=True)
class _Stored:
    classification_code: str
    compartments: tuple[str, ...]


def _raise_conversation_label(scope: Scope, conversation_id: UUID, turn: Label) -> None:
    """The conversation holds every turn, so it takes the derived label of all of them
    (its current label + this turn's) and moves to the top of the list."""
    row_filter = scope.filter("conversation")
    params = {"id": conversation_id, "user_id": scope.ctx.user_id, **row_filter.params}
    where = f"id = :id AND user_id = :user_id AND {row_filter.where_sql}"
    current = scope.conn.execute(
        text(f"SELECT classification_code, compartments FROM conversations WHERE {where}"),
        params,
    ).one()  # open_conversation already found it under the same filter + RLS
    label = Labels.load(scope.conn).derive(
        [
            _Stored(str(current.classification_code), tuple(current.compartments or ())),
            _Stored(turn.code, turn.compartments),
        ]
    )
    scope.conn.execute(
        text(
            "UPDATE conversations SET classification_code = :classification,"
            f" compartments = :new_compartments, updated_at = now() WHERE {where}"
            " RETURNING id"
        ),
        {**params, "classification": label.code, "new_compartments": list(label.compartments)},
    ).one()


def store_turn(
    scope: Scope,
    conversation_id: UUID,
    question: str,
    answer: str,
    label: Label,
    *,
    new_conversation: bool,
) -> None:
    """Store the question and answer under `label`; the scope commits after its audit."""
    ctx = scope.ctx
    common = {
        "classification": label.code,
        "compartments": list(label.compartments),
        "unit_id": ctx.unit_id,
    }
    if not new_conversation:
        _raise_conversation_label(scope, conversation_id, label)
    else:
        scope.conn.execute(
            text(
                "INSERT INTO conversations"
                " (id, user_id, title, classification_code, compartments, unit_id)"
                " VALUES (:id, :user_id, :title, :classification, :compartments, :unit_id)"
            ),
            {
                "id": conversation_id,
                "user_id": ctx.user_id,
                "title": question[:TITLE_CHARS],
                **common,
            },
        )
    scope.conn.execute(
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
                "role": role,
                "content": content,
                **common,
            }
            for role, content in (("user", question), ("assistant", answer))
        ],
    )
    scope.commit()

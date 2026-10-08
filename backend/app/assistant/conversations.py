"""Conversation storage for the assistant (SPEC 10.1).

Conversations are per user: an id owned by anyone else is reported as
missing, never as forbidden, so ids cannot be probed. Every stored turn
carries the derived label it was given (highest classification and union of
compartments of its inputs, from `app.authz.labels`). Each function sets the
caller's RLS context itself, so none of them can run without one.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.ai_gateway.base import ChatMessage
from app.authz.context import AccessContext
from app.authz.labels import Label
from app.db import set_rls_context_for

HISTORY_TURNS = 6


class ConversationNotFound(Exception):
    """The id does not name one of the caller's conversations."""


def open_conversation(
    conn: Connection, ctx: AccessContext, requested: UUID | None
) -> tuple[UUID, bool]:
    """(conversation id, is_new); an id owned by anyone else raises ConversationNotFound."""
    if requested is None:
        return uuid4(), True
    set_rls_context_for(conn, ctx)
    row = conn.execute(
        text("SELECT id FROM conversations WHERE id = :id AND user_id = :user_id"),
        {"id": requested, "user_id": ctx.user_id},
    ).first()
    if row is None:
        raise ConversationNotFound(str(requested))
    return requested, False


def load_history(
    conn: Connection, ctx: AccessContext, conversation_id: UUID
) -> tuple[ChatMessage, ...]:
    """The last HISTORY_TURNS messages, oldest first."""
    set_rls_context_for(conn, ctx)
    rows = conn.execute(
        text(
            "SELECT role, content FROM messages"
            " WHERE conversation_id = :id"
            " ORDER BY created_at DESC, id DESC LIMIT :limit"
        ),
        {"id": conversation_id, "limit": HISTORY_TURNS},
    ).all()
    return tuple(ChatMessage(role=str(row.role), text=str(row.content)) for row in reversed(rows))


def store_turn(
    conn: Connection,
    ctx: AccessContext,
    conversation_id: UUID,
    question: str,
    answer: str,
    label: Label,
    *,
    new_conversation: bool,
) -> None:
    """Store the question and answer under `label`; the caller commits."""
    set_rls_context_for(conn, ctx)
    common = {
        "classification": label.code,
        "compartments": list(label.compartments),
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
                "role": role,
                "content": content,
                **common,
            }
            for role, content in (("user", question), ("assistant", answer))
        ],
    )

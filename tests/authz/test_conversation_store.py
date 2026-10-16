"""Conversation storage reads put the policy row filter in the SQL, and history keeps turn order.

Runs on the table owner's connection, which bypasses RLS (as in test_filter_only.py), so
the filter in the query is the only thing that can hide a row. Everything is written inside
one transaction and rolled back.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.assistant.conversations import ConversationNotFound, load_history, open_conversation
from app.authz.scope import Scope
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from support.contexts import CONTEXTS, access_context

USERNAME = "coo"  # cleared to restricted


@pytest.fixture
def scope(owner_engine: Engine, seeded: None) -> Iterator[Scope]:
    with owner_engine.connect() as conn:
        transaction = conn.begin()
        try:
            user_id = conn.execute(
                text("SELECT id FROM users WHERE username = :u"), {"u": USERNAME}
            ).scalar_one()
            yield Scope(replace(access_context(USERNAME), user_id=user_id), conn)
        finally:
            transaction.rollback()


def _conversation(conn: Connection, user_id: UUID, classification: str) -> UUID:
    conversation_id = uuid4()
    conn.execute(
        text(
            "INSERT INTO conversations"
            " (id, user_id, title, classification_code, compartments, unit_id)"
            " SELECT :id, :user_id, 'probe', :classification, '{}', id FROM units"
            " WHERE path = :unit_path"
        ),
        {
            "id": conversation_id,
            "user_id": user_id,
            "classification": classification,
            "unit_path": CONTEXTS[USERNAME]["unit_path"],
        },
    )
    return conversation_id


def test_open_conversation_applies_the_row_filter_not_only_ownership(scope: Scope) -> None:
    """The caller owns both threads; only the one within their clearance can be opened."""
    within = _conversation(scope.conn, scope.ctx.user_id, "restricted")
    above = _conversation(scope.conn, scope.ctx.user_id, "secret")

    assert open_conversation(scope, within) == (within, False)
    with pytest.raises(ConversationNotFound):
        open_conversation(scope, above)


def test_history_puts_the_question_before_its_answer_when_they_share_a_timestamp(
    scope: Scope,
) -> None:
    """Both rows of a turn are written in one transaction, so created_at ties. The ids are
    chosen so that ordering by id alone would put the answer first."""
    conversation_id = _conversation(scope.conn, scope.ctx.user_id, "restricted")
    scope.conn.execute(
        text(
            "INSERT INTO messages"
            " (id, conversation_id, role, content, classification_code, compartments, unit_id)"
            " SELECT :id, c.id, :role, :content, 'restricted', '{}', c.unit_id"
            " FROM conversations c WHERE c.id = :conversation_id"
        ),
        [
            {
                "id": UUID(int=(1 << 128) - 1),
                "role": "user",
                "content": "question",
                "conversation_id": conversation_id,
            },
            {
                "id": UUID(int=0),
                "role": "assistant",
                "content": "answer",
                "conversation_id": conversation_id,
            },
        ],
    )

    history = load_history(scope, conversation_id)
    assert [(m.role, m.text) for m in history] == [("user", "question"), ("assistant", "answer")]

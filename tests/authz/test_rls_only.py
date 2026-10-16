"""RLS-only authorization layer: raw SQL as gateway_app, no application code.

For each demo user the test takes the hand-authored SPEC 7.4 access context
(tests/support/contexts.py — not read from the seeded users table, and no Policy
or filter module is involved; that arrives in step 5), sets it with
set_rls_context, and compares raw-SQL results against the independent
oracle in expected.py.

Three checks per user: visible document source_refs, visible record
source_refs, and the Q2 keyword chunk count.
"""

from uuid import NAMESPACE_URL, uuid5

import pytest
from app.db import set_rls_context
from authz.expected import GOLD_DOCUMENTS, GOLD_KEYWORD_CHUNK_COUNTS, GOLD_RECORDS, KEYWORD
from sqlalchemy import text
from sqlalchemy.engine import Engine
from support.contexts import CONTEXTS, USERNAMES


def _context(username: str) -> dict:
    return {
        "user_id": uuid5(NAMESPACE_URL, f"test-user:{username}"),
        "session_id": f"rls-only:{username}",
        **CONTEXTS[username],
    }


def _visible_source_refs(app_engine: Engine, username: str, table: str) -> set[str]:
    with app_engine.connect() as conn:
        set_rls_context(conn, **_context(username))
        rows = conn.execute(text(f"SELECT source_ref FROM {table}")).scalars()
        return set(rows)


@pytest.mark.parametrize("username", USERNAMES)
def test_gold_document_visibility(app_engine: Engine, seeded: None, username: str) -> None:
    visible = _visible_source_refs(app_engine, username, "documents")
    assert visible == GOLD_DOCUMENTS[username]


@pytest.mark.parametrize("username", USERNAMES)
def test_gold_record_visibility(app_engine: Engine, seeded: None, username: str) -> None:
    visible = _visible_source_refs(app_engine, username, "canonical_records")
    assert visible == GOLD_RECORDS[username]


@pytest.mark.parametrize("username", USERNAMES)
def test_gold_keyword_chunk_count(app_engine: Engine, seeded: None, username: str) -> None:
    with app_engine.connect() as conn:
        set_rls_context(conn, **_context(username))
        count = conn.execute(
            text("SELECT count(*) FROM chunks WHERE text ILIKE :pattern"),
            {"pattern": f"%{KEYWORD}%"},
        ).scalar()
    assert count == GOLD_KEYWORD_CHUNK_COUNTS[username]

"""Cross-check: layer 2 (RLS only, gateway_app) must equal layer 3 (policy filter only, owner).

If the pure-Python row filter and the SQL row-level-security policies ever
disagree about visibility for any demo user, one of them is wrong — this is
the test that catches drift between the two independently-built encodings of
the SPEC 7.1 rule. A third comparison (both layers together) is what the
wired endpoints get in step 6.
"""

import pytest
from app.db import set_rls_context
from expected import KEYWORD
from sqlalchemy import text
from sqlalchemy.engine import Engine
from test_filter_only import filtered_keyword_count, filtered_source_refs
from test_rls_only import USERNAMES, _context, _visible_source_refs


def _rls_keyword_count(engine: Engine, username: str) -> int:
    with engine.connect() as conn:
        set_rls_context(conn, **_context(username))
        count = conn.execute(
            text("SELECT count(*) FROM chunks WHERE text ILIKE :pattern"),
            {"pattern": f"%{KEYWORD}%"},
        ).scalar()
    return int(count)


@pytest.mark.parametrize("username", USERNAMES)
def test_document_visibility_agrees(
    app_engine: Engine, owner_engine: Engine, seeded: None, username: str
) -> None:
    rls = _visible_source_refs(app_engine, username, "documents")
    policy = filtered_source_refs(owner_engine, username, "document")
    assert rls == policy


@pytest.mark.parametrize("username", USERNAMES)
def test_record_visibility_agrees(
    app_engine: Engine, owner_engine: Engine, seeded: None, username: str
) -> None:
    rls = _visible_source_refs(app_engine, username, "canonical_records")
    policy = filtered_source_refs(owner_engine, username, "record")
    assert rls == policy


@pytest.mark.parametrize("username", USERNAMES)
def test_keyword_count_agrees(
    app_engine: Engine, owner_engine: Engine, seeded: None, username: str
) -> None:
    assert _rls_keyword_count(app_engine, username) == filtered_keyword_count(
        owner_engine, username
    )

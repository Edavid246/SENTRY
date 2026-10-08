"""Permission-aware retrieval: the authorization filter runs inside the query.

The adversarial cases matter more than the happy path: a restricted user one
level below Brigade 2 must never receive the Confidential Brigade 2 policy or
the Restricted logistics SOP, even though both are highly relevant to the
query — relevance never overrides authorization (Principle Zero)."""

from __future__ import annotations

from app.authz.context import AccessContext, permissions_for_role
from app.db import set_rls_context
from app.knowledge.retrieve import retrieve_chunks
from app.seed import _id
from sqlalchemy import text
from sqlalchemy.engine import Engine

# (role, unit_path, clearance_rank, compartments)
USERS = {
    "a.bello": ("commander", "/command-a/", 3, ("UAS-OPS", "FORENSICS")),
    "t.adeyemi": ("training", "/command-a/bde-2/bn-4/", 1, ()),
}


def _context(username: str) -> AccessContext:
    role, unit_path, rank, compartments = USERS[username]
    return AccessContext(
        user_id=_id(f"user:{username}"),
        username=username,
        display_name=username,
        role=role,
        unit_id=_id(f"unit:{unit_path}"),
        unit_path=unit_path,
        clearance_code=None,
        clearance_rank=rank,
        compartments=frozenset(compartments),
        data_scope="standard",
        permissions=permissions_for_role(role),
        session_id=f"retrieve:{username}",
        token_id="test",
        auth_method="dev",
    )


def _refs(engine: Engine, username: str, question: str) -> list[str]:
    ctx = _context(username)
    with engine.connect() as conn:
        set_rls_context(
            conn,
            user_id=ctx.user_id,
            clearance_rank=ctx.clearance_rank,
            compartments=list(ctx.compartments),
            unit_path=ctx.unit_path,
            data_scope=ctx.data_scope,
            session_id=ctx.session_id,
        )
        return [
            chunk.document_ref for chunk in retrieve_chunks(conn, ctx, question, query_vector=None)
        ]


def test_relevant_policy_is_retrieved_for_commander(
    app_engine: Engine, ingested: dict[str, int]
) -> None:
    refs = _refs(app_engine, "a.bello", "maintenance")
    assert "DOC-201" in refs


def test_logistics_question_retrieves_the_sop(app_engine: Engine, ingested: dict[str, int]) -> None:
    refs = _refs(app_engine, "a.bello", "stock depot reorder")
    assert "DOC-203" in refs


def test_restricted_user_cannot_retrieve_higher_classified_parent_unit_docs(
    app_engine: Engine, ingested: dict[str, int]
) -> None:
    """Adeyemi (Restricted, Battalion 4) is a highly relevant searcher, but the
    Confidential Brigade 2 policy (DOC-201) and the Restricted Brigade 2 SOP
    (DOC-203) are above/outside her scope and must not appear."""
    refs = _refs(app_engine, "t.adeyemi", "servicing maintenance")
    assert "DOC-201" not in refs
    assert "DOC-203" not in refs
    # Her own unit's documents remain reachable.
    assert "DOC-204" in refs


def test_retrieval_sets_the_rls_context_itself(
    app_engine: Engine, ingested: dict[str, int]
) -> None:
    """A fresh connection with no context set: retrieval scopes it to the caller,
    so it cannot be run unscoped and returns exactly the caller's chunks."""
    ctx = _context("t.adeyemi")
    with app_engine.connect() as conn:
        fresh = [c.document_ref for c in retrieve_chunks(conn, ctx, "servicing", query_vector=None)]
    assert fresh == _refs(app_engine, "t.adeyemi", "servicing")


def test_no_rls_context_reads_no_chunks(app_engine: Engine, ingested: dict[str, int]) -> None:
    """The database layer on its own: without an access context RLS returns nothing."""
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM chunks")).scalar_one() == 0

"""Permission-aware retrieval: the authorization filter runs inside the query.

The adversarial cases matter more than the happy path: a restricted user one
level below EIB Stratoc must never receive the Confidential EIB Stratoc policy or
the Restricted logistics SOP, even though both are highly relevant to the
query — relevance never overrides authorization (Principle Zero)."""

from __future__ import annotations

from app.authz.context import AccessContext, permissions_for_role
from app.authz.scope import Scope
from app.db import clear_rls_context
from app.ids import entity_id as _id
from app.knowledge.retrieve import retrieve_chunks
from sqlalchemy import text
from sqlalchemy.engine import Engine

# (role, unit_path, clearance_rank, compartments)
USERS = {
    "owner": ("commander", "/eib-group/", 3, ("UAS-OPS", "FORENSICS")),
    "coo": ("training", "/eib-group/stratoc/site-4/", 1, ()),
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
        scope = Scope(ctx, conn)
        return [chunk.document_ref for chunk in retrieve_chunks(scope, question, query_vector=None)]


def test_relevant_policy_is_retrieved_for_commander(
    app_engine: Engine, ingested: dict[str, int]
) -> None:
    refs = _refs(app_engine, "owner", "maintenance")
    assert "DOC-201" in refs


def test_logistics_question_retrieves_the_sop(app_engine: Engine, ingested: dict[str, int]) -> None:
    refs = _refs(app_engine, "owner", "stock depot reorder")
    assert "DOC-203" in refs


def test_restricted_user_cannot_retrieve_higher_classified_parent_unit_docs(
    app_engine: Engine, ingested: dict[str, int]
) -> None:
    """COO (Restricted, Stratoc Site Team 4) is a highly relevant searcher, but the
    Confidential EIB Stratoc policy (DOC-201) and the Restricted EIB Stratoc SOP
    (DOC-203) are above/outside her scope and must not appear."""
    refs = _refs(app_engine, "coo", "servicing maintenance")
    assert "DOC-201" not in refs
    assert "DOC-203" not in refs
    # Her own unit's documents remain reachable.
    assert "DOC-204" in refs


def test_retrieval_needs_the_scopes_rls_context_as_well_as_its_filter(
    app_engine: Engine, ingested: dict[str, int]
) -> None:
    """The row filter alone is not enough: with the scope's RLS context cleared,
    the database itself returns nothing, so both layers always apply together."""
    ctx = _context("owner")
    with app_engine.connect() as conn:
        scope = Scope(ctx, conn)
        assert retrieve_chunks(scope, "maintenance", query_vector=None)
        clear_rls_context(conn)
        assert retrieve_chunks(scope, "maintenance", query_vector=None) == []


def test_no_rls_context_reads_no_chunks(app_engine: Engine, ingested: dict[str, int]) -> None:
    """The database layer on its own: without an access context RLS returns nothing."""
    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM chunks")).scalar_one() == 0

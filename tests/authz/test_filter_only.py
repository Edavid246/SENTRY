"""Policy-only authorization layer: LocalPolicy.row_filter executed as SQL, no RLS.

Layer 3 of 4. The parameterized WHERE from LocalPolicy.row_filter runs against
the table owner (gateway_owner bypasses RLS — no FORCE ROW LEVEL SECURITY), so
the application-level filter is the only thing deciding visibility here.
Contexts are the hand-authored SPEC 7.4 contexts from test_rls_only; roles and
clearance codes are small local dicts — no token, no endpoint, no seed reads.
Results are checked against the independent oracle in expected.py.
"""

from uuid import NAMESPACE_URL, uuid5

import pytest
from app.authz.context import AccessContext, permissions_for_role
from app.authz.policy import RESOURCE_TABLES, LocalPolicy
from expected import GOLD_DOCUMENTS, GOLD_KEYWORD_CHUNK_COUNTS, GOLD_RECORDS, KEYWORD
from sqlalchemy import text
from sqlalchemy.engine import Engine
from test_rls_only import CONTEXTS, USERNAMES

ROLES: dict[str, str] = {
    "owner": "commander",
    "logistics.head": "logistics",
    "coo": "training",
    "briech.lead": "uas_ops",
    "group.it": "sysadmin",
    "group.audit": "auditor",
}

CLEARANCE_CODES: dict[str, str | None] = {
    "owner": "secret",
    "logistics.head": "confidential",
    "coo": "restricted",
    "briech.lead": "confidential",
    "group.it": None,
    "group.audit": "restricted",
}

POLICY = LocalPolicy()


def access_context(username: str) -> AccessContext:
    """Build the SPEC 7.4 AccessContext by hand (independent of app.seed).

    unit_id is a deterministic placeholder: LocalPolicy.row_filter never
    reads it (the unit path is what the filter uses), so inventing one here
    keeps this layer free of database lookups.
    """
    hand = CONTEXTS[username]
    role = ROLES[username]
    return AccessContext(
        user_id=uuid5(NAMESPACE_URL, f"test-user:{username}"),
        username=username,
        display_name=username,
        role=role,
        unit_id=uuid5(NAMESPACE_URL, f"test-unit:{username}"),
        unit_path=hand["unit_path"],
        clearance_code=CLEARANCE_CODES[username],
        clearance_rank=hand["clearance_rank"],
        compartments=frozenset(hand["compartments"]),
        data_scope=hand["data_scope"],
        permissions=permissions_for_role(role),
        session_id=f"filter-only:{username}",
        token_id=f"filter-only:{username}",
        auth_method="test",
    )


def filtered_source_refs(engine: Engine, username: str, resource: str) -> set[str]:
    row_filter = POLICY.row_filter(access_context(username), resource)
    table = RESOURCE_TABLES[resource]
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT source_ref FROM {table} WHERE {row_filter.where_sql}"),
            row_filter.params,
        ).scalars()
    return set(rows)


def filtered_keyword_count(engine: Engine, username: str) -> int:
    row_filter = POLICY.row_filter(access_context(username), "chunk")
    with engine.connect() as conn:
        count = conn.execute(
            text(
                f"SELECT count(*) FROM chunks WHERE text ILIKE :pattern AND {row_filter.where_sql}"
            ),
            {"pattern": f"%{KEYWORD}%", **row_filter.params},
        ).scalar()
    return int(count)


@pytest.mark.parametrize("username", USERNAMES)
def test_policy_document_visibility(owner_engine: Engine, seeded: None, username: str) -> None:
    assert filtered_source_refs(owner_engine, username, "document") == GOLD_DOCUMENTS[username]


@pytest.mark.parametrize("username", USERNAMES)
def test_policy_record_visibility(owner_engine: Engine, seeded: None, username: str) -> None:
    assert filtered_source_refs(owner_engine, username, "record") == GOLD_RECORDS[username]


@pytest.mark.parametrize("username", USERNAMES)
def test_policy_keyword_chunk_count(owner_engine: Engine, seeded: None, username: str) -> None:
    assert filtered_keyword_count(owner_engine, username) == GOLD_KEYWORD_CHUNK_COUNTS[username]

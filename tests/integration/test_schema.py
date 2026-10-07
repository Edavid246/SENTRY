"""Schema tests: the step-3 migration's structure, RLS posture and grants.

Asserts the approved amendments directly against the live schema:
  * starts_with (never LIKE) and NULLIF guards inside every policy;
  * no index on chunks.embedding (exact search — docs/STUBS.md);
  * append-only grants on audit_events (SPEC 14.2);
  * a cleared pooled context yields zero rows on the real tables, not an error.
"""

from uuid import uuid4

import pytest
from app.db import clear_rls_context, set_rls_context
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError

EXPECTED_TABLES = {
    "alembic_version",
    "audit_events",
    "canonical_records",
    "chunks",
    "classification_levels",
    "compartments",
    "conversations",
    "documents",
    "messages",
    "source_systems",
    "units",
    "user_compartments",
    "users",
}

CLASSIFIED_TABLES = (
    "documents",
    "chunks",
    "canonical_records",
    "conversations",
    "messages",
    "findings",
)
# Tables the runtime role may add rows to (all with a SELECT policy); their
# UPDATE/DELETE stay denied so turns are append-only like the audit log.
APPEND_TABLES = ("conversations", "messages")
# Derived findings are upserted by the correlation job: INSERT and UPDATE, both gated by the
# same rule as WITH CHECK; never DELETE.
UPSERT_TABLES = ("findings",)


def test_migration_created_all_tables(owner_engine: Engine, migrated: None) -> None:
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
    assert set(rows) >= EXPECTED_TABLES


def test_rls_enabled_only_on_classified_tables(owner_engine: Engine, migrated: None) -> None:
    with owner_engine.connect() as conn:
        flags = dict(
            conn.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r'"
                )
            ).all()
        )
    for table in CLASSIFIED_TABLES:
        assert flags[table] is True, f"RLS not enabled on {table}"
    assert flags["users"] is False
    assert flags["units"] is False
    assert flags["audit_events"] is False


def test_policies_are_scoped_to_gateway_app_with_literal_rule(
    owner_engine: Engine, migrated: None
) -> None:
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename, policyname, qual, "
                "'gateway_app' = ANY(roles) AS applies_to_app "
                "FROM pg_policies WHERE schemaname = 'public'"
            )
        ).all()
    by_table: dict[str, dict[str, object]] = {}
    for row in rows:
        by_table.setdefault(row.tablename, {})[row.policyname] = row
    assert set(by_table) == set(CLASSIFIED_TABLES)
    for table in CLASSIFIED_TABLES:
        policies = by_table[table]
        # Every classified table has a gateway_app SELECT policy.
        select = policies[f"{table}_select"]
        assert select.applies_to_app is True, f"policy on {table} does not apply to gateway_app"
        # Approved amendments, locked in as assertions:
        assert "starts_with(" in select.qual
        assert "LIKE" not in select.qual.replace("ILIKE", "")
        assert "NULLIF(current_setting(" in select.qual
        for guc in ("app.data_scope", "app.clearance_rank", "app.compartments", "app.unit_path"):
            assert guc in select.qual
        # Only the append-only conversation tables admit INSERT (as WITH CHECK).
        if table in APPEND_TABLES + UPSERT_TABLES:
            assert f"{table}_insert" in policies
        else:
            assert not any(name.endswith("_insert") for name in policies)


def test_grants_are_read_only_plus_append_only_audit(owner_engine: Engine, migrated: None) -> None:
    with owner_engine.connect() as conn:

        def privileges(table: str, privilege: str) -> bool:
            return conn.execute(
                text("SELECT has_table_privilege('gateway_app', :t, :p)"),
                {"t": table, "p": privilege},
            ).scalar()

        for table in ("documents", "chunks", "canonical_records", "users", "units"):
            assert privileges(table, "SELECT") is True
            assert privileges(table, "UPDATE") is False
            assert privileges(table, "DELETE") is False
        assert privileges("audit_events", "INSERT") is True
        assert privileges("audit_events", "SELECT") is True
        assert privileges("audit_events", "UPDATE") is False
        assert privileges("audit_events", "DELETE") is False
        assert (
            conn.execute(
                text(
                    "SELECT has_sequence_privilege('gateway_app', 'audit_events_seq_seq', 'USAGE')"
                )
            ).scalar()
            is True
        )
        for table in APPEND_TABLES:
            assert (
                conn.execute(
                    text("SELECT has_table_privilege('gateway_app', :t, 'INSERT')"), {"t": table}
                ).scalar()
                is True
            )
            assert (
                conn.execute(
                    text("SELECT has_table_privilege('gateway_app', :t, 'UPDATE')"), {"t": table}
                ).scalar()
                is False
            )
            assert (
                conn.execute(
                    text("SELECT has_table_privilege('gateway_app', :t, 'DELETE')"), {"t": table}
                ).scalar()
                is False
            )


def test_findings_grants_allow_upsert_but_not_delete(owner_engine: Engine, migrated: None) -> None:
    with owner_engine.connect() as conn:
        for privilege, expected in (
            ("SELECT", True),
            ("INSERT", True),
            ("UPDATE", True),
            ("DELETE", False),
        ):
            assert (
                conn.execute(
                    text("SELECT has_table_privilege('gateway_app', 'findings', :p)"),
                    {"p": privilege},
                ).scalar()
                is expected
            ), privilege


def test_embedding_column_is_vector_without_index(owner_engine: Engine, migrated: None) -> None:
    with owner_engine.connect() as conn:
        col_type = conn.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE c.relname = 'chunks' AND a.attname = 'embedding'"
            )
        ).scalar()
        embedding_indexes = conn.execute(
            text(
                "SELECT count(*) FROM pg_indexes "
                "WHERE tablename = 'chunks' AND indexdef ILIKE '%embedding%'"
            )
        ).scalar()
    assert col_type == "vector(1024)"
    assert embedding_indexes == 0  # exact search — docs/STUBS.md (approved amendment)


def test_gateway_app_can_insert_into_audit_events(
    app_engine: Engine, owner_engine: Engine, migrated: None
) -> None:
    """End-to-end append-only proof: INSERT works (incl. sequence usage),
    UPDATE/DELETE hit permission denied. Owner removes the probe row."""
    try:
        with app_engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_events (event_id, payload, prev_hash, hash) "
                    "VALUES (:eid, '{}'::jsonb, :prev, 'probe')"
                ),
                {"eid": "test-schema-probe-event", "prev": "0" * 64},
            )
            conn.commit()
            for stmt in ("UPDATE audit_events SET hash = 'x'", "DELETE FROM audit_events"):
                with pytest.raises(ProgrammingError) as excinfo:
                    conn.execute(text(stmt))
                assert "permission denied" in str(excinfo.value).lower()
                conn.rollback()
    finally:
        with owner_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM audit_events WHERE event_id = :eid"),
                {"eid": "test-schema-probe-event"},
            )


def test_cleared_context_on_real_table_returns_zero_not_error(
    app_engine: Engine, seeded: None
) -> None:
    """The NULLIF guard against the real documents policy on a reused pooled
    connection: a set context sees rows, a cleared context sees zero rows —
    never a cast error."""
    with app_engine.connect() as conn:
        set_rls_context(
            conn,
            user_id=uuid4(),
            clearance_rank=3,
            compartments=["UAS-OPS", "FORENSICS"],
            unit_path="/command-a/",
            data_scope="standard",
            session_id="test-schema-session",
        )
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar() > 0
        conn.commit()
        clear_rls_context(conn)  # session-level '' on this pooled connection
        conn.commit()
        assert conn.execute(text("SELECT count(*) FROM documents")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM chunks")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM canonical_records")).scalar() == 0

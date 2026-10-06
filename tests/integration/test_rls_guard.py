"""Guard tests for the database roles created by infra/postgres/init/01-init.sh.

Proves, against a live gateway_test database, that:
  * the runtime role (gateway_app) is not a superuser and has NOBYPASSRLS;
  * row-level security actually hides rows from gateway_app;
  * a cleared/stale session context returns ZERO rows (no error) — the
    NULLIF(..., '') guard required by the RLS policies;
  * gateway_app cannot UPDATE (append-only posture, SPEC 14.2).

A scratch probe table is created and dropped around the tests so these pass
even before the real schema migration runs (the migrated schema itself is
covered by test_schema.py).
"""

import pytest
from app.db import clear_rls_context
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError

PROBE_TABLE = "rls_guard_probe"


@pytest.fixture()
def probe(owner_engine: Engine) -> None:
    """Scratch table with an RLS policy shaped like the real ones."""
    with owner_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {PROBE_TABLE}"))
        conn.execute(text(f"CREATE TABLE {PROBE_TABLE} (id int PRIMARY KEY, marker text NOT NULL)"))
        conn.execute(text(f"ALTER TABLE {PROBE_TABLE} ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                f"CREATE POLICY {PROBE_TABLE}_select ON {PROBE_TABLE} "
                "FOR SELECT TO gateway_app "
                "USING (marker = NULLIF(current_setting('app.probe_marker', true), ''))"
            )
        )
        conn.execute(text(f"GRANT SELECT ON {PROBE_TABLE} TO gateway_app"))
        conn.execute(text(f"INSERT INTO {PROBE_TABLE} VALUES (1, 'alpha'), (2, 'beta')"))
    yield
    with owner_engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {PROBE_TABLE}"))


def test_gateway_app_is_not_superuser_and_cannot_bypass_rls(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls, rolcreaterole "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
    assert row.current_user == "gateway_app"
    assert row.rolsuper is False
    assert row.rolbypassrls is False
    assert row.rolcreaterole is False


def test_rls_hides_unauthorized_rows(app_engine: Engine, probe: None) -> None:
    with app_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.probe_marker', 'alpha', true)"))
        count = conn.execute(text(f"SELECT count(*) FROM {PROBE_TABLE}")).scalar()
        assert count == 1  # only the 'alpha' row is visible

        conn.execute(text("SELECT set_config('app.probe_marker', 'beta', true)"))
        count = conn.execute(text(f"SELECT count(*) FROM {PROBE_TABLE}")).scalar()
        assert count == 1
        assert conn.execute(text(f"SELECT marker FROM {PROBE_TABLE}")).scalar_one() == "beta"


def test_stale_pooled_context_returns_zero_rows_not_an_error(
    app_engine: Engine, probe: None
) -> None:
    """Reuse one pooled connection: set context for one 'user', then clear it
    (session-level '') and query in a fresh transaction. Must be zero rows —
    never a cast error — proving the NULLIF guard in the policy."""
    with app_engine.connect() as conn:
        clear_rls_context(conn)  # session-level '' on this pooled connection
        conn.commit()
        # Same connection reused (pool_size=1): context is now '' everywhere.
        count = conn.execute(text(f"SELECT count(*) FROM {PROBE_TABLE}")).scalar()
        assert count == 0


def test_gateway_app_cannot_update(app_engine: Engine, probe: None) -> None:
    with app_engine.connect() as conn:
        with pytest.raises(ProgrammingError) as excinfo:
            conn.execute(text(f"UPDATE {PROBE_TABLE} SET marker = 'x'"))
        assert "permission denied" in str(excinfo.value).lower()
        conn.rollback()

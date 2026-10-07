"""LocalPolicy.item_visible (Python) must agree with row_filter (SQL).

Dashboard fixtures are filtered with the Python predicate; this proves it is the
same SPEC 7.1 rule as the SQL one, by checking every seeded record for every
demo user against the independent oracle in expected.py.
"""

import pytest
from app.authz.policy import LocalPolicy
from expected import GOLD_RECORDS
from sqlalchemy import text
from sqlalchemy.engine import Engine
from test_filter_only import access_context
from test_rls_only import USERNAMES

POLICY = LocalPolicy()


@pytest.mark.parametrize("username", USERNAMES)
def test_python_predicate_matches_the_oracle_on_every_record(
    owner_engine: Engine, seeded: None, username: str
) -> None:
    ctx = access_context(username)
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT r.source_ref, cl.rank, r.compartments, u.path"
                " FROM canonical_records r"
                " JOIN classification_levels cl ON cl.code = r.classification_code"
                " JOIN units u ON u.id = r.unit_id"
            )
        ).all()
    visible = {
        ref
        for ref, rank, compartments, path in rows
        if POLICY.item_visible(
            ctx,
            classification_rank=rank,
            compartments=compartments or [],
            unit_path=path,
        )
    }
    assert visible == GOLD_RECORDS[username]

import uuid

from app.db import RLS_KEYS, format_array, rls_clear_statements, rls_context_statements


def _context(**overrides):
    kwargs = {
        "user_id": uuid.uuid4(),
        "clearance_rank": 3,
        "compartments": {"UAS-OPS", "FORENSICS"},
        "unit_path": "/eib-group/",
        "data_scope": "standard",
        "session_id": "sess-1",
    }
    kwargs.update(overrides)
    return rls_context_statements(**kwargs)


def test_context_statements_cover_all_keys_transaction_locally() -> None:
    statements = _context()
    assert len(statements) == len(RLS_KEYS)
    applied_keys = set()
    for stmt, params in statements:
        assert stmt.startswith("SELECT set_config('app.")
        assert stmt.endswith(", true)")  # transaction-local: never session-persistent
        assert set(params) == {"value"}
        key = stmt.split("'")[1].removeprefix("app.")
        applied_keys.add(key)
    assert applied_keys == set(RLS_KEYS)


def test_context_values_are_formatted_for_postgres() -> None:
    params = [
        next(iter(p.values()))
        for _, p in _context(
            user_id="u1",
            clearance_rank=2,
            compartments={"FORENSICS", "UAS-OPS"},
            unit_path="/eib-group/stratoc/",
            data_scope="standard",
            session_id="s1",
        )
    ]
    assert "u1" in params
    assert "2" in params
    assert "{FORENSICS,UAS-OPS}" in params
    assert "/eib-group/stratoc/" in params
    assert "standard" in params
    assert "s1" in params


def test_clear_statements_use_session_level_empty_string() -> None:
    """A cleared pooled connection must yield '' (NULLIF -> NULL -> zero rows), not error."""
    statements = rls_clear_statements()
    assert len(statements) == len(RLS_KEYS)
    for stmt in statements:
        assert stmt.startswith("SELECT set_config('app.")
        assert stmt.endswith(", '', false)")  # session-level clear


def test_format_array_rejects_unexpected_codes() -> None:
    assert format_array(["B", "A"]) == "{A,B}"
    assert format_array(()) == "{}"
    try:
        format_array(["bad code"])
    except ValueError:
        pass
    else:
        raise AssertionError("invalid compartment code must be rejected")

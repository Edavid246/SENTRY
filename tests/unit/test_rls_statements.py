import uuid

from app.db import format_array, rls_context_statements


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


def test_format_array_rejects_unexpected_codes() -> None:
    assert format_array(["B", "A"]) == "{A,B}"
    assert format_array(()) == "{}"
    try:
        format_array(["bad code"])
    except ValueError:
        pass
    else:
        raise AssertionError("invalid compartment code must be rejected")

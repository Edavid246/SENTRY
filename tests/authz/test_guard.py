"""app.api.guard.guarded: the decide -> deny/scope -> audit sequence (no database).

The audit sink is captured, and the connection is None (nothing is read), so
these prove the ordering rules every guarded route inherits: a deny is audited
before it is answered, and an allowed request is audited on the way out even
when the route raises (a 404 for a missing row, a model outage).
"""

import pytest
from app.api import guard
from fastapi import HTTPException
from test_filter_only import access_context


@pytest.fixture
def written(monkeypatch) -> list[list[dict]]:
    batches: list[list[dict]] = []
    monkeypatch.setattr(guard, "audit_events", lambda payloads: batches.append(payloads))
    return batches


@pytest.mark.parametrize(("on_deny", "status"), [("forbidden", 403), ("not_found", 404)])
def test_deny_is_audited_then_answered(written, on_deny: str, status: int) -> None:
    ctx = access_context("s.eze")
    with (
        pytest.raises(HTTPException) as raised,
        guard.guarded(ctx, None, "read", "document", on_deny=on_deny),
    ):
        pytest.fail("a denied request must never reach its body")
    assert raised.value.status_code == status
    assert [[e["decision"] for e in batch] for batch in written] == [["deny"]]


def test_empty_deny_runs_the_body_without_a_filter(written) -> None:
    with guard.guarded(access_context("s.eze"), None, "read", "document", on_deny="empty") as scope:
        assert scope.allowed is False
        with pytest.raises(RuntimeError):
            scope.filter("document")
    assert [[e["decision"] for e in batch] for batch in written] == [["deny"]]


def test_allowed_request_audits_decide_and_reads_on_exit(written) -> None:
    with guard.guarded(access_context("a.bello"), None, "read", "document") as scope:
        assert scope.filter("document").where_sql
        scope.read("documents", 3)
        assert written == []  # nothing is written until the block ends
    (batch,) = written
    assert [(e["action"], e.get("rows")) for e in batch] == [("decide", None), ("query", 3)]


def test_allowed_request_is_audited_even_when_the_body_raises(written) -> None:
    ctx = access_context("a.bello")
    with (
        pytest.raises(HTTPException),
        guard.guarded(ctx, None, "read", "document") as scope,
    ):
        scope.read("documents", 0)
        raise HTTPException(status_code=404, detail="not found")
    (batch,) = written
    assert [e["action"] for e in batch] == ["decide", "query"]


def test_audit_resource_names_the_decide_event(written) -> None:
    ctx = access_context("a.bello")
    with guard.guarded(ctx, None, "retrieve", "record", audit_resource="connected_map"):
        pass
    assert written[0][0]["resource"] == "connected_map"

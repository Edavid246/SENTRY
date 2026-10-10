"""app.authz.scope + app.api.guard: the decide -> deny/scope -> audit sequence.

The audit sink is captured and the connection is a recorder (no database), so
these prove the ordering rules every guarded route and the assistant inherit:
a deny is audited before it is answered, an allowed request is audited on the
way out (decide events first, then everything recorded, in order) even when
the body raises, and a commit happens only after the audit batch is written.
"""

import pytest
from app.api import guard
from app.authz import scope as scope_module
from fastapi import HTTPException
from test_filter_only import access_context


class RecordingConn:
    """Stands in for a Connection: records statements and commits, returns nothing."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    def execute(self, statement, params=None):
        self.log.append("execute")

    def commit(self) -> None:
        self.log.append("commit")


@pytest.fixture
def log() -> list[str]:
    return []


@pytest.fixture
def written(monkeypatch, log) -> list[list[dict]]:
    batches: list[list[dict]] = []

    def sink(payloads):
        batches.append(payloads)
        log.append("audit")
        return [{"event_id": f"e{i}"} for i, _ in enumerate(payloads)]

    monkeypatch.setattr(scope_module, "audit_events", sink)
    monkeypatch.setattr(guard, "audit_events", sink)
    return batches


@pytest.mark.parametrize(("on_deny", "status"), [("forbidden", 403), ("not_found", 404)])
def test_deny_is_audited_then_answered(written, log, on_deny: str, status: int) -> None:
    ctx = access_context("group.it")
    with (
        pytest.raises(HTTPException) as raised,
        guard.guarded(ctx, RecordingConn(log), "read", "document", on_deny=on_deny),
    ):
        pytest.fail("a denied request must never reach its body")
    assert raised.value.status_code == status
    assert [[e["decision"] for e in batch] for batch in written] == [["deny"]]
    assert "execute" not in log  # no RLS context, no query: nothing ran


def test_empty_deny_yields_no_scope(written, log) -> None:
    ctx = access_context("group.it")
    with guard.guarded_or_empty(
        ctx, RecordingConn(log), "retrieve", "record", audit_resource="connected_map"
    ) as scope:
        assert scope is None
    assert [[(e["resource"], e["decision"]) for e in batch] for batch in written] == [
        [("connected_map", "deny")]
    ]


def test_allowed_request_audits_decide_and_reads_on_exit(written, log) -> None:
    with guard.guarded(access_context("owner"), RecordingConn(log), "read", "document") as scope:
        assert scope.filter("document").where_sql
        scope.read("document", 3)
        assert written == []  # nothing is written until the block ends
    (batch,) = written
    assert [(e["action"], e.get("rows")) for e in batch] == [("decide", None), ("query", 3)]


def test_the_rls_context_is_set_once_when_the_scope_opens(written, log) -> None:
    with guard.guarded(access_context("owner"), RecordingConn(log), "read", "document"):
        set_by_scope = list(log)
    assert set_by_scope and set(set_by_scope) == {"execute"}
    assert log == [*set_by_scope, "audit"]


def test_allowed_request_is_audited_even_when_the_body_raises(written, log) -> None:
    ctx = access_context("owner")
    with (
        pytest.raises(HTTPException),
        guard.guarded(ctx, RecordingConn(log), "read", "document") as scope,
    ):
        scope.read("document", 0)
        scope.commit()
        raise HTTPException(status_code=404, detail="not found")
    (batch,) = written
    assert [e["action"] for e in batch] == ["decide", "query"]
    assert "commit" not in log  # a failed request stores nothing


def test_writes_are_committed_only_after_the_audit_batch(written, log) -> None:
    with scope_module.authorized(
        access_context("owner"), RecordingConn(log), [("read", "document")]
    ) as scope:
        scope.commit()
        assert "commit" not in log
    assert log[-2:] == ["audit", "commit"]
    assert scope.written[-1]["event_id"] == "e0"


def test_requirements_are_decided_in_order_and_the_first_deny_stops(written, log) -> None:
    ctx = access_context("owner")
    with pytest.raises(scope_module.Forbidden):
        scope_module.authorize(
            ctx, [("read", "document"), ("manage", "document"), ("query", "record")]
        )
    (batch,) = written
    assert [(e["requested"], e["decision"]) for e in batch] == [
        ("read", "allow"),
        ("manage", "deny"),
    ]


def test_permitted_audits_the_decision_alone(written) -> None:
    guard.permitted(access_context("group.audit"), "read_audit", "audit")
    assert [[e["decision"] for e in batch] for batch in written] == [["allow"]]
    with pytest.raises(HTTPException) as raised:
        guard.permitted(access_context("briech.lead"), "read_audit", "audit")
    assert raised.value.status_code == 403

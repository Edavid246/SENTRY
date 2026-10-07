"""GET /audit and GET /audit/verify through the real HTTP stack (SPEC 14).

Covers the three questions the demo has to answer honestly: who may read the
trail, what got recorded for real requests (login, decide, query), and what
verification reports when the chain and both tamper-evidence layers are
healthy — plus the blocking behaviour when the audit write itself fails.
"""

from __future__ import annotations

import pytest
from app.audit.chain import append_events, utc_now_iso
from app.db import get_engine
from test_auth_endpoints import auth_header, login

AUDITOR = "f.danjuma"
SYSADMIN = "s.eze"
DATA_USERS = ["a.bello", "a.okafor", "t.adeyemi", "k.musa"]


def _audit(client, username: str = AUDITOR, limit: int = 200) -> list[dict]:
    response = client.get(f"/audit?limit={limit}", headers=auth_header(client, username))
    assert response.status_code == 200, response.text
    return response.json()


def _latest(events: list[dict], **match) -> dict | None:
    for event in sorted(events, key=lambda item: item["seq"], reverse=True):
        if all(event["payload"].get(key) == value for key, value in match.items()):
            return event
    return None


def test_login_success_and_failure_are_both_audited(client) -> None:
    assert login(client, "a.bello", password="wrong-password").status_code == 401
    assert login(client, "a.bello").status_code == 200
    events = _audit(client)
    denied = _latest(events, actor="a.bello", action="login", decision="deny")
    allowed = _latest(events, actor="a.bello", action="login", decision="allow")
    assert denied is not None
    assert denied["payload"]["reasons"] == ["invalid credentials"]
    assert allowed is not None
    assert allowed["payload"]["resource"] == "auth"
    assert allowed["payload"]["user_id"]


@pytest.mark.parametrize("username", DATA_USERS)
def test_operational_roles_may_not_read_the_audit_trail(client, username: str) -> None:
    response = client.get("/audit", headers=auth_header(client, username))
    assert response.status_code == 403
    verify = client.get("/audit/verify", headers=auth_header(client, username))
    assert verify.status_code == 403


def test_auditor_and_sysadmin_may_read_the_audit_trail(client) -> None:
    for username in (AUDITOR, SYSADMIN):
        response = client.get("/audit?limit=5", headers=auth_header(client, username))
        assert response.status_code == 200, response.text
        verify = client.get("/audit/verify", headers=auth_header(client, username))
        assert verify.status_code == 200, verify.text


def test_audit_requires_authentication(client) -> None:
    assert client.get("/audit").status_code == 401
    assert client.get("/audit/verify").status_code == 401


def test_rejected_token_is_audited(client) -> None:
    response = client.get("/audit", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401
    rejected = _latest(_audit(client), action="authenticate", decision="deny")
    assert rejected is not None
    assert rejected["payload"]["actor"] == "anonymous"


def test_allowed_data_request_records_decide_then_query(client) -> None:
    headers = auth_header(client, "a.bello")
    response = client.get("/documents", headers=headers)
    assert response.status_code == 200
    events = _audit(client)
    decide = _latest(
        events, actor="a.bello", action="decide", resource="document", decision="allow"
    )
    query = _latest(events, actor="a.bello", action="query", resource="documents")
    assert decide is not None and query is not None
    assert decide["payload"]["requested"] == "read"
    assert query["payload"]["rows"] == len(response.json())
    assert query["payload"]["decision"] == "allow"
    assert decide["seq"] < query["seq"]


def test_denied_data_request_records_a_single_denied_decide(client) -> None:
    headers = auth_header(client, SYSADMIN)
    assert client.get("/documents", headers=headers).status_code == 403
    events = _audit(client)
    decide = _latest(events, actor=SYSADMIN, action="decide", resource="document")
    assert decide is not None
    assert decide["payload"]["decision"] == "deny"
    assert any("not granted" in reason for reason in decide["payload"]["reasons"])
    assert _latest(events, actor=SYSADMIN, action="query") is None


def test_verify_reports_healthy_chain_and_both_layers(client) -> None:
    # A batch of exactly `interval` events always crosses a checkpoint
    # boundary, so both external layers get a fresh tip.
    append_events(
        get_engine(),
        [
            {
                "actor": "checkpoint-seed",
                "action": "test",
                "resource": "audit",
                "decision": "allow",
                "timestamp": utc_now_iso(),
                "n": i,
            }
            for i in range(10)
        ],
    )
    response = client.get("/audit/verify", headers=auth_header(client, AUDITOR))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "valid",
        "first_broken_seq",
        "event_count",
        "checkpoint_ok",
        "checkpoint_tip",
        "ledger_ok",
        "ledger_tip",
    }
    assert body["valid"] is True
    assert body["first_broken_seq"] is None
    assert isinstance(body["event_count"], int) and body["event_count"] >= 10
    assert body["checkpoint_ok"] is True
    assert body["ledger_ok"] is True
    for tip_key in ("checkpoint_tip", "ledger_tip"):
        assert set(body[tip_key]) == {"seq", "hash"}
        assert len(body[tip_key]["hash"]) == 64


def test_audit_items_have_the_viewer_shape(client) -> None:
    events = _audit(client, limit=5)
    assert events
    seqs = [event["seq"] for event in events]
    assert seqs == sorted(seqs, reverse=True)
    for event in events:
        assert set(event) == {"seq", "created_at", "payload", "prev_hash", "hash"}
        assert len(event["prev_hash"]) == 64
        assert len(event["hash"]) == 64
        payload = event["payload"]
        assert {"actor", "action", "resource", "decision", "timestamp"} <= set(payload)


def test_login_timestamps_are_utc(client) -> None:
    assert login(client, "t.adeyemi").status_code == 200
    event = _latest(_audit(client), actor="t.adeyemi", action="login", decision="allow")
    assert event is not None
    assert event["payload"]["timestamp"].endswith("+00:00")


def test_audit_write_failure_blocks_the_request(client, monkeypatch) -> None:
    headers = auth_header(client, "a.bello")

    def boom(*args, **kwargs) -> None:
        raise RuntimeError("audit storage down")

    monkeypatch.setattr("app.api.endpoints.audit_events", boom)
    with pytest.raises(RuntimeError, match="audit storage down"):
        client.get("/documents", headers=headers)

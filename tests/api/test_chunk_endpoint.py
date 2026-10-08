"""GET /api/v1/documents/{document_id}/chunks/{chunk_id}: cited-passage viewer.

Every citation in an answer or a stored turn must open the exact page it
points at, through the same decide -> row filter + RLS path as every other
classified read (SPEC 7.3, SPEC 14). Denied, foreign, and malformed ids
answer 404 — never 403 — so a probe cannot confirm that a restricted
passage exists.
"""

import pytest
from app.seed import _id
from test_assistant_endpoints import _audit, _latest
from test_auth_endpoints import auth_header

# Confidential, own unit of t.adeyemi: visible to a.bello, above t.adeyemi's
# restricted clearance, and unreachable without the right unit path.
CHUNK_016 = str(_id("chunk:DOC-016:1"))
# Secret + UAS-OPS compartment in the UAS wing: a.bello holds the compartment
# and the clearance; a.okafor has neither the rank nor the compartment, and
# k.musa holds the compartment but is only confidential-cleared.
CHUNK_005 = str(_id("chunk:DOC-005:1"))


def _read(client, username: str, ref: str, chunk_id: str):
    return client.get(
        f"/api/v1/documents/{ref}/chunks/{chunk_id}",
        headers=auth_header(client, username),
    )


def test_viewer_returns_the_cited_passage(client) -> None:
    response = _read(client, "a.bello", "DOC-016", CHUNK_016)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "chunk_id",
        "document_id",
        "document_ref",
        "document_title",
        "text",
        "page",
        "section",
        "classification_code",
        "compartments",
    }
    assert body["chunk_id"] == CHUNK_016
    assert body["document_ref"] == "DOC-016"
    assert body["document_title"] == "Training Readiness Summary Q3"
    assert body["classification_code"] == "confidential"
    assert body["compartments"] == []
    assert body["page"] == 1
    assert body["section"] == "Summary"
    assert body["text"] == (
        "Training Readiness Summary Q3 — reference copy held at /command-a/bde-2/bn-4/."
    )


def test_viewer_also_accepts_the_document_uuid(client) -> None:
    with_uuid = _read(client, "a.bello", str(_id("doc:DOC-016")), CHUNK_016)
    assert with_uuid.status_code == 200, with_uuid.text
    with_ref = _read(client, "a.bello", "DOC-016", CHUNK_016)
    assert with_uuid.json() == with_ref.json()


def test_passage_above_the_callers_clearance_is_404_not_403(client) -> None:
    response = _read(client, "t.adeyemi", "DOC-016", CHUNK_016)
    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}

    events = _audit(client)
    decide = _latest(events, actor="t.adeyemi", action="decide", resource="chunk", decision="allow")
    assert decide is not None
    assert decide["payload"]["requested"] == "read"
    rows = _latest(events, actor="t.adeyemi", action="query", resource="chunk")
    assert rows is not None
    assert rows["payload"]["rows"] == 0


def test_caller_without_data_scope_is_denied_before_any_row_read(client) -> None:
    response = _read(client, "s.eze", "DOC-016", CHUNK_016)
    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}

    events = _audit(client)
    decide = _latest(events, actor="s.eze", action="decide", resource="chunk", decision="deny")
    assert decide is not None
    reasons = decide["payload"]["reasons"]
    assert "data_scope 'none' does not permit data actions" in reasons
    assert any("not granted by role 'sysadmin'" in reason for reason in reasons)
    assert _latest(events, actor="s.eze", action="query", resource="chunk") is None


def test_a_caller_missing_the_compartment_gets_404(client) -> None:
    assert _read(client, "a.okafor", "DOC-005", CHUNK_005).status_code == 404
    # k.musa holds UAS-OPS but is only confidential-cleared: compartment
    # right does not buy a secret passage.
    assert _read(client, "k.musa", "DOC-005", CHUNK_005).status_code == 404
    # The compartment holder with the clearance reads it fine.
    assert _read(client, "a.bello", "DOC-005", CHUNK_005).status_code == 200


def test_passage_from_a_different_document_is_404(client) -> None:
    response = _read(client, "a.bello", "DOC-001", CHUNK_016)
    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}


def test_unknown_and_malformed_ids_answer_404_not_500(client) -> None:
    cases = [
        ("DOC-016", "0" * 32),
        ("DOC-999", CHUNK_016),
        ("DOC-016", "not-a-uuid"),
        ("not-a-ref", CHUNK_016),
    ]
    for ref, chunk_id in cases:
        response = _read(client, "a.bello", ref, chunk_id)
        assert response.status_code == 404, (ref, chunk_id, response.status_code)
        assert response.json() == {"detail": "not found"}


def test_viewer_reads_are_audited(client) -> None:
    baseline = max(event["seq"] for event in _audit(client))
    assert _read(client, "a.bello", "DOC-016", CHUNK_016).status_code == 200

    events = [event for event in _audit(client) if event["seq"] > baseline]
    decide = _latest(events, actor="a.bello", action="decide", resource="chunk", decision="allow")
    assert decide is not None
    assert decide["payload"]["requested"] == "read"
    rows = _latest(events, actor="a.bello", action="query", resource="chunk")
    assert rows is not None
    assert rows["payload"]["rows"] == 1
    assert decide["seq"] < rows["seq"]


def test_viewer_requires_authentication(client) -> None:
    response = client.get(f"/api/v1/documents/DOC-016/chunks/{CHUNK_016}")
    assert response.status_code == 401
    assert response.json() == {"detail": "not authenticated"}


@pytest.mark.parametrize("username", ["f.danjuma", "s.eze"])
def test_users_outside_the_data_scope_never_reach_a_passage(client, username) -> None:
    response = _read(client, username, "DOC-016", CHUNK_016)
    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}

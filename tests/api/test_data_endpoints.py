"""GET /documents, /records and /documents/{id}: gold sets through the full HTTP stack.

Login -> JWT -> AccessContext -> decide -> set_rls_context + row filter -> rows,
exactly as production runs it. Same expected.py oracle as the lower layers.
"""

import pytest
from expected import GOLD_DOCUMENTS, GOLD_RECORDS
from test_auth_endpoints import auth_header
from test_rls_only import USERNAMES

# Users whose decide() denies data actions entirely: lists answer 403, detail 404.
NO_DATA_USERS = frozenset({"s.eze", "f.danjuma"})


@pytest.mark.parametrize("username", USERNAMES)
def test_documents_gold_set(client, username: str) -> None:
    response = client.get("/api/v1/documents", headers=auth_header(client, username))
    if username in NO_DATA_USERS:
        assert response.status_code == 403
        assert response.json() == {"detail": "forbidden"}
        return
    assert response.status_code == 200
    items = response.json()
    assert {item["source_ref"] for item in items} == GOLD_DOCUMENTS[username]
    for item in items:
        assert set(item) == {"source_ref", "title", "classification_code"}


@pytest.mark.parametrize("username", USERNAMES)
def test_records_gold_set(client, username: str) -> None:
    response = client.get("/api/v1/records", headers=auth_header(client, username))
    if username in NO_DATA_USERS:
        assert response.status_code == 403
        assert response.json() == {"detail": "forbidden"}
        return
    assert response.status_code == 200
    items = response.json()
    assert {item["source_ref"] for item in items} == GOLD_RECORDS[username]
    for item in items:
        assert set(item) == {"source_ref", "entity_type", "classification_code"}


def test_visible_document_detail(client) -> None:
    response = client.get("/api/v1/documents/DOC-001", headers=auth_header(client, "a.bello"))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"source_ref", "title", "classification_code"}
    assert body["source_ref"] == "DOC-001"


def test_restricted_document_probed_returns_404_not_403(client) -> None:
    # k.musa may read documents, but DOC-001 sits outside their unit: 404, no
    # confirmation that the document exists.
    response = client.get("/api/v1/documents/DOC-001", headers=auth_header(client, "k.musa"))
    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}


def test_user_without_read_permission_gets_404_on_detail(client) -> None:
    response = client.get("/api/v1/documents/DOC-001", headers=auth_header(client, "s.eze"))
    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}


def test_unknown_document_returns_404(client) -> None:
    response = client.get("/api/v1/documents/DOC-999", headers=auth_header(client, "a.bello"))
    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}


@pytest.mark.parametrize(
    "path",
    ["/api/v1/documents", "/api/v1/records", "/api/v1/me", "/api/v1/documents/DOC-001"],
)
def test_endpoints_require_authorization(client, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 401
    assert response.json() == {"detail": "not authenticated"}


def test_documents_without_token_uses_generic_401(client) -> None:
    response = client.get("/api/v1/documents", headers={"Authorization": "Bearer bogus.token.here"})
    assert response.status_code == 401
    assert response.json() == {"detail": "not authenticated"}


# --- GET /api/v1/records/{source_ref} ---------------------------------------


def test_record_detail_visible_and_hidden(client) -> None:
    from test_auth_endpoints import auth_header

    bello = client.get("/api/v1/records/REC-023", headers=auth_header(client, "a.bello"))
    assert bello.status_code == 200
    body = bello.json()
    assert body["classification_code"] == "secret" and body["compartments"] == ["UAS-OPS"]
    assert body["data"]["certification"] == "UAS Pilot"
    # Not visible to a lower-cleared user: 404, same as a record that does not exist.
    hidden = client.get("/api/v1/records/REC-023", headers=auth_header(client, "t.adeyemi"))
    missing = client.get("/api/v1/records/REC-999", headers=auth_header(client, "t.adeyemi"))
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()
    assert (
        client.get("/api/v1/records/REC-011", headers=auth_header(client, "t.adeyemi")).status_code
        == 200
    )


def test_record_detail_no_data_roles_and_audit(client) -> None:
    from test_assistant_endpoints import _audit, _latest
    from test_auth_endpoints import auth_header

    assert (
        client.get("/api/v1/records/REC-011", headers=auth_header(client, "s.eze")).status_code
        == 404
    )
    client.get("/api/v1/records/REC-011", headers=auth_header(client, "a.okafor"))
    event = _latest(_audit(client), actor="a.okafor", action="query", resource="record")
    assert event["payload"]["rows"] == 1

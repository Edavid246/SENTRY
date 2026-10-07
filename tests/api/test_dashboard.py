"""Dashboard summary (Part C): permission-aware, audited, placeholder data.

The fixtures carry classification/compartments/unit and are filtered through
LocalPolicy.item_visible, so different users get different dashboards and the
Secret finding never reaches a Restricted caller.
"""

from __future__ import annotations

from test_assistant_endpoints import _audit, _latest
from test_auth_endpoints import auth_header

PATH = "/api/v1/dashboard/summary"
TILE_KEYS = {"readiness", "maintenance_backlog", "expiring_certifications", "recent_findings"}
ITEM_KEYS = {
    "id",
    "label",
    "value",
    "unit",
    "detail",
    "severity",
    "trend",
    "classification",
    "compartments",
    "unit_path",
    "unit_name",
}


def _summary(client, username: str):
    return client.get(PATH, headers=auth_header(client, username))


def _ids(body: dict, tile: str) -> set[str]:
    return {item["id"] for item in body["tiles"][tile]["items"]}


def _all_ids(body: dict) -> set[str]:
    return {i for tile in body["tiles"] for i in _ids(body, tile)}


def test_shape_is_the_contract_for_every_tile(client) -> None:
    body = _summary(client, "a.bello").json()
    assert set(body["tiles"]) == TILE_KEYS
    for tile in body["tiles"].values():
        assert set(tile) == {"stub", "source", "title", "items"}
        assert tile["stub"] is True and tile["source"]
        for item in tile["items"]:
            assert set(item) == ITEM_KEYS


def test_bello_and_adeyemi_get_different_dashboards(client) -> None:
    bello = _summary(client, "a.bello").json()
    adeyemi = _summary(client, "t.adeyemi").json()
    assert _ids(bello, "readiness") == {"RDY-CMD", "RDY-BDE2", "RDY-BN4", "RDY-UAS"}
    assert _ids(adeyemi, "readiness") == {"RDY-BN4"}
    assert _ids(bello, "maintenance_backlog") == {"MNT-BN4", "MNT-BDE2", "MNT-UAS"}
    assert _ids(adeyemi, "maintenance_backlog") == {"MNT-BN4"}
    assert _ids(adeyemi, "expiring_certifications") == {"CRT-BN4"}
    assert _all_ids(adeyemi) < _all_ids(bello)


def test_secret_finding_is_visible_to_bello_and_absent_for_adeyemi(client) -> None:
    bello = _summary(client, "a.bello").json()
    adeyemi = _summary(client, "t.adeyemi").json()
    assert "FND-CORR" in _ids(bello, "recent_findings")
    assert _ids(adeyemi, "recent_findings") == {"FND-ATT"}
    # Nowhere in the raw response either, not even as text.
    assert "FND-CORR" not in _summary(client, "t.adeyemi").text
    assert "spare-part shortage" not in _summary(client, "t.adeyemi").text


def test_confidential_user_sees_confidential_but_not_secret(client) -> None:
    okafor = _summary(client, "a.okafor").json()
    assert _ids(okafor, "recent_findings") == {"FND-ATT", "FND-AMM"}
    # UAS Wing is outside Okafor's unit scope (and needs UAS-OPS).
    assert "RDY-UAS" not in _ids(okafor, "readiness")


def test_compartment_item_needs_the_compartment(client) -> None:
    musa = _summary(client, "k.musa").json()
    # Musa holds UAS-OPS and is in the UAS Wing: sees only that unit's items.
    assert _all_ids(musa) == {"RDY-UAS", "MNT-UAS"}


def test_no_data_roles_get_403(client) -> None:
    assert _summary(client, "s.eze").status_code == 403
    assert _summary(client, "f.danjuma").status_code == 403


def test_unauthenticated_is_401(client) -> None:
    assert client.get(PATH).status_code == 401


def test_every_returned_item_is_labelled_with_its_classification(client) -> None:
    body = _summary(client, "a.bello").json()
    secret = [i for t in body["tiles"].values() for i in t["items"] if i["id"] == "FND-CORR"][0]
    assert secret["classification"] == "secret"
    assert secret["unit_name"] == "Battalion 4"


def test_audit_events_are_written(client) -> None:
    body = _summary(client, "t.adeyemi").json()
    events = _audit(client)
    decide = _latest(events, actor="t.adeyemi", action="decide", resource="dashboard")
    query = _latest(events, actor="t.adeyemi", action="query", resource="dashboard")
    assert decide["payload"]["decision"] == "allow"
    assert query["payload"]["rows"] == len(_all_ids(body))
    assert sorted(query["payload"]["item_ids"]) == sorted(_all_ids(body))


def test_denied_call_is_audited(client) -> None:
    _summary(client, "s.eze")
    deny = _latest(_audit(client), actor="s.eze", action="decide", resource="dashboard")
    assert deny["payload"]["decision"] == "deny" and deny["payload"]["reasons"]

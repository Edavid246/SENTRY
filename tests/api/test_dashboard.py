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


FINDING = "FND-RISING-FAULTS-BN-4"


def _run_correlation(client) -> None:
    """The finding exists only once a commander has run the job (idempotent)."""
    assert (
        client.post("/api/v1/correlation/run", headers=auth_header(client, "a.bello")).status_code
        == 200
    )


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
        assert tile["source"]
        for item in tile["items"]:
            assert set(item) == ITEM_KEYS


def test_bello_and_adeyemi_get_different_dashboards(client) -> None:
    bello = _summary(client, "a.bello").json()
    adeyemi = _summary(client, "t.adeyemi").json()
    assert _ids(bello, "readiness") == {"RDY-CMD", "RDY-BDE2", "RDY-BN4", "RDY-UAS"}
    assert _ids(adeyemi, "readiness") == {"RDY-BN4"}
    # real tiles: overdue equipment REC-011 (Bn 4) and REC-014 (Bde 2)
    assert _ids(bello, "maintenance_backlog") == {"MNT-BN-4", "MNT-BDE-2"}
    assert _ids(adeyemi, "maintenance_backlog") == {"MNT-BN-4"}
    assert _ids(bello, "expiring_certifications") == {
        "CRT-BN-4",
        "CRT-BDE-2",
        "CRT-UAS-WING",
        "CRT-COMMAND-A",
    }
    assert _ids(adeyemi, "expiring_certifications") == {"CRT-BN-4"}
    assert _all_ids(adeyemi) < _all_ids(bello)


def test_secret_finding_is_visible_to_bello_and_absent_for_adeyemi(client) -> None:
    _run_correlation(client)
    bello = _summary(client, "a.bello").json()
    adeyemi = _summary(client, "t.adeyemi").json()
    assert _ids(bello, "recent_findings") == {FINDING}
    assert _ids(adeyemi, "recent_findings") == set()
    # Nowhere in the raw response either, not even as text.
    for needle in (FINDING, "spare-part shortage", "lapsed maintainer"):
        assert needle not in _summary(client, "t.adeyemi").text


def test_tiles_are_real_exactly_where_the_data_is_real(client) -> None:
    tiles = _summary(client, "a.bello").json()["tiles"]
    assert {k: t["stub"] for k, t in tiles.items()} == {
        "readiness": True,
        "maintenance_backlog": False,
        "expiring_certifications": False,
        "recent_findings": False,
    }
    assert "typed tool" in tiles["maintenance_backlog"]["source"]


def test_real_tile_items_are_derived_and_inherit_classification(client) -> None:
    items = {
        i["id"]: i
        for i in _summary(client, "a.bello").json()["tiles"]["expiring_certifications"]["items"]
    }
    # one Secret/UAS-OPS record in the UAS Wing group: the count inherits both
    assert items["CRT-UAS-WING"]["classification"] == "secret"
    assert items["CRT-UAS-WING"]["compartments"] == ["UAS-OPS"]
    # Bde 2 group mixes Restricted and Confidential records: highest wins
    assert items["CRT-BDE-2"]["classification"] == "confidential"
    assert items["CRT-BDE-2"]["value"] == 2
    assert items["CRT-BN-4"]["detail"] == "REC-019, REC-020, REC-041, REC-042"


def test_real_tiles_call_the_audited_typed_tools(client) -> None:
    _summary(client, "t.adeyemi")
    tools = {
        e["payload"]["tool"]
        for e in _audit(client)
        if e["payload"].get("action") == "data_query" and e["payload"]["actor"] == "t.adeyemi"
    }
    assert {"equipment_due_for_maintenance", "expired_certifications"} <= tools


def test_confidential_user_sees_confidential_but_not_secret(client) -> None:
    okafor = _summary(client, "a.okafor").json()
    _run_correlation(client)
    assert _ids(_summary(client, "a.okafor").json(), "recent_findings") == set()
    # UAS Wing is outside Okafor's unit scope (and needs UAS-OPS).
    assert "RDY-UAS" not in _ids(okafor, "readiness")


def test_compartment_item_needs_the_compartment(client) -> None:
    musa = _summary(client, "k.musa").json()
    # Musa holds UAS-OPS and is in the UAS Wing: sees only that unit's items.
    # (the Secret expired UAS certification is above Musa's clearance)
    assert _all_ids(musa) == {"RDY-UAS"}


def test_no_data_roles_get_403(client) -> None:
    assert _summary(client, "s.eze").status_code == 403
    assert _summary(client, "f.danjuma").status_code == 403


def test_unauthenticated_is_401(client) -> None:
    assert client.get(PATH).status_code == 401


def test_every_returned_item_is_labelled_with_its_classification(client) -> None:
    body = _summary(client, "a.bello").json()
    _run_correlation(client)
    body = _summary(client, "a.bello").json()
    secret = [i for t in body["tiles"].values() for i in t["items"] if i["id"] == FINDING][0]
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

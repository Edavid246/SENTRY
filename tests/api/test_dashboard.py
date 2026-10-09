"""Dashboard summary: permission-aware, audited, every tile counted from typed tools.

Counts come from audited typed tools filtered by the adapter, so different users get
different dashboards and the Secret finding never reaches a Restricted caller.
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


FINDING = "FND-RISING-FAULTS-SITE-4"


def _run_correlation(client) -> None:
    """The finding exists only once a commander has run the job (idempotent)."""
    assert (
        client.post("/api/v1/correlation/run", headers=auth_header(client, "owner")).status_code
        == 200
    )


def _summary(client, username: str):
    return client.get(PATH, headers=auth_header(client, username))


def _ids(body: dict, tile: str) -> set[str]:
    return {item["id"] for item in body["tiles"][tile]["items"]}


def _all_ids(body: dict) -> set[str]:
    return {i for tile in body["tiles"] for i in _ids(body, tile)}


def test_shape_is_the_contract_for_every_tile(client) -> None:
    body = _summary(client, "owner").json()
    assert set(body["tiles"]) == TILE_KEYS
    for tile in body["tiles"].values():
        assert set(tile) == {"stub", "source", "title", "items"}
        assert tile["source"]
        for item in tile["items"]:
            assert set(item) == ITEM_KEYS


def test_owner_and_coo_get_different_dashboards(client) -> None:
    owner = _summary(client, "owner").json()
    coo = _summary(client, "coo").json()
    # group status: one item per subsidiary; Giga and Poctova have nothing open (0 items)
    assert _ids(owner, "readiness") == {
        "GRP-STRATOC",
        "GRP-BRIECH",
        "GRP-EIB-GROUP",
        "GRP-GIGA",
        "GRP-POCTOVA",
    }
    assert _ids(coo, "readiness") == {"GRP-STRATOC"}
    # real tiles: overdue equipment REC-011 (Site 4) and REC-014 (Stratoc)
    assert _ids(owner, "maintenance_backlog") == {"MNT-SITE-4", "MNT-STRATOC"}
    assert _ids(coo, "maintenance_backlog") == {"MNT-SITE-4"}
    assert _ids(owner, "expiring_certifications") == {
        "CRT-SITE-4",
        "CRT-STRATOC",
        "CRT-BRIECH",
        "CRT-EIB-GROUP",
    }
    assert _ids(coo, "expiring_certifications") == {"CRT-SITE-4"}
    assert _all_ids(coo) < _all_ids(owner)


def test_secret_finding_is_visible_to_owner_and_absent_for_coo(client) -> None:
    _run_correlation(client)
    owner = _summary(client, "owner").json()
    coo = _summary(client, "coo").json()
    assert _ids(owner, "recent_findings") == {FINDING}
    assert _ids(coo, "recent_findings") == set()
    # Nowhere in the raw response either, not even as text.
    for needle in (FINDING, "spare-part shortage", "lapsed maintainer"):
        assert needle not in _summary(client, "coo").text


def test_tiles_are_real_exactly_where_the_data_is_real(client) -> None:
    tiles = _summary(client, "owner").json()["tiles"]
    assert {k: t["stub"] for k, t in tiles.items()} == {
        "readiness": False,
        "maintenance_backlog": False,
        "expiring_certifications": False,
        "recent_findings": False,
    }
    assert "typed tool" in tiles["maintenance_backlog"]["source"]


def test_real_tile_items_are_derived_and_inherit_classification(client) -> None:
    items = {
        i["id"]: i
        for i in _summary(client, "owner").json()["tiles"]["expiring_certifications"]["items"]
    }
    # one Secret/UAS-OPS record in the Briech UAS group: the count inherits both
    assert items["CRT-BRIECH"]["classification"] == "secret"
    assert items["CRT-BRIECH"]["compartments"] == ["UAS-OPS"]
    # Stratoc group mixes Restricted and Confidential records: highest wins
    assert items["CRT-STRATOC"]["classification"] == "confidential"
    assert items["CRT-STRATOC"]["value"] == 2
    assert items["CRT-SITE-4"]["detail"] == "REC-019, REC-020, REC-041, REC-042"


def test_group_status_counts_and_inherited_labels(client) -> None:
    def items(user):
        tile = _summary(client, user).json()["tiles"]["readiness"]
        return {i["id"]: i for i in tile["items"]}

    owner = items("owner")
    # Stratoc: REC-011/014 equipment, 019-022/041/042 certs, 010/026 stock = 10 (Confidential)
    assert owner["GRP-STRATOC"]["value"] == 10
    assert owner["GRP-STRATOC"]["classification"] == "confidential"
    # Briech: REC-023 cert (Secret, UAS-OPS) + cancelled missions 056/057/060 (060 Secret)
    assert owner["GRP-BRIECH"]["value"] == 4
    assert owner["GRP-BRIECH"]["classification"] == "secret"
    assert owner["GRP-BRIECH"]["compartments"] == ["UAS-OPS"]
    # a subsidiary with nothing open: zero inputs, lowest label, no compartments
    assert owner["GRP-GIGA"]["value"] == 0
    assert owner["GRP-GIGA"]["classification"] == "unclassified"
    assert owner["GRP-GIGA"]["compartments"] == []
    # the limited user's count covers only what that user may see (Site 4 rows)
    assert items("coo")["GRP-STRATOC"]["value"] == 6
    assert items("coo")["GRP-STRATOC"]["classification"] == "restricted"
    assert items("briech.lead")["GRP-BRIECH"]["value"] == 2  # cert 023 and mission 060 hidden
    assert items("briech.lead")["GRP-BRIECH"]["classification"] == "confidential"


def test_real_tiles_call_the_audited_typed_tools(client) -> None:
    _summary(client, "coo")
    tools = {
        e["payload"]["tool"]
        for e in _audit(client)
        if e["payload"].get("action") == "data_query" and e["payload"]["actor"] == "coo"
    }
    assert {
        "equipment_due_for_maintenance",
        "expired_certifications",
        "stock_below_threshold",
        "uas_missions",
    } <= tools


def test_confidential_user_sees_confidential_but_not_secret(client) -> None:
    logistics_head = _summary(client, "logistics.head").json()
    _run_correlation(client)
    assert _ids(_summary(client, "logistics.head").json(), "recent_findings") == set()
    # Briech UAS is outside The logistics head's unit scope (and needs UAS-OPS).
    assert _ids(logistics_head, "readiness") == {"GRP-STRATOC"}


def test_compartment_item_needs_the_compartment(client) -> None:
    briech_lead = _summary(client, "briech.lead").json()
    # The Briech lead holds UAS-OPS and is in the Briech UAS: sees only that unit's items.
    # (the Secret expired UAS certification is above The Briech lead's clearance)
    assert _all_ids(briech_lead) == {"GRP-BRIECH"}


def test_no_data_roles_get_403(client) -> None:
    assert _summary(client, "group.it").status_code == 403
    assert _summary(client, "group.audit").status_code == 403


def test_unauthenticated_is_401(client) -> None:
    assert client.get(PATH).status_code == 401


def test_every_returned_item_is_labelled_with_its_classification(client) -> None:
    body = _summary(client, "owner").json()
    _run_correlation(client)
    body = _summary(client, "owner").json()
    secret = [i for t in body["tiles"].values() for i in t["items"] if i["id"] == FINDING][0]
    assert secret["classification"] == "secret"
    assert secret["unit_name"] == "Stratoc Site Team 4"


def test_audit_events_are_written(client) -> None:
    body = _summary(client, "coo").json()
    events = _audit(client)
    decide = _latest(events, actor="coo", action="decide", resource="dashboard")
    query = _latest(events, actor="coo", action="query", resource="dashboard")
    assert decide["payload"]["decision"] == "allow"
    assert query["payload"]["rows"] == len(_all_ids(body))
    assert sorted(query["payload"]["item_ids"]) == sorted(_all_ids(body))


def test_denied_call_is_audited(client) -> None:
    _summary(client, "group.it")
    deny = _latest(_audit(client), actor="group.it", action="decide", resource="dashboard")
    assert deny["payload"]["decision"] == "deny" and deny["payload"]["reasons"]


def test_tool_queries_are_audited_after_the_decision_that_allowed_them(client) -> None:
    """One batch per request, in causal order: decide, the tiles' data_query events, query."""
    tip = max(event["seq"] for event in _audit(client))
    _summary(client, "owner")
    mine = [
        e["payload"]["action"]
        for e in sorted(_audit(client), key=lambda e: e["seq"])
        if e["seq"] > tip and e["payload"]["actor"] == "owner" and e["payload"]["action"] != "login"
    ]
    # maintenance + certifications tiles, then the four group-status tools
    assert mine == ["decide", *["data_query"] * 6, "query"]

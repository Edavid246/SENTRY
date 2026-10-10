"""Group home summary: one card per division the caller can see, an alert only when needed.

Expected counts are hand-authored from the seed rows (not derived from app.seed). Hidden
divisions are absent, never present-but-locked; no-data roles are refused like every other
data endpoint.
"""

from __future__ import annotations

from test_assistant_endpoints import _audit, _latest
from test_auth_endpoints import auth_header

PATH = "/api/v1/home/summary"
ALL_FIVE = ["briech", "stratoc", "giga", "poctova", "field-ops"]


def _home(client, username: str):
    return client.get(PATH, headers=auth_header(client, username))


def _cards(client, username: str) -> dict[str, dict]:
    response = _home(client, username)
    assert response.status_code == 200, response.text
    return {d["key"]: d for d in response.json()["divisions"]}


def _run_correlation(client) -> None:
    assert (
        client.post("/api/v1/correlation/run", headers=auth_header(client, "owner")).status_code
        == 200
    )


def test_owner_sees_all_five_cards_in_order(client) -> None:
    assert list(_cards(client, "owner")) == ALL_FIVE


def test_card_shape(client) -> None:
    card = _cards(client, "owner")["poctova"]
    assert set(card) == {"key", "name", "tagline", "alert"}
    assert set(card["alert"]) == {"count", "parts", "classification", "compartments"}
    assert card["alert"]["count"] == sum(p["count"] for p in card["alert"]["parts"])


def test_owner_alert_counts_come_from_the_typed_tools(client) -> None:
    _run_correlation(client)
    cards = _cards(client, "owner")
    counts = {
        key: {p["what"]: p["count"] for p in card["alert"]["parts"]} for key, card in cards.items()
    }
    assert counts["poctova"] == {
        "deliveries overdue": 2,
        "production runs on QC hold": 1,
        "findings open": 1,
    }
    assert counts["giga"] == {"deliveries overdue": 1, "custody breaks": 2, "findings open": 1}
    assert counts["stratoc"]["findings open"] == 1
    assert counts["field-ops"] == {"equipment overdue": 1, "stock lines short": 1}
    assert counts["briech"]["findings open"] == 1  # the QC hold behind the overdue airframes
    assert cards["briech"]["alert"]["count"] == 10


def test_alert_is_a_derived_item_and_inherits_the_highest_label(client) -> None:
    cards = _cards(client, "owner")
    giga = cards["giga"]["alert"]
    assert giga["classification"] == "secret"
    assert giga["compartments"] == ["CLIENT-D", "FORENSICS"]
    poctova = cards["poctova"]["alert"]
    assert poctova["classification"] == "confidential"
    assert poctova["compartments"] == ["CLIENT-C"]


def test_certifications_are_background_not_a_card_alert(client) -> None:
    for card in _cards(client, "owner").values():
        assert all("certification" not in p["what"] for p in card["alert"]["parts"])


def test_a_division_the_caller_cannot_see_is_absent(client) -> None:
    assert list(_cards(client, "briech.lead")) == ["briech"]
    assert list(_cards(client, "coo")) == ["field-ops"]
    assert list(_cards(client, "logistics.head")) == ["stratoc", "field-ops"]


def test_restricted_callers_get_smaller_counts_and_lower_labels(client) -> None:
    owner = _cards(client, "owner")["briech"]["alert"]
    lead = _cards(client, "briech.lead")["briech"]["alert"]
    assert lead["count"] == 6 < owner["count"]
    assert lead["classification"] == "confidential"
    assert "FORENSICS" not in lead["compartments"]


def test_site_level_user_never_sees_the_secret_finding_in_any_count(client) -> None:
    _run_correlation(client)
    card = _cards(client, "coo")["field-ops"]
    assert all(p["what"] != "findings open" for p in card["alert"]["parts"])
    assert card["alert"]["classification"] == "restricted"


def test_no_data_roles_are_refused(client) -> None:
    assert _home(client, "group.it").status_code == 403
    assert _home(client, "group.audit").status_code == 403


def test_unauthenticated_is_refused(client) -> None:
    assert client.get(PATH).status_code in (401, 403)


def test_read_and_denial_are_audited(client) -> None:
    assert _home(client, "briech.lead").status_code == 200
    assert _home(client, "group.it").status_code == 403
    events = _audit(client)
    decide = _latest(events, actor="briech.lead", action="decide", resource="dashboard")
    query = _latest(events, actor="briech.lead", action="query", resource="dashboard")
    assert decide["payload"]["decision"] == "allow"
    assert query["payload"]["rows"] == 6 and len(query["payload"]["item_ids"]) == 6
    deny = _latest(events, actor="group.it", action="decide", resource="dashboard")
    assert deny["payload"]["decision"] == "deny"

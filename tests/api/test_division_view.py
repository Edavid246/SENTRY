"""Division dashboards (Phase C): sections are typed-tool output, narrowed to the division.

Expected rows are hand-authored from the seed (app.seed, REC-083..092): Poctova has runs
REC-085 (released) and REC-086 (hold, helmet liner), and serials REC-091 and REC-092.
A division the caller cannot see answers 404, the same as one that does not exist.
"""

from __future__ import annotations

from test_auth_endpoints import auth_header

BASE = "/api/v1/divisions"


def _get(client, username: str, path: str):
    return client.get(f"{BASE}/{path}", headers=auth_header(client, username))


def _sections(client, username: str, key: str) -> dict[str, dict]:
    response = _get(client, username, key)
    assert response.status_code == 200, response.text
    return {s["key"]: s for s in response.json()["sections"]}


def _refs(section: dict) -> list[str]:
    return [r["ref"] for r in section["rows"]]


def test_poctova_sections_for_the_owner(client) -> None:
    sections = _sections(client, "owner", "poctova")
    assert list(sections) == [
        "qc-holds",
        "runs",
        "stock",
        "deliveries",
        "maintenance",
        "certifications",
    ]
    assert _refs(sections["qc-holds"]) == ["REC-086"]
    assert _refs(sections["runs"]) == ["REC-085", "REC-086"]
    assert [r["flagged"] for r in sections["runs"]["rows"]] == [False, True]
    assert sections["runs"]["flagged"] == 1
    assert len(sections["deliveries"]["rows"]) == 2


def test_section_is_a_derived_item_and_inherits_labels(client) -> None:
    sections = _sections(client, "owner", "poctova")
    assert sections["runs"]["classification"] == "confidential"
    assert sections["runs"]["compartments"] == []
    assert "CLIENT-C" in sections["deliveries"]["compartments"]


def test_empty_section_has_no_label(client) -> None:
    empty = [s for s in _sections(client, "owner", "poctova").values() if not s["rows"]]
    assert all(s["classification"] is None and s["compartments"] == [] for s in empty)


def test_hidden_and_unknown_divisions_read_the_same(client) -> None:
    hidden = _get(client, "briech.lead", "poctova")
    unknown = _get(client, "briech.lead", "nonesuch")
    assert hidden.status_code == unknown.status_code == 404
    assert hidden.json() == unknown.json()
    assert _get(client, "owner", "field-ops").status_code == 404  # no unit path of its own


def test_a_division_without_sections_yet_is_empty_not_missing(client) -> None:
    assert _get(client, "owner", "giga").json()["sections"] == []


def test_serial_trace_returns_one_row_with_delivery(client) -> None:
    body = _get(client, "owner", "poctova/trace?serial=PCT-ARM-0007").json()
    assert _refs(body) == ["REC-091"]
    assert "delivered to" in body["rows"][0]["detail"]


def test_hidden_serial_reads_like_a_missing_one(client) -> None:
    hidden = _get(client, "briech.lead", "briech/trace?serial=PCT-ARM-0007")
    missing = _get(client, "briech.lead", "briech/trace?serial=BRC-9999")
    assert hidden.status_code == missing.status_code == 200
    assert hidden.json()["rows"] == missing.json()["rows"] == []


def test_bad_serial_is_refused_without_a_query(client) -> None:
    assert _get(client, "owner", "poctova/trace?serial=not-a-serial").status_code == 422


def test_requires_login(client) -> None:
    assert client.get(f"{BASE}/poctova").status_code == 401

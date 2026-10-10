"""Forensic case workspace (Phase D): cases, evidence, chain of custody.

Expected values are hand-authored from the seed (app.seed, REC-007, REC-061/062 and REC-098..117):
three cases, six evidence items, and one planted custody break (REC-112: EV-017-01 reaches the lab
from a courier, but the last holder was examiner A. Danjuma). Everything is FORENSICS-only, so only
the owner sees any of it; for everyone else it is absent, and a hidden case answers 404.
"""

from __future__ import annotations

import pytest
from test_auth_endpoints import auth_header

API = "/api/v1"
CASES = ["FR-2026-009", "FR-2026-014", "FR-2026-017"]


def _get(client, username: str, path: str):
    return client.get(f"{API}/{path}", headers=auth_header(client, username))


def _sections(client, username: str) -> dict[str, dict]:
    response = _get(client, username, "divisions/giga")
    assert response.status_code == 200, response.text
    return {s["key"]: s for s in response.json()["sections"]}


def _refs(section: dict) -> list[str]:
    return [r["ref"] for r in section["rows"]]


def test_giga_sections_for_the_owner(client) -> None:
    sections = _sections(client, "owner")
    assert list(sections) == [
        "custody-breaks",
        "cases",
        "evidence",
        "maintenance",
        "certifications",
    ]
    # open cases first, then closed; the broken case is the flagged one
    assert _refs(sections["cases"]) == ["REC-007", "REC-098", "REC-099"]
    assert [r["flagged"] for r in sections["cases"]["rows"]] == [False, True, False]
    assert _refs(sections["evidence"]) == [
        "REC-104",  # EV-009-01
        "REC-061",  # EV-014-01
        "REC-100",
        "REC-101",
        "REC-102",  # EV-017-01 carries the break
        "REC-103",
    ]
    assert _refs(sections["custody-breaks"]) == ["REC-112"]
    assert sections["custody-breaks"]["rows"][0]["href"] == "/cases/FR-2026-017"
    assert sections["cases"]["rows"][1]["href"] == "/cases/FR-2026-017"


def test_forensic_sections_inherit_the_highest_label(client) -> None:
    sections = _sections(client, "owner")
    assert sections["cases"]["classification"] == "secret"
    assert sections["cases"]["compartments"] == ["FORENSICS"]
    assert sections["custody-breaks"]["classification"] == "confidential"


def test_the_giga_card_counts_custody_breaks(client) -> None:
    cards = {c["key"]: c for c in _get(client, "owner", "home/summary").json()["divisions"]}
    parts = {p["what"]: p["count"] for p in cards["giga"]["alert"]["parts"]}
    assert parts == {"deliveries overdue": 1, "custody breaks": 1}


def test_case_view_with_the_planted_break(client) -> None:
    body = _get(client, "owner", "cases/FR-2026-017").json()
    assert (body["ref"], body["state"], body["breaks"]) == ("REC-098", "open", 1)
    assert [e["evidence_ref"] for e in body["evidence"]] == ["EV-017-01", "EV-017-02"]
    broken, clean = body["evidence"]
    assert [s["ref"] for s in broken["steps"]] == ["REC-111", "REC-112"]
    assert broken["steps"][0]["expected_holder"] is None
    assert broken["steps"][1]["expected_holder"] == "A. Danjuma"
    assert broken["steps"][1]["from_holder"] == "Courier R. Bala"
    assert all(s["expected_holder"] is None for s in clean["steps"])


def test_case_view_is_a_derived_item_and_inherits_labels(client) -> None:
    secret = _get(client, "owner", "cases/FR-2026-014").json()
    assert (secret["classification"], secret["compartments"]) == ("secret", ["FORENSICS"])
    assert secret["breaks"] == 0
    confidential = _get(client, "owner", "cases/FR-2026-009").json()
    assert confidential["classification"] == "confidential"
    # the trail is date-ordered: seized, to the lab, then handed back
    steps = confidential["evidence"][0]["steps"]
    assert [s["action"] for s in steps] == [
        "seized",
        "transferred to lab",
        "returned to client",
    ]


@pytest.mark.parametrize("username", ["briech.lead", "logistics.head", "coo"])
def test_a_hidden_case_reads_like_a_missing_one(client, username: str) -> None:
    hidden = _get(client, username, "cases/FR-2026-014")
    missing = _get(client, username, "cases/FR-2099-999")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()


def test_a_malformed_case_ref_is_not_found(client) -> None:
    assert _get(client, "owner", "cases/not-a-case").status_code == 404


def test_other_roles_see_no_forensic_rows(client) -> None:
    assert _get(client, "briech.lead", "divisions/giga").status_code == 404


def test_every_forensic_record_carries_its_cases_label() -> None:
    """The break check reads only visible events, which is safe because a case's records agree."""
    from app import seed

    forensic = [r for r in seed.RECORDS if r[1] in {"Case", "EvidenceItem", "CustodyEvent"}]
    assert len(forensic) == 3 + 6 + 14
    case_label = {r[6]["case_ref"]: r[3] for r in forensic if r[1] == "Case"}
    assert set(case_label) == set(CASES)
    for ref, _entity, _source, classification, compartments, _unit, data in forensic:
        assert (classification, compartments) == (case_label[data["case_ref"]], ["FORENSICS"]), ref


def test_forensic_tool_parameters_are_validated(client) -> None:
    from app.data_queries.tools import forensics as tools

    assert tools._EVIDENCE_RE.match("EV-014-01") and not tools._EVIDENCE_RE.match("EV-14-1")
    assert tools._CASE_RE.match("FR-2026-014") and not tools._CASE_RE.match("FR-26-14")

"""Authorization matrix for the group-home endpoints: divisions, compliance, cases, reports.

The oracle is independent of the code under test: expected statuses are hand-derived from each
user's role and unit (a role without `read` gets 404, not 403, from these routes; a unit that does
not overlap a division cannot see it), and every record reference an endpoint returns must be in
the hand-authored gold visibility set (tests/authz/expected.py). A report's marking may never
exceed its caller's clearance.

Hand derivation, from the seed users:
  owner           /eib-group/               every division, every case
  logistics.head  /eib-group/stratoc/       Stratoc and Field Operations (sites below Stratoc)
  coo             /eib-group/stratoc/site-4/  the same two, narrower rows
  briech.lead     /eib-group/briech/        Briech only
  group.it        no `read` (sysadmin)      nothing
  group.audit     no `read` (auditor)       nothing
Cases are FORENSICS-compartmented and Giga-owned: only the owner is cleared for them.
"""

from __future__ import annotations

import pytest
from expected import GOLD_RECORDS
from test_auth_endpoints import auth_header

API = "/api/v1"
ALL = ["owner", "logistics.head", "coo", "briech.lead", "group.it", "group.audit"]
DIVISIONS = ["briech", "stratoc", "giga", "poctova", "field-ops"]
CASES = ["FR-2026-009", "FR-2026-014", "FR-2026-017"]

# Hand-authored: which divisions each user can open (all others answer 404).
VISIBLE_DIVISIONS: dict[str, set[str]] = {
    "owner": set(DIVISIONS),
    "logistics.head": {"stratoc", "field-ops"},
    "coo": {"stratoc", "field-ops"},
    "briech.lead": {"briech"},
    "group.it": set(),
    "group.audit": set(),
}
CAN_READ = {"owner", "logistics.head", "coo", "briech.lead"}

# Classification order, lowest first, and each user's clearance (seed users, hand-authored).
ORDER = ["unclassified", "restricted", "confidential", "secret"]  # secret = Government-sensitive
# How a marking names each level (the UI's wording), hand-authored.
SHOWN_AS = {
    "OPEN": "unclassified",
    "INTERNAL": "restricted",
    "CONFIDENTIAL": "confidential",
    "GOVERNMENT-SENSITIVE": "secret",
}
CLEARANCE = {
    "owner": "secret",
    "logistics.head": "confidential",
    "coo": "restricted",
    "briech.lead": "confidential",
}


def _get(client, username: str, path: str):
    return client.get(f"{API}/{path}", headers=auth_header(client, username))


@pytest.mark.parametrize("division", DIVISIONS)
@pytest.mark.parametrize("username", ALL)
def test_division_status_matrix(client, username: str, division: str) -> None:
    expected = 200 if division in VISIBLE_DIVISIONS[username] else 404
    assert _get(client, username, f"divisions/{division}").status_code == expected
    assert _get(client, username, f"reports/{division}").status_code == expected
    assert _get(client, username, f"reports/{division}/export?format=pdf").status_code == expected


@pytest.mark.parametrize("username", ALL)
def test_compliance_status_matrix(client, username: str) -> None:
    expected = 200 if username in CAN_READ else 404
    assert _get(client, username, "compliance").status_code == expected


@pytest.mark.parametrize("case_ref", CASES)
@pytest.mark.parametrize("username", ALL)
def test_case_status_matrix(client, username: str, case_ref: str) -> None:
    expected = 200 if username == "owner" else 404
    assert _get(client, username, f"cases/{case_ref}").status_code == expected


@pytest.mark.parametrize("username", sorted(CAN_READ))
def test_every_returned_record_is_in_the_gold_visibility_set(client, username: str) -> None:
    gold = GOLD_RECORDS[username]
    seen: set[str] = set()
    sections = _get(client, username, "compliance").json()["sections"]
    seen |= {r["ref"] for s in sections for r in s["rows"]}
    for division in VISIBLE_DIVISIONS[username]:
        page = _get(client, username, f"divisions/{division}").json()
        seen |= {r["ref"] for s in page["sections"] for r in s["rows"]}
        report = _get(client, username, f"reports/{division}").json()
        seen |= set(report["refs"])
    assert seen, "the endpoints returned no records at all"
    assert seen <= gold, sorted(seen - gold)


@pytest.mark.parametrize("username", sorted(CAN_READ))
def test_a_report_is_never_marked_above_its_callers_clearance(client, username: str) -> None:
    for division in VISIBLE_DIVISIONS[username]:
        report = _get(client, username, f"reports/{division}").json()
        assert ORDER.index(report["classification"]) <= ORDER.index(CLEARANCE[username])
        for section in report["sections"]:
            if section["marking"]:
                shown = section["marking"].split(" (")[0]
                assert ORDER.index(SHOWN_AS[shown]) <= ORDER.index(CLEARANCE[username])


def test_the_owners_case_records_are_all_in_the_gold_set(client) -> None:
    gold = GOLD_RECORDS["owner"]
    for case_ref in CASES:
        case = _get(client, "owner", f"cases/{case_ref}").json()
        refs = {case["ref"]} | {e["ref"] for e in case["evidence"]}
        refs |= {s["ref"] for e in case["evidence"] for s in e["steps"]}
        assert refs <= gold, sorted(refs - gold)


@pytest.mark.parametrize("username", ALL)
def test_a_denied_caller_gets_the_same_404_as_for_a_missing_page(client, username: str) -> None:
    """A role with no read gets the same body as a missing page, never a hint it exists."""
    if username in CAN_READ:
        pytest.skip("only denied roles")
    denied = _get(client, username, "reports/poctova")
    missing = _get(client, username, "reports/nonesuch")
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json()

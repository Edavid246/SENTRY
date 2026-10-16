"""Division dashboards (Phase C): sections are typed-tool output, narrowed to the division.

Expected rows are hand-authored from the seed (app.seed, REC-083..092): Poctova has runs
REC-085 (released) and REC-086 (hold, helmet liner), and serials REC-091 and REC-092.
A division the caller cannot see answers 404, the same as one that does not exist.
"""

from __future__ import annotations

from support.http import get, run_correlation
from support.responses import section_refs, sections_by_key

BASE = "/api/v1/divisions"


def _sections(client, username: str, key: str) -> dict[str, dict]:
    return sections_by_key(get(client, username, f"{BASE}/{key}"))


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
    assert section_refs(sections["qc-holds"]) == ["REC-086"]
    assert section_refs(sections["runs"]) == ["REC-085", "REC-086"]
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
    hidden = get(client, "briech.lead", f"{BASE}/poctova")
    unknown = get(client, "briech.lead", f"{BASE}/nonesuch")
    assert hidden.status_code == unknown.status_code == 404
    assert hidden.json() == unknown.json()


def test_serial_trace_returns_one_row_with_delivery(client) -> None:
    body = get(client, "owner", f"{BASE}/poctova/trace?serial=PCT-ARM-0007").json()
    assert section_refs(body) == ["REC-091"]
    assert "delivered to" in body["rows"][0]["detail"]


def test_hidden_serial_reads_like_a_missing_one(client) -> None:
    hidden = get(client, "briech.lead", f"{BASE}/briech/trace?serial=PCT-ARM-0007")
    missing = get(client, "briech.lead", f"{BASE}/briech/trace?serial=BRC-9999")
    assert hidden.status_code == missing.status_code == 200
    assert hidden.json()["rows"] == missing.json()["rows"] == []


def test_bad_serial_is_refused_without_a_query(client) -> None:
    assert get(client, "owner", f"{BASE}/poctova/trace?serial=not-a-serial").status_code == 422


def test_requires_login(client) -> None:
    assert client.get(f"{BASE}/poctova").status_code == 401


def test_briech_sections_for_the_owner(client) -> None:
    sections = _sections(client, "owner", "briech")
    assert list(sections) == [
        "fleet",
        "missions",
        "deliveries",
        "contracts",
        "maintenance",
        "certifications",
    ]
    # REC-009 has no service interval (no gauge); REC-095 is 492 of 500 hours (a nearly full gauge).
    assert section_refs(sections["fleet"]) == ["REC-009", "REC-095"]
    assert [r["meter"] for r in sections["fleet"]["rows"]] == [None, 0.984]
    assert [r["flagged"] for r in sections["fleet"]["rows"]] == [False, True]
    assert section_refs(sections["contracts"]) == ["REC-063", "REC-064", "REC-065"]
    assert [r["flagged"] for r in sections["contracts"]["rows"]] == [False, True, False]


def test_briech_lead_sees_fewer_rows_and_a_lower_label(client) -> None:
    sections = _sections(client, "briech.lead", "briech")
    assert section_refs(sections["fleet"]) == [
        "REC-009"
    ]  # the Secret airframe is absent, not locked
    assert sections["fleet"]["classification"] == "confidential"
    assert sections["deliveries"]["compartments"] == ["CLIENT-A"]
    assert section_refs(sections["maintenance"]) == []


def test_stratoc_sections_and_finding_link(client) -> None:

    run_correlation(client)
    sections = _sections(client, "owner", "stratoc")
    assert list(sections) == ["findings", "detections", "sensors", "maintenance", "certifications"]
    (finding,) = sections["findings"]["rows"]
    assert finding["href"] == "/findings/FND-RISING-FAULTS-SITE-4"
    assert sections["findings"]["classification"] == "secret"  # inherits its Secret input
    assert section_refs(sections["sensors"]) == ["REC-047", "REC-046"]
    assert set(section_refs(sections["detections"])) == {
        "REC-048", "REC-049", "REC-051", "REC-052", "REC-054",
    }  # fmt: skip
    assert all(not r["flagged"] for r in sections["detections"]["rows"])


def test_coo_never_sees_the_secret_finding_on_the_stratoc_page(client) -> None:

    run_correlation(client)
    sections = _sections(client, "coo", "stratoc")
    assert sections["findings"]["rows"] == []
    assert sections["findings"]["classification"] is None


def test_field_operations_owner_view(client) -> None:
    body = get(client, "owner", f"{BASE}/field-ops").json()
    assert body["facts"] == [
        {"label": "Field sites", "value": "Stratoc Site Team 4"},
        {"label": "Supporting", "value": "EIB Stratoc"},
        {"label": "Personnel", "value": "5"},
    ]
    sections = {s["key"]: s for s in body["sections"]}
    assert list(sections) == ["personnel", "training", "stock", "maintenance"]
    # Site Team 4 rows only: Stratoc-level (REC-021/022) and Briech (REC-023) people are not here.
    assert section_refs(sections["personnel"]) == [
        "REC-019",
        "REC-041",
        "REC-020",
        "REC-042",
        "REC-025",
    ]
    assert [r["flagged"] for r in sections["personnel"]["rows"]] == [True, True, True, True, False]
    assert section_refs(sections["stock"]) == ["REC-026"]


def test_field_operations_for_the_site_commander_hides_the_confidential_row(client) -> None:
    sections = _sections(client, "coo", "field-ops")
    # Confidential: absent, not locked.
    assert "REC-015" not in section_refs(sections["maintenance"])
    assert sections["maintenance"]["classification"] == "restricted"


def test_field_operations_hidden_from_a_division_lead(client) -> None:
    assert get(client, "briech.lead", f"{BASE}/field-ops").status_code == 404
    assert get(client, "group.audit", f"{BASE}/field-ops").status_code == 404

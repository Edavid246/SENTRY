"""Forensic questions reach the forensic tools, and only the owner's data answers them.

Routing is the demo's deterministic keyword router (docs/PRODUCTION_DEBT.md); authorization is
not in it: the tools search on the caller's own scope, so the same question from a caller who is
not cleared for FORENSICS returns an empty table and the model is never given a forensic row.
"""

from __future__ import annotations

import pytest
from app.data_queries.routing import route_question
from fakes import FakeLLM
from test_assistant_endpoints import _ask


@pytest.fixture
def explain_calls(models) -> list:
    llm = FakeLLM()
    models(llm)
    return llm.explained


@pytest.mark.parametrize(
    ("question", "tool", "params"),
    [
        ("Which evidence has a custody break?", "custody_gaps", {}),
        ("Show me any gaps in the chain of custody", "custody_gaps", {}),
        ("Show the custody trail for EV-017-01", "custody_trail", {"evidence_ref": "EV-017-01"}),
        (
            "What is the chain of custody for ev-014-02?",
            "custody_trail",
            {"evidence_ref": "EV-014-02"},
        ),
        ("List the evidence items", "evidence_items", {}),
        ("List the evidence in case FR-2026-017", "evidence_items", {"case_ref": "FR-2026-017"}),
        ("Show me the forensic cases", "forensic_cases", {}),
        ("Which open cases are there for forensics?", "forensic_cases", {}),
    ],
)
def test_routing_to_forensic_tools(question, tool, params) -> None:
    routed = route_question(question)
    assert routed is not None and routed.tool == tool and routed.params == params


@pytest.mark.parametrize(
    ("question", "tool"),
    [
        ("Show equipment due for maintenance", "equipment_due_for_maintenance"),
        ("Trace serial PCT-ARM-0007", "serial_trace"),
        ("List the production runs on QC hold", "production_qc_holds"),
        ("Show contracts that are at risk", "contracts_status"),
    ],
)
def test_other_questions_still_route_where_they_did(question, tool) -> None:
    routed = route_question(question)
    assert routed is not None and routed.tool == tool


@pytest.mark.parametrize(
    "question",
    [
        "What is the policy on evidence handling?",  # a document question stays on knowledge
        "Summarize the use cases for the drones",
    ],
)
def test_unrelated_questions_do_not_reach_forensic_tools(question) -> None:
    routed = route_question(question)
    assert routed is None or not routed.tool.startswith(("custody", "evidence", "forensic"))


@pytest.mark.parametrize(
    "question",
    [
        "What evidence is there for the training report?",
        "Summarize the evidence behind this answer",
        "What is the custody of the drone?",  # 'custody' alone, no EV number, no break word
        "Who has custody",
    ],
)
def test_prose_about_evidence_or_custody_stays_on_knowledge(question) -> None:
    routed = route_question(question)
    assert routed is None or not routed.tool.startswith(("custody", "evidence", "forensic"))


def test_a_case_number_filters_the_case_list() -> None:
    routed = route_question("Show case FR-2026-017")
    assert routed is not None and routed.tool == "forensic_cases"
    assert routed.params == {"case_ref": "FR-2026-017"}


def test_the_case_tool_returns_only_the_requested_case(client, explain_calls) -> None:
    every = _ask(client, "owner", "Show me the forensic cases").json()["result_table"]["rows"]
    one = _ask(client, "owner", "Show case FR-2026-017").json()["result_table"]["rows"]
    assert len(every) > 1
    assert [row["case_ref"] for row in one] == ["FR-2026-017"]


def test_the_owner_gets_the_planted_break_through_the_assistant(client, explain_calls) -> None:
    response = _ask(client, "owner", "Which evidence has a custody break?")
    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body["result_table"]["rows"]] == ["REC-112"]
    row = body["result_table"]["rows"][0]
    assert (row["evidence_ref"], row["recorded_holder"], row["expected_holder"]) == (
        "EV-017-01",
        "Courier R. Bala",
        "A. Danjuma",
    )
    assert explain_calls == ["custody_gaps"]


@pytest.mark.parametrize("username", ["briech.lead", "logistics.head", "coo"])
def test_a_caller_without_forensics_gets_an_empty_table(client, explain_calls, username) -> None:
    for question in (
        "Which evidence has a custody break?",
        "Show the custody trail for EV-017-01",
        "Show me the forensic cases",
        "List the evidence items",
    ):
        response = _ask(client, username, question)
        assert response.status_code == 200
        assert response.json()["result_table"]["rows"] == []
    assert explain_calls == []  # no rows, no model call


def test_a_malformed_evidence_ref_is_refused(client, explain_calls) -> None:
    response = _ask(client, "owner", "Show the custody trail for EV-17-1")
    assert response.status_code == 200
    # not an evidence number, so the router does not send it to custody_trail
    assert (
        response.json().get("result_table") is None or response.json()["result_table"]["rows"] == []
    )

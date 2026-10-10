"""Contracts and deliveries (pivot Task 4): typed tools, client separation, routing.

Client agencies are generic labels mapped to CLIENT-A..D compartments. Only the owner holds
all four; briech.lead holds CLIENT-A, so sees Client Agency A's Briech contracts and nothing
for the other clients. The expected sets are hand-authored from the seed table
(app.seed, REC-063..082) and pinned in tests/authz/expected.py.
"""

from __future__ import annotations

import pytest
from app.data_queries.errors import ToolParamError
from app.data_queries.routing import route_question
from app.data_queries.tools import TOOLS
from scoped import run_tool, scoped
from test_assistant_endpoints import _ask
from test_connected_data import _ctx, explain_calls  # noqa: F401

OVERDUE_QUESTION = "Which deliveries are overdue?"
CONTRACT_QUESTION = "Show me the contracts and their status"

DELIVERY_COLUMNS = [
    "id",
    "delivery_ref",
    "contract_ref",
    "client",
    "item",
    "quantity",
    "due_date",
    "days_overdue",
    "status",
    "unit_path",
]
CONTRACT_COLUMNS = [
    "id",
    "contract_ref",
    "client",
    "subject",
    "status",
    "end_date",
    "value_musd",
    "unit_path",
]

# DL-101/103/105 (Briech), 201/204 (Poctova), 301 (Stratoc), 401 (Giga): past due, not delivered.
OWNER_OVERDUE = {"REC-071", "REC-073", "REC-075", "REC-076", "REC-079", "REC-081", "REC-082"}
BRIECH_LEAD_OVERDUE = {"REC-071", "REC-073"}  # Client Agency A only
OWNER_CONTRACTS = {f"REC-0{n}" for n in range(63, 71)}


def _ids(body: dict) -> set[str]:
    return {row["id"] for row in body["result_table"]["rows"]}


def test_overdue_deliveries_by_user(client, explain_calls) -> None:  # noqa: F811
    owner = _ask(client, "owner", OVERDUE_QUESTION).json()
    lead = _ask(client, "briech.lead", OVERDUE_QUESTION).json()
    assert owner["result_table"]["columns"] == DELIVERY_COLUMNS
    assert _ids(owner) == OWNER_OVERDUE
    assert _ids(lead) == BRIECH_LEAD_OVERDUE
    # oldest due date first; days_overdue counts from the due date, delivered rows never appear
    rows = owner["result_table"]["rows"]
    assert [r["delivery_ref"] for r in rows][0] == "DL-201"  # 15 days overdue
    assert rows[0]["days_overdue"] == 15
    assert all(r["status"] != "delivered" for r in rows)


@pytest.mark.parametrize("username", ["coo", "logistics.head"])
def test_users_without_client_compartments_see_no_deliveries_or_contracts(
    client,
    explain_calls,  # noqa: F811
    username,
) -> None:
    for question in (OVERDUE_QUESTION, CONTRACT_QUESTION):
        body = _ask(client, username, question).json()
        assert body["refused"] is False
        assert not (body["result_table"] or {}).get("rows")


def test_contracts_by_user_client_and_status(client, explain_calls) -> None:  # noqa: F811
    owner = _ask(client, "owner", CONTRACT_QUESTION).json()
    assert owner["result_table"]["columns"] == CONTRACT_COLUMNS
    assert _ids(owner) == OWNER_CONTRACTS
    lead = _ask(client, "briech.lead", CONTRACT_QUESTION).json()
    assert _ids(lead) == {"REC-063", "REC-064"}
    at_risk = _ask(client, "owner", "List the contracts that are at risk").json()
    assert _ids(at_risk) == {"REC-064", "REC-068"}
    done = _ask(client, "owner", "Which contracts are completed?").json()
    assert _ids(done) == {"REC-067"}


def test_client_filter_never_widens_visibility(client, explain_calls) -> None:  # noqa: F811
    c = _ask(client, "owner", "Which deliveries are overdue for Client Agency C?").json()
    assert _ids(c) == {"REC-076", "REC-079"}
    # another client's data is simply absent for a user without that compartment
    b = _ask(client, "briech.lead", "Which deliveries are overdue for Client Agency B?").json()
    assert _ids(b) == set()
    a = _ask(client, "briech.lead", "Which deliveries are overdue for Client Agency A?").json()
    assert _ids(a) == BRIECH_LEAD_OVERDUE


@pytest.mark.parametrize(
    ("tool", "params"),
    [
        ("deliveries_overdue", {"client": "Client Agency A'; DROP TABLE x;--"}),
        ("deliveries_overdue", {"client": 7}),
        ("deliveries_overdue", {"client": ["Client Agency A"]}),
        ("deliveries_overdue", {"surprise": 1}),
        ("deliveries_overdue", {"unit_path": "/eib-group/poctova/"}),  # outside briech.lead's unit
        ("contracts_status", {"status": "exploded"}),
        ("contracts_status", {"client": "../../x"}),
        ("contracts_status", {"unit_path": "/eib-group/"}),
    ],
)
def test_bad_params_are_refused_with_a_denied_audit_event(client, app_engine, tool, params) -> None:
    ctx = _ctx(client, app_engine, "briech.lead")
    outcome, _ = run_tool(app_engine, ctx, tool, params)
    assert outcome.refused and outcome.result is None
    with pytest.raises(ToolParamError), scoped(app_engine, ctx) as scope:
        TOOLS[tool](scope, params)


@pytest.mark.parametrize(
    ("question", "tool", "params"),
    [
        (OVERDUE_QUESTION, "deliveries_overdue", {}),
        ("Show late shipments", "deliveries_overdue", {}),
        (
            "List delayed deliveries for client agency b",
            "deliveries_overdue",
            {"client": "Client Agency B"},
        ),
        (CONTRACT_QUESTION, "contracts_status", {}),
        (
            "Which contracts for Client Agency D are active?",
            "contracts_status",
            {"client": "Client Agency D", "status": "active"},
        ),
        ("Show contracts that are at risk", "contracts_status", {"status": "at_risk"}),
    ],
)
def test_routing_to_contract_tools(question, tool, params) -> None:
    routed = route_question(question)
    assert routed is not None and routed.tool == tool and routed.params == params


@pytest.mark.parametrize(
    ("question", "tool"),
    [
        ("Show equipment due for maintenance", "equipment_due_for_maintenance"),
        ("Which stock is low in inventory?", "stock_below_threshold"),
        ("List UAS missions cancelled this week", "uas_missions"),
    ],
)
def test_existing_questions_still_route_where_they_did(question, tool) -> None:
    routed = route_question(question)
    assert routed is not None and routed.tool == tool and "client" not in routed.params


def test_contract_policy_questions_stay_on_the_knowledge_pathway() -> None:
    assert route_question("What does the contract policy document say about deliveries?") is None


def test_dashboard_overdue_deliveries_tile(client) -> None:
    from test_auth_endpoints import auth_header

    def tile(user):
        body = client.get("/api/v1/dashboard/summary", headers=auth_header(client, user)).json()
        return {i["id"]: i for i in body["tiles"]["overdue_deliveries"]["items"]}

    owner = tile("owner")
    assert {k: v["value"] for k, v in owner.items()} == {
        "DLV-BRIECH": 3,
        "DLV-POCTOVA": 2,
        "DLV-STRATOC": 1,
        "DLV-GIGA": 1,
    }
    # derived counts inherit the highest classification and the union of compartments
    assert owner["DLV-GIGA"]["classification"] == "secret"
    assert owner["DLV-GIGA"]["compartments"] == ["CLIENT-D", "FORENSICS"]
    assert owner["DLV-BRIECH"]["compartments"] == ["CLIENT-A", "CLIENT-B"]
    lead = tile("briech.lead")
    assert {k: v["value"] for k, v in lead.items()} == {"DLV-BRIECH": 2}
    assert lead["DLV-BRIECH"]["compartments"] == ["CLIENT-A"]
    assert tile("coo") == {}

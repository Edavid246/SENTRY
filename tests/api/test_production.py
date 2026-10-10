"""Manufacturing and serial traceability (pivot Task 5): typed tools, visibility, routing.

Expected sets are hand-authored from the seed table (app.seed, REC-083..092) and the oracle in
tests/authz/expected.py. briech.lead sees Briech runs/serials that are unassigned or delivered
to Client Agency A; Poctova rows are outside its unit, and nobody else holds CLIENT compartments.
"""

from __future__ import annotations

import pytest
from app.data_queries.errors import ToolParamError
from app.data_queries.routing import route_question
from app.data_queries.tools import TOOLS
from scoped import run_tool, scoped
from test_assistant_endpoints import _ask
from test_connected_data import _ctx

SERIAL_COLUMNS = [
    "id",
    "serial",
    "product",
    "run_ref",
    "qc_status",
    "delivered_to",
    "delivery_ref",
    "unit_path",
]
HOLD_COLUMNS = [
    "id",
    "run_ref",
    "product",
    "quantity",
    "qc_status",
    "hold_reason",
    "serials_traced",
    "unit_path",
]


def _rows(body: dict) -> list[dict]:
    return (body["result_table"] or {}).get("rows") or []


def test_serial_trace_owner_sees_run_qc_and_delivery(client, explain_calls) -> None:  # noqa: F811
    body = _ask(client, "owner", "Trace serial BRC-0041").json()
    assert body["result_table"]["columns"] == SERIAL_COLUMNS
    (row,) = _rows(body)
    assert row["id"] == "REC-087"
    assert (row["run_ref"], row["qc_status"]) == ("PR-BR-014", "released")
    assert (row["delivered_to"], row["delivery_ref"]) == ("Client Agency A", "DL-101")
    poctova = _rows(_ask(client, "owner", "Trace serial PCT-ARM-0007").json())
    assert [r["id"] for r in poctova] == ["REC-091"]
    assert poctova[0]["delivered_to"] == "Client Agency C"


def test_hidden_serial_looks_like_a_missing_one(client, explain_calls) -> None:  # noqa: F811
    # PCT-ARM-0007 exists but is outside briech.lead's unit; BRC-9999 does not exist.
    hidden = _ask(client, "briech.lead", "Trace serial PCT-ARM-0007").json()
    missing = _ask(client, "briech.lead", "Trace serial BRC-9999").json()
    assert hidden["refused"] is False and missing["refused"] is False
    assert _rows(hidden) == [] and _rows(missing) == []
    for user in ("coo", "logistics.head"):
        assert _rows(_ask(client, user, "Trace serial BRC-0041").json()) == []


def test_briech_lead_cannot_see_serials_delivered_to_other_clients(client, explain_calls) -> None:  # noqa: F811
    for serial, expected in (("BRC-0041", 1), ("BRC-0043", 1), ("BRC-0051", 1)):
        assert len(_rows(_ask(client, "briech.lead", f"Trace serial {serial}").json())) == expected


def test_qc_holds_by_user(client, explain_calls) -> None:  # noqa: F811
    owner = _ask(client, "owner", "Which production runs are on QC hold?").json()
    assert owner["result_table"]["columns"] == HOLD_COLUMNS
    rows = {r["id"]: r for r in _rows(owner)}
    assert set(rows) == {"REC-084", "REC-086"}
    assert rows["REC-084"]["hold_reason"] == "gimbal bracket torque out of tolerance"
    assert rows["REC-084"]["serials_traced"] == 1  # only BRC-0051 is traced to PR-BR-015
    lead = _rows(_ask(client, "briech.lead", "Show production holds").json())
    assert [r["id"] for r in lead] == ["REC-084"]
    for user in ("coo", "logistics.head"):
        assert _rows(_ask(client, user, "Show production holds").json()) == []


@pytest.mark.parametrize(
    ("tool", "params"),
    [
        ("serial_trace", {}),
        ("serial_trace", {"serial": "BRC-0041'; DROP TABLE x;--"}),
        ("serial_trace", {"serial": 41}),
        ("serial_trace", {"serial": ["BRC-0041"]}),
        ("serial_trace", {"serial": "brc-0041"}),
        ("serial_trace", {"serial": "BRC-0041", "surprise": 1}),
        ("serial_trace", {"serial": "BRC-0041", "unit_path": "/eib-group/poctova/"}),
        ("production_qc_holds", {"serial": "BRC-0041"}),
        ("production_qc_holds", {"unit_path": "/eib-group/"}),
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
        ("Trace serial BRC-0041", "serial_trace", {"serial": "BRC-0041"}),
        ("show the traceability for pct-arm-0007", "serial_trace", {"serial": "PCT-ARM-0007"}),
        ("Which batches are on hold?", "production_qc_holds", {}),
        ("List production runs on QC hold", "production_qc_holds", {}),
    ],
)
def test_routing_to_production_tools(question, tool, params) -> None:
    routed = route_question(question)
    assert routed is not None and routed.tool == tool and routed.params == params


def test_production_routing_does_not_capture_other_questions() -> None:
    assert route_question("Which deliveries are overdue?").tool == "deliveries_overdue"
    assert route_question("Show contracts at risk").tool == "contracts_status"
    assert route_question("Show equipment due for maintenance").tool == (
        "equipment_due_for_maintenance"
    )
    assert route_question("What does the QC policy say about holds?") is None

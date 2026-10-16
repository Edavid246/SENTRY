"""A dashboard never shows tool rows the policy would not let the caller query (refactor D3).

The dashboard routes decide only `read` on `dashboard`; the typed tools they run need `query` on
`record`. `execute_tool` decides that requirement itself before the tool runs, so a caller whose
policy allows the dashboard but withholds record queries gets the page with no tool rows, and
the denial is in the audit trail. No current role is in that position: every role with `read`
also has `query`, so the policy here withholds it for everyone.
"""

from __future__ import annotations

import pytest
from app.authz import scope as scope_module
from support.audit import audit_events, audit_tip
from support.http import get
from support.policies import WITHHELD, Withholding


@pytest.fixture
def no_record_queries(monkeypatch) -> None:
    policy = Withholding(scope_module.get_policy(), ("query", "record"))
    monkeypatch.setattr(scope_module, "get_policy", lambda: policy)


def _owner_events_since(client, tip: int) -> list[dict]:
    return [
        e["payload"]
        for e in sorted(audit_events(client), key=lambda e: e["seq"])
        if e["seq"] > tip and e["payload"]["actor"] == "owner" and e["payload"]["action"] != "login"
    ]


def test_division_page_has_no_tool_rows_and_the_denial_is_audited(
    client, no_record_queries
) -> None:
    tip = audit_tip(client)
    response = get(client, "owner", "/api/v1/divisions/poctova")
    assert response.status_code == 200, response.text
    sections = response.json()["sections"]
    assert sections and all(s["rows"] == [] for s in sections)

    events = _owner_events_since(client, tip)
    decides = [
        (e["requested"], e["resource"], e["decision"]) for e in events if e["action"] == "decide"
    ]
    assert decides == [("read", "dashboard", "allow"), ("query", "record", "deny")]
    assert next(e for e in events if e["decision"] == "deny")["reasons"] == [WITHHELD]
    queries = [e for e in events if e["action"] == "data_query"]
    assert len(queries) == len(sections) and all(q["decision"] == "deny" for q in queries)


def test_home_counts_nothing_from_the_tools(client, no_record_queries) -> None:
    response = get(client, "owner", "/api/v1/home/summary")
    assert response.status_code == 200, response.text
    for division in response.json()["divisions"]:
        parts = division["alert"]["parts"] if division["alert"] else []
        # findings come from the findings store under the dashboard read, not from a tool
        assert {p["what"] for p in parts} <= {"findings open"}


def test_serial_trace_is_refused(client, no_record_queries) -> None:
    response = get(client, "owner", "/api/v1/divisions/poctova/trace?serial=PCT-ARM-0007")
    assert response.status_code == 422

"""Connected-technology data pathway (SPEC 10.5, 11.3): UAS missions and surveillance detections.

Synthetic ONVIF-style detections and MAVLink/MISB-style missions reach the assistant only
through the adapter and typed tools, so these prove (as test_data_pathway does for the
logistics tools) that:

  * the same question returns fewer rows for a lower-cleared user, and compartment-marked
    UAS-OPS data never reaches a user without that compartment;
  * the returned sets equal the hand-authored oracle in tests/authz/expected.py;
  * hostile or out-of-range parameters are a safe, audited refusal;
  * routing sends UAS and surveillance questions to the right tool.

The model is stubbed. Seed dates are offsets from the demo date/noon (app.seed), so the
sets are stable on any day.
"""

from __future__ import annotations

import pytest
from app.authz.tokens import DevTokenValidator
from app.data_queries.errors import ToolParamError
from app.data_queries.explain import Explanation
from app.data_queries.registry import execute_tool
from app.data_queries.routing import route_question
from test_assistant_endpoints import _ask
from test_auth_endpoints import auth_header

CANCELLED_QUESTION = "How many UAS missions were cancelled this week, and where did they fly?"
DETECTION_QUESTION = "Summarize detections near DEP-B4 in the last 48 hours"
ALL_DETECTIONS_QUESTION = "Show me the surveillance detections in the last 48 hours"

MISSION_COLUMNS = [
    "id",
    "mission",
    "platform",
    "status",
    "mission_date",
    "area",
    "reason",
    "unit_path",
]
DETECTION_COLUMNS = [
    "id",
    "observed_at",
    "site",
    "sensor_id",
    "object_type",
    "confidence",
    "unit_path",
]


@pytest.fixture
def explain_calls(monkeypatch) -> list:
    calls: list = []

    def stub(question, result, *, gateway=None):
        calls.append(result.tool)
        return Explanation(text=f"Stub: {len(result.rows)} row(s).", provider="stub", model="s-1")

    monkeypatch.setattr("app.api.assistant.explain_result", stub)
    return calls


def _ids(body: dict) -> set[str]:
    return {row["id"] for row in body["result_table"]["rows"]}


def _ctx(client, app_engine, username: str):
    token = auth_header(client, username)["Authorization"].split(" ", 1)[1]
    with app_engine.connect() as conn:
        return DevTokenValidator().validate(token, conn=conn)


# --- UAS missions -----------------------------------------------------------


def test_cancelled_missions_this_week_by_user(client, explain_calls) -> None:
    bello = _ask(client, "a.bello", CANCELLED_QUESTION).json()
    musa = _ask(client, "k.musa", CANCELLED_QUESTION).json()
    # 056 and 057 are Confidential UAS-OPS; 060 is Secret (Bello only); 059 is 40 days old
    assert bello["result_table"]["columns"] == MISSION_COLUMNS
    assert _ids(bello) == {"REC-056", "REC-057", "REC-060"}
    assert _ids(musa) == {"REC-056", "REC-057"}
    assert all(row["status"] == "cancelled" for row in bello["result_table"]["rows"])
    assert explain_calls == ["uas_missions"] * 2


@pytest.mark.parametrize("username", ["t.adeyemi", "a.okafor"])
def test_users_without_uas_ops_get_no_missions(client, explain_calls, username) -> None:
    body = _ask(client, username, CANCELLED_QUESTION).json()
    assert body["result_table"]["rows"] == []
    assert body["refused"] is False
    assert "Gimbal" not in body["answer"] and "gimbal" not in body["answer"]


def test_missions_default_window_is_thirty_days(client, app_engine) -> None:
    ctx = _ctx(client, app_engine, "a.bello")
    with app_engine.connect() as conn:
        outcome = execute_tool(ctx, conn, "uas_missions", {})
    assert {row["id"] for row in outcome.result.rows} == {
        "REC-055",
        "REC-056",
        "REC-057",
        "REC-058",
        "REC-060",
    }  # REC-059 is 40 days old
    with app_engine.connect() as conn:
        wide = execute_tool(ctx, conn, "uas_missions", {"period_days": 60, "status": "completed"})
    assert {row["id"] for row in wide.result.rows} == {"REC-055", "REC-058"}


# --- detections -------------------------------------------------------------


def test_detections_scoped_by_clearance_unit_and_compartment(client, explain_calls) -> None:
    ask = lambda user: _ids(_ask(client, user, ALL_DETECTIONS_QUESTION).json())  # noqa: E731
    # 050 is 70 h old; 053 is UAS-OPS; 054 is Confidential (above Adeyemi's Restricted)
    assert ask("a.bello") == {"REC-048", "REC-049", "REC-051", "REC-052", "REC-053", "REC-054"}
    assert ask("a.okafor") == {"REC-048", "REC-049", "REC-051", "REC-052", "REC-054"}
    assert ask("t.adeyemi") == {"REC-048", "REC-049"}
    assert ask("k.musa") == {"REC-053"}


def test_detections_near_a_site_and_window(client, explain_calls) -> None:
    body = _ask(client, "a.bello", DETECTION_QUESTION).json()
    assert body["result_table"]["columns"] == DETECTION_COLUMNS
    assert _ids(body) == {"REC-048", "REC-049", "REC-054"}  # DEP-B4, newest first
    assert [row["id"] for row in body["result_table"]["rows"]] == ["REC-054", "REC-048", "REC-049"]
    longer = _ask(client, "a.bello", "Show detections near DEP-B4 in the last 100 hours").json()
    assert _ids(longer) == {"REC-048", "REC-049", "REC-050", "REC-054"}


# --- safe refusals ----------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "params"),
    [
        ("detections_near_site", {"site": "DEP-B4; DROP TABLE x"}),
        ("detections_near_site", {"site": "../../etc"}),
        ("detections_near_site", {"period_hours": 0}),
        ("detections_near_site", {"period_hours": 10**6}),
        ("detections_near_site", {"period_hours": True}),
        ("detections_near_site", {"surprise": 1}),
        ("uas_missions", {"status": "exploded"}),
        ("uas_missions", {"period_days": -1}),
        ("uas_missions", {"period_days": "30"}),
        ("uas_missions", {"unit_path": "/command-a/"}),  # outside Adeyemi's unit scope
    ],
)
def test_bad_params_are_refused_with_a_denied_audit_event(client, app_engine, tool, params) -> None:
    ctx = _ctx(client, app_engine, "t.adeyemi")
    with app_engine.connect() as conn:
        outcome = execute_tool(ctx, conn, tool, params)
    assert outcome.refused and outcome.result is None
    with pytest.raises(ToolParamError):
        from app.data_queries.registry import REGISTRY

        with app_engine.connect() as conn:
            REGISTRY[tool](ctx, params, conn)


# --- routing ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "tool", "params"),
    [
        (CANCELLED_QUESTION, "uas_missions", {"status": "cancelled", "period_days": 7}),
        (
            "Which UAS missions were cancelled this month and why?",
            "uas_missions",
            {"status": "cancelled", "period_days": 30},
        ),
        ("List the drone flights from the past 14 days", "uas_missions", {"period_days": 14}),
        (DETECTION_QUESTION, "detections_near_site", {"site": "DEP-B4", "period_hours": 48}),
        ("Show sensor detections at dep-b2", "detections_near_site", {"site": "DEP-B2"}),
    ],
)
def test_routing_to_connected_tools(question, tool, params) -> None:
    routed = route_question(question)
    assert routed is not None and routed.tool == tool
    assert routed.params == params


@pytest.mark.parametrize(
    "question",
    [
        "Find the UAS maintenance schedule document",
        "What does the UAS contingency policy say about launch criteria?",
    ],
)
def test_document_questions_about_uas_stay_on_the_knowledge_pathway(question) -> None:
    assert route_question(question) is None


# --- map GeoJSON ------------------------------------------------------------

MAP_PATH = "/api/v1/connected/map"


def _map(client, username: str, **params):
    return client.get(MAP_PATH, params=params, headers=auth_header(client, username))


def _refs(response) -> set[str]:
    return {f["properties"]["ref"] for f in response.json()["features"]}


def test_map_features_equal_the_oracle_per_user(client) -> None:
    assert _refs(_map(client, "a.bello")) == {
        *("REC-046", "REC-047"),  # sensors
        *("REC-048", "REC-049", "REC-051", "REC-052", "REC-053", "REC-054"),  # detections <= 48 h
        *("REC-055", "REC-056", "REC-057", "REC-058", "REC-060"),  # missions <= 30 days
    }
    assert _refs(_map(client, "t.adeyemi")) == {"REC-046", "REC-048", "REC-049"}
    assert _refs(_map(client, "k.musa")) == {
        *("REC-053", "REC-055", "REC-056", "REC-057", "REC-058")  # no Secret 060
    }


def test_map_geometry_shapes_and_window(client) -> None:
    body = _map(client, "a.bello", hours=100, mission_days=60).json()
    assert body["type"] == "FeatureCollection"
    kinds = {f["properties"]["kind"]: f["geometry"]["type"] for f in body["features"]}
    assert kinds == {"sensor": "Point", "detection": "Point", "mission": "LineString"}
    refs = {f["properties"]["ref"] for f in body["features"]}
    assert {"REC-050", "REC-059"} <= refs  # 70 h old detection, 40-day-old mission
    for feature in body["features"]:
        assert {"classification", "compartments", "unit_path"} <= set(feature["properties"])


@pytest.mark.parametrize("username", ["s.eze", "f.danjuma"])
def test_map_is_empty_for_roles_without_data_access(client, username) -> None:
    response = _map(client, username)
    assert response.status_code == 200
    assert response.json()["features"] == []


def test_map_requires_authentication_and_validates_window(client) -> None:
    assert client.get(MAP_PATH).status_code == 401
    assert _map(client, "a.bello", hours=0).status_code == 422
    assert _map(client, "a.bello", hours=100000).status_code == 422


def test_map_read_is_audited_with_the_returned_ids_only(client) -> None:
    from test_assistant_endpoints import _audit

    _map(client, "t.adeyemi")
    events = [
        e
        for e in sorted(_audit(client), key=lambda e: e["seq"])
        if e["payload"].get("resource") == "connected_map" and e["payload"]["actor"] == "t.adeyemi"
    ]
    query = [e for e in events if e["payload"]["action"] == "query"][-1]["payload"]
    assert set(query["record_ids"]) == {"REC-046", "REC-048", "REC-049"}
    assert query["rows"] == 3
    assert "REC-053" not in str(query)  # the UAS-OPS detection never appears, even in the audit


REPLAY_PATH = "/api/v1/connected/replay"


def _replay(client, username: str, **params):
    return client.get(REPLAY_PATH, params=params, headers=auth_header(client, username))


def _replay_refs(response) -> list[str]:
    return [f["properties"]["ref"] for f in response.json()["events"]]


def test_replay_streams_visible_detections_in_time_order(client) -> None:
    bello = _replay(client, "a.bello")
    times = [f["properties"]["observed_at"] for f in bello.json()["events"]]
    assert times == sorted(times)
    assert set(_replay_refs(bello)) == {
        "REC-048",
        "REC-049",
        "REC-051",
        "REC-052",
        "REC-053",
        "REC-054",
    }
    assert set(_replay_refs(_replay(client, "t.adeyemi"))) == {"REC-048", "REC-049"}
    assert _replay_refs(_replay(client, "k.musa")) == ["REC-053"]  # the UAS-OPS detection


def test_replay_advances_with_the_clock_without_repeating(client) -> None:
    full = _replay(client, "a.bello").json()["events"]
    first, second = full[0]["properties"], full[1]["properties"]
    early = _replay(client, "a.bello", upto=first["observed_at"])
    assert _replay_refs(early) == [first["ref"]]
    nxt = _replay(client, "a.bello", after=first["observed_at"], upto=second["observed_at"])
    assert first["ref"] not in _replay_refs(nxt)
    assert second["ref"] in _replay_refs(nxt)
    rest = _replay(client, "a.bello", after=full[-1]["properties"]["observed_at"])
    assert _replay_refs(rest) == []


@pytest.mark.parametrize("username", ["s.eze", "f.danjuma"])
def test_replay_is_empty_for_roles_without_data_access(client, username) -> None:
    response = _replay(client, username)
    assert response.status_code == 200
    assert response.json()["events"] == []


def test_replay_requires_authentication_and_valid_timestamps(client) -> None:
    assert client.get(REPLAY_PATH).status_code == 401
    assert _replay(client, "a.bello", after="not-a-time").status_code == 422
    assert _replay(client, "a.bello", upto="yesterday-ish").status_code == 422


def test_replay_audit_lists_only_delivered_ids(client) -> None:
    from test_assistant_endpoints import _audit

    _replay(client, "t.adeyemi")
    events = [
        e
        for e in sorted(_audit(client), key=lambda e: e["seq"])
        if e["payload"].get("resource") == "connected_replay"
        and e["payload"]["actor"] == "t.adeyemi"
        and e["payload"]["action"] == "query"
    ]
    query = events[-1]["payload"]
    assert set(query["record_ids"]) == {"REC-048", "REC-049"}
    assert "REC-053" not in str(query)

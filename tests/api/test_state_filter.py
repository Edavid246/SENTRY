"""State filter (pivot Task 2): a validated, closed list narrows tools, map and replay.

The filter runs in Python on rows the adapter already authorized (row filter + RLS inside
the query), so it can only narrow what a caller sees, never widen it.
"""

from __future__ import annotations

import pytest
from app.data_queries.errors import ToolParamError
from app.data_queries.tools import TOOLS
from app.geo.states import STATES, check_state
from scoped import run_tool, scoped
from test_auth_endpoints import auth_header
from test_connected_data import _ctx

MAP_PATH = "/api/v1/connected/map"
REPLAY_PATH = "/api/v1/connected/replay"


def _refs(response) -> set[str]:
    return {f["properties"]["ref"] for f in response.json()["features"]}


def _replay_refs(response) -> set[str]:
    return {f["properties"]["ref"] for f in response.json()["events"]}


def test_state_list_is_36_states_plus_fct() -> None:
    assert len(STATES) == 37 and len(set(STATES)) == 37
    assert "Federal Capital Territory" in STATES and "Niger" in STATES
    assert check_state(None) is None and check_state("") is None
    assert check_state("Niger") == "Niger"


@pytest.mark.parametrize("bad", ["niger", "Atlantis", "Niger; DROP TABLE x", 5, ["Niger"]])
def test_check_state_rejects_everything_off_the_list(bad) -> None:
    with pytest.raises(ValueError):
        check_state(bad)


# --- map ---------------------------------------------------------------------


def test_map_state_filter_narrows_and_never_widens(client) -> None:
    for user in ("owner", "logistics.head", "coo", "briech.lead"):
        everything = _refs(client.get(MAP_PATH, headers=auth_header(client, user)))
        niger = _refs(
            client.get(MAP_PATH, params={"state": "Niger"}, headers=auth_header(client, user))
        )
        assert niger == everything  # all demo sites are in Niger State
    kaduna = client.get(MAP_PATH, params={"state": "Kaduna"}, headers=auth_header(client, "owner"))
    assert kaduna.status_code == 200 and kaduna.json()["features"] == []


def test_map_state_filter_keeps_hidden_records_hidden(client) -> None:
    refs = _refs(
        client.get(MAP_PATH, params={"state": "Niger"}, headers=auth_header(client, "coo"))
    )
    assert refs == {"REC-046", "REC-048", "REC-049"}
    assert "REC-060" not in refs and "REC-053" not in refs


@pytest.mark.parametrize("bad", ["Atlantis", "niger", "Niger'--"])
def test_map_rejects_an_unknown_state(client, bad) -> None:
    response = client.get(MAP_PATH, params={"state": bad}, headers=auth_header(client, "owner"))
    assert response.status_code == 422


def test_replay_state_filter(client) -> None:
    owner = auth_header(client, "owner")
    everything = _replay_refs(client.get(REPLAY_PATH, headers=owner))
    assert everything
    assert (
        _replay_refs(client.get(REPLAY_PATH, params={"state": "Niger"}, headers=owner))
        == everything
    )
    assert _replay_refs(client.get(REPLAY_PATH, params={"state": "Lagos"}, headers=owner)) == set()
    assert client.get(REPLAY_PATH, params={"state": "Atlantis"}, headers=owner).status_code == 422
    coo = _replay_refs(
        client.get(REPLAY_PATH, params={"state": "Niger"}, headers=auth_header(client, "coo"))
    )
    assert coo <= everything and "REC-053" not in coo


# --- typed tools ---------------------------------------------------------------


def _rows(app_engine, ctx, tool, params):
    with scoped(app_engine, ctx) as scope:
        return {row["id"] for row in TOOLS[tool](scope, params).rows}


def test_tools_filter_by_state_without_widening(client, app_engine) -> None:
    owner = _ctx(client, app_engine, "owner")
    coo = _ctx(client, app_engine, "coo")
    all_missions = _rows(app_engine, owner, "uas_missions", {"period_days": 60})
    assert all_missions
    assert (
        _rows(app_engine, owner, "uas_missions", {"period_days": 60, "state": "Niger"})
        == all_missions
    )
    assert _rows(app_engine, owner, "uas_missions", {"period_days": 60, "state": "Kaduna"}) == set()
    assert _rows(app_engine, coo, "uas_missions", {"state": "Niger"}) == set()  # no UAS-OPS
    all_det = _rows(app_engine, owner, "detections_near_site", {})
    assert _rows(app_engine, owner, "detections_near_site", {"state": "Niger"}) == all_det
    assert _rows(app_engine, owner, "detections_near_site", {"state": "Lagos"}) == set()
    narrow = _rows(app_engine, coo, "detections_near_site", {"state": "Niger"})
    assert narrow == {"REC-048", "REC-049"} and narrow < all_det


@pytest.mark.parametrize("tool", ["uas_missions", "detections_near_site"])
@pytest.mark.parametrize("state", ["Atlantis", "niger", "Niger; DROP TABLE x", 7, True])
def test_tools_refuse_an_unknown_state_with_a_denied_audit_event(
    client, app_engine, tool, state
) -> None:
    ctx = _ctx(client, app_engine, "owner")
    outcome, _ = run_tool(app_engine, ctx, tool, {"state": state})
    assert outcome.refused and outcome.result is None
    with pytest.raises(ToolParamError), scoped(app_engine, ctx) as scope:
        TOOLS[tool](scope, {"state": state})

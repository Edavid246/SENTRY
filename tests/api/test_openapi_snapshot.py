"""The API surface as a snapshot (docs/REFACTOR_PLAN.md, step 0.1).

Every path, method, parameter and response schema the server publishes, compared with
tests/snapshots/openapi.json. A refactor that moves routes or models must leave this
unchanged; a failure means the API changed.

Prose is left out: descriptions and summaries come from docstrings and change with them.
Names are kept, because the web app's generated types (web/src/lib/api-types.ts) are keyed
by schema name. If a change is intended, re-record with UPDATE_SNAPSHOTS=1, then regenerate
the web types (`npm run gen:api`).
"""

from __future__ import annotations

from typing import Any

PROSE = frozenset({"description", "summary"})


def _shape(node: Any) -> Any:
    """The schema without its prose (a property *named* description is a dict, so it stays)."""
    if isinstance(node, dict):
        return {
            key: _shape(value)
            for key, value in node.items()
            if not (key in PROSE and isinstance(value, str))
        }
    if isinstance(node, list):
        return [_shape(value) for value in node]
    return node


def test_api_surface_matches_the_snapshot(client, snapshot) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    snapshot("openapi", _shape(response.json()))

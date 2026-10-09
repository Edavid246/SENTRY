"""One route convention: every router lives under /api/v1, no root aliases.

The UI proxies /api/* same-origin, so a route that also answers at the root
would shadow the proxy and let a second, differently-guarded path drift in
silently. The openapi sweep enforces the whole surface at once; the
parameterised 404s pin the aliases that used to exist.

Two deliberate exceptions, both called out in the step report:
- /healthz is a system route, not one of the business routers — compose
  healthchecks it directly at http://127.0.0.1:8001/healthz.
- No CORS middleware is installed at all (air-gap: same-origin only), which
  is confirmed here rather than assumed.
"""

import pytest
from app.main import create_app
from starlette.middleware.cors import CORSMiddleware
from test_auth_endpoints import login

# Root-level aliases that must be gone: (method, path).
ROOT_ALIASES = [
    ("POST", "/auth/login"),
    ("GET", "/me"),
    ("GET", "/documents"),
    ("GET", "/documents/DOC-001"),
    ("GET", "/records"),
    ("GET", "/audit"),
    ("GET", "/audit/verify"),
    ("GET", "/assistant/conversations"),
]


@pytest.mark.parametrize("method,path", ROOT_ALIASES)
def test_root_level_aliases_are_removed(client, method: str, path: str) -> None:
    response = client.request(method, path, json={} if method == "POST" else None)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("method,path", ROOT_ALIASES)
def test_the_same_routes_answer_under_api_v1(client, method: str, path: str) -> None:
    """The other half of the convention: nothing was deleted, only prefixed."""
    prefixed = f"/api/v1{path}"
    response = client.request(method, prefixed, json={} if method == "POST" else None)
    if method == "POST":
        assert response.status_code in (401, 422), response.text
    else:
        # Unauthenticated but routed: 401, not the 404 an alias would give.
        assert response.status_code == 401, response.text
        assert response.json() == {"detail": "not authenticated"}


def test_every_business_path_is_under_api_v1(client) -> None:
    spec = client.get("/openapi.json").json()
    outside = [path for path in spec["paths"] if not path.startswith("/api/v1")]
    assert outside == ["/healthz"]


def test_healthz_stays_at_the_root(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert login(client, "owner").status_code == 200


def test_no_cors_middleware_is_installed() -> None:
    application = create_app()
    cors = [m.cls for m in application.user_middleware if m.cls is CORSMiddleware]
    assert cors == []


def test_preflight_and_origin_responses_carry_no_cors_headers(client) -> None:
    preflight = client.options(
        "/api/v1/documents",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert preflight.headers.get("access-control-allow-origin") is None
    plain = client.get("/api/v1/documents", headers={"Origin": "http://localhost:3000"})
    assert plain.status_code == 401
    assert plain.headers.get("access-control-allow-origin") is None

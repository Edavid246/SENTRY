"""One route convention: every router lives under /api/v1, no root aliases.

The UI proxies /api/* same-origin, so a route that also answers at the root
would shadow the proxy and let a second, differently-guarded path drift in
silently. The openapi sweep enforces the whole surface at once.

Two deliberate exceptions, both called out in the step report:
- /healthz is a system route, not one of the business routers — compose
  healthchecks it directly at http://127.0.0.1:8001/healthz.
- No CORS middleware is installed at all (air-gap: same-origin only), which
  is confirmed here rather than assumed.
"""

from app.main import create_app
from starlette.middleware.cors import CORSMiddleware
from support.http import login


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

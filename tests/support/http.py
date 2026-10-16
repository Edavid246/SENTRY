"""HTTP helpers for the API tests: log in as a demo user and call the API as them."""

from __future__ import annotations

from weakref import WeakKeyDictionary

from app.seed import DEMO_PASSWORD

QUERY_PATH = "/api/v1/assistant/query"

# One bearer token per client and user. Logging in is an argon2 verify plus an audit event
# (and every 10th event a ledger commit): a fresh login per request was about a quarter of
# the test run. Tokens are stateless JWTs that outlive the run (2 h), so reuse is safe; a
# test about login itself calls `login`, which always logs in.
_tokens: WeakKeyDictionary = WeakKeyDictionary()


def login(client, username: str, password: str = DEMO_PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def auth_header(client, username: str) -> dict[str, str]:
    tokens = _tokens.setdefault(client, {})
    if username not in tokens:
        response = login(client, username)
        assert response.status_code == 200, response.text
        tokens[username] = response.json()["access_token"]
    return {"Authorization": f"Bearer {tokens[username]}"}


def get(client, username: str, path: str):
    return client.get(path, headers=auth_header(client, username))


def ask(client, username: str, question: str, conversation_id: str | None = None):
    body: dict[str, str] = {"question": question}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    return client.post(QUERY_PATH, json=body, headers=auth_header(client, username))


def run_correlation(client) -> None:
    """Run the correlation rules as the owner, so the findings exist."""
    assert (
        client.post("/api/v1/correlation/run", headers=auth_header(client, "owner")).status_code
        == 200
    )

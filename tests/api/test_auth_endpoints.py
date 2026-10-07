"""POST /auth/login and GET /me: authentication and identity through the real HTTP stack.

Every assertion compares against the hand-authored SPEC 7.4 contexts in
test_rls_only (CONTEXTS/ROLES) — the same oracle the RLS-only and
filter-only layers use — so a divergence anywhere in login -> token ->
AccessContext -> response shows up as a failure here.
"""

import pytest
from app.seed import DEMO_PASSWORD
from test_filter_only import ROLES
from test_rls_only import CONTEXTS, USERNAMES


def login(client, username: str, password: str = DEMO_PASSWORD):
    return client.post("/auth/login", json={"username": username, "password": password})


def auth_header(client, username: str) -> dict[str, str]:
    response = login(client, username)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize("username", USERNAMES)
def test_login_succeeds_for_every_demo_user(client, username: str) -> None:
    response = login(client, username)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type"}
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_wrong_password_is_generic_401(client) -> None:
    response = login(client, "a.bello", password="wrong-password")
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}


def test_unknown_username_is_the_same_401(client) -> None:
    response = login(client, "ghost.user", password="whatever")
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}


def test_wrong_password_and_unknown_username_are_indistinguishable(client) -> None:
    wrong_password = login(client, "a.bello", password="wrong-password")
    unknown_user = login(client, "ghost.user", password="whatever")
    assert wrong_password.status_code == unknown_user.status_code
    assert wrong_password.json() == unknown_user.json()


@pytest.mark.parametrize("username", USERNAMES)
def test_me_matches_hand_authored_context(client, username: str) -> None:
    response = client.get("/me", headers=auth_header(client, username))
    assert response.status_code == 200
    body = response.json()
    # Exact key set: no permissions, no token_id, no internal ids.
    assert set(body) == {
        "username",
        "role",
        "unit_path",
        "clearance_code",
        "clearance_rank",
        "compartments",
        "data_scope",
    }
    hand = CONTEXTS[username]
    assert body["username"] == username
    assert body["role"] == ROLES[username]
    assert body["unit_path"] == hand["unit_path"]
    assert body["clearance_rank"] == hand["clearance_rank"]
    assert body["compartments"] == sorted(hand["compartments"])
    assert body["data_scope"] == hand["data_scope"]


def test_me_without_authorization_header_401(client) -> None:
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "not authenticated"}


@pytest.mark.parametrize(
    "header_value",
    ["Token abc123", "Bearer", "Bearer    ", "Basic ZGVtbzpkZW1v", "abc123"],
    ids=["no-scheme", "bearer-no-token", "bearer-blank-token", "other-scheme", "no-space"],
)
def test_me_malformed_authorization_header_401(client, header_value: str) -> None:
    response = client.get("/me", headers={"Authorization": header_value})
    assert response.status_code == 401
    assert response.json() == {"detail": "not authenticated"}


def test_me_garbage_token_401(client) -> None:
    response = client.get("/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401
    assert response.json() == {"detail": "not authenticated"}


def test_me_forged_token_401(client) -> None:
    import jwt

    forged = jwt.encode(
        {"sub": "a.bello", "exp": 9_999_999_999},
        "wrong-secret-deliberately-long-enough",
        algorithm="HS256",
    )
    response = client.get("/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert response.json() == {"detail": "not authenticated"}

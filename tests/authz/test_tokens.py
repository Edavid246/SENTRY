"""Dev token validator: issue/validate round trip and every fail-closed path.

Keycloak is stubbed (docs/STUBS.md): DevTokenValidator is the dev stand-in.
Validation reads the user/unit/clearance/compartments from the database, so
the resolved context must match the hand-authored SPEC 7.4 contexts used by
the RLS-only and filter-only layers — that equivalence is asserted here.
"""

import base64
import json
import time

import pytest
from app.authz.tokens import DevTokenValidator, TokenError
from app.config import Settings
from sqlalchemy import text
from sqlalchemy.engine import Engine
from test_rls_only import CONTEXTS, USERNAMES


def _validator(settings: Settings) -> DevTokenValidator:
    return DevTokenValidator(settings=settings)


def _b64url(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_round_trip_resolves_full_context(
    app_engine: Engine, seeded: None, settings: Settings
) -> None:
    validator = _validator(settings)
    token = validator.issue_token("a.bello")
    with app_engine.connect() as conn:
        ctx = validator.validate(token, conn=conn)
    assert ctx.username == "a.bello"
    assert ctx.role == "commander"
    assert ctx.unit_path == "/command-a/"
    assert ctx.clearance_rank == 3
    assert ctx.compartments == frozenset({"UAS-OPS", "FORENSICS"})
    assert ctx.data_scope == "standard"
    assert "read" in ctx.permissions and "query" in ctx.permissions
    assert ctx.auth_method == "dev-jwt"
    assert ctx.token_id and ctx.session_id


@pytest.mark.parametrize("username", USERNAMES)
def test_resolved_context_matches_hand_authored(
    app_engine: Engine, seeded: None, settings: Settings, username: str
) -> None:
    validator = _validator(settings)
    token = validator.issue_token(username)
    with app_engine.connect() as conn:
        ctx = validator.validate(token, conn=conn)
    hand = CONTEXTS[username]
    assert ctx.clearance_rank == hand["clearance_rank"]
    assert ctx.compartments == frozenset(hand["compartments"])
    assert ctx.unit_path == hand["unit_path"]
    assert ctx.data_scope == hand["data_scope"]


def test_garbage_token_rejected(app_engine: Engine, settings: Settings) -> None:
    with app_engine.connect() as conn, pytest.raises(TokenError, match="invalid token"):
        _validator(settings).validate("not.a.jwt", conn=conn)


def test_token_signed_with_wrong_secret_rejected(app_engine: Engine, settings: Settings) -> None:
    forged = DevTokenValidator(
        secret="wrong-secret-deliberately-long-enough", settings=settings
    ).issue_token("a.bello")
    with app_engine.connect() as conn, pytest.raises(TokenError, match="invalid token"):
        _validator(settings).validate(forged, conn=conn)


def test_expired_token_rejected(app_engine: Engine, settings: Settings) -> None:
    token = _validator(settings).issue_token("a.bello", ttl_seconds=-5)
    with app_engine.connect() as conn, pytest.raises(TokenError, match="invalid token"):
        _validator(settings).validate(token, conn=conn)


def test_alg_none_token_rejected(app_engine: Engine, settings: Settings) -> None:
    now = 1_700_000_000
    token = (
        f"{_b64url({'alg': 'none', 'typ': 'JWT'})}"
        f".{_b64url({'sub': 'a.bello', 'iat': now, 'exp': now + 3600, 'jti': 'x'})}."
    )
    with app_engine.connect() as conn, pytest.raises(TokenError, match="invalid token"):
        _validator(settings).validate(token, conn=conn)


def test_unknown_user_rejected(app_engine: Engine, settings: Settings) -> None:
    token = _validator(settings).issue_token("ghost.user")
    with app_engine.connect() as conn, pytest.raises(TokenError, match="unknown or inactive"):
        _validator(settings).validate(token, conn=conn)


def test_inactive_user_rejected(
    app_engine: Engine, owner_engine: Engine, seeded: None, settings: Settings
) -> None:
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE users SET is_active = false WHERE username = 'f.danjuma'"))
    try:
        token = _validator(settings).issue_token("f.danjuma")
        with pytest.raises(TokenError, match="unknown or inactive"), app_engine.connect() as conn:
            _validator(settings).validate(token, conn=conn)
    finally:
        with owner_engine.begin() as conn:
            conn.execute(text("UPDATE users SET is_active = true WHERE username = 'f.danjuma'"))


@pytest.mark.parametrize("jti", [None, "", 42], ids=["missing", "blank", "not-a-string"])
def test_token_without_a_token_id_rejected(
    app_engine: Engine, seeded: None, settings: Settings, jti: object
) -> None:
    """A correctly signed token still needs a jti: the audit trail names every token."""
    import jwt

    now = int(time.time())
    claims: dict = {"sub": "a.bello", "iat": now, "exp": now + 3600}
    if jti is not None:
        claims["jti"] = jti
    token = jwt.encode(claims, settings.dev_jwt_secret, algorithm="HS256")
    with app_engine.connect() as conn, pytest.raises(TokenError, match="token id|invalid token"):
        _validator(settings).validate(token, conn=conn)

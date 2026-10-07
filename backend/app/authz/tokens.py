"""Dev token validator: JWT in, AccessContext out (SPEC 7.1, 7.4).

Keycloak is stubbed for the demo (docs/STUBS.md). The dev profile issues
HS256 tokens with a config-supplied secret and resolves each token to a
fully-built AccessContext by reading the user, unit, clearance and
compartments from the database at validation time — the context is never
trusted from token claims alone. The real deployment swaps this class for
the Keycloak-backed TokenValidator behind the same interface.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

import jwt
from sqlalchemy import text

from app.authz.context import AccessContext, permissions_for_role
from app.config import Settings, get_settings

_USER_SQL = """
    SELECT u.id, u.username, u.display_name, u.role, u.data_scope,
           u.is_active, u.clearance_code,
           un.id AS unit_id, un.path AS unit_path,
           COALESCE(cl.rank, -1) AS clearance_rank
    FROM users u
    JOIN units un ON un.id = u.unit_id
    LEFT JOIN classification_levels cl ON cl.code = u.clearance_code
    WHERE u.username = :username
"""

_COMPARTMENTS_SQL = """
    SELECT compartment_code
    FROM user_compartments
    WHERE user_id = :user_id
"""


class TokenError(Exception):
    """Token is missing, malformed, forged, expired, or has no user."""


class DevTokenValidator:
    """HS256 token issue/validate; fail-closed on every error path."""

    def __init__(
        self,
        secret: str | None = None,
        ttl_seconds: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self._secret = secret if secret is not None else cfg.dev_jwt_secret
        self._ttl = ttl_seconds if ttl_seconds is not None else cfg.dev_jwt_ttl_seconds

    def issue_token(self, username: str, ttl_seconds: int | None = None) -> str:
        ttl = self._ttl if ttl_seconds is None else ttl_seconds
        now = int(time.time())
        claims = {
            "sub": username,
            "iat": now,
            "exp": now + ttl,
            "jti": str(uuid4()),
            "sid": str(uuid4()),
        }
        return jwt.encode(claims, self._secret, algorithm="HS256")

    def validate(self, token: str, *, conn: Any) -> AccessContext:
        try:
            claims = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise TokenError(f"invalid token: {exc}") from exc

        username = claims.get("sub")
        if not isinstance(username, str) or not username:
            raise TokenError("token has no subject claim")
        if "exp" not in claims:
            raise TokenError("token has no expiry claim")

        row = conn.execute(text(_USER_SQL), {"username": username}).mappings().first()
        if row is None or not row["is_active"]:
            raise TokenError(f"unknown or inactive user '{username}'")

        compartments = frozenset(
            conn.execute(text(_COMPARTMENTS_SQL), {"user_id": row["id"]}).scalars()
        )
        return AccessContext(
            user_id=UUID(str(row["id"])),
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
            unit_id=UUID(str(row["unit_id"])),
            unit_path=row["unit_path"],
            clearance_code=row["clearance_code"],
            clearance_rank=int(row["clearance_rank"]),
            compartments=compartments,
            data_scope=row["data_scope"],
            permissions=permissions_for_role(row["role"]),
            session_id=str(claims.get("sid", "")),
            token_id=str(claims["jti"]),
            auth_method="dev-jwt",
        )

"""Login and identity: POST /api/v1/auth/login and GET /api/v1/me.

Everything is mounted under /api/v1 (one route convention; no root-level aliases) so the
Next.js UI can proxy /api/* to this service same-origin. Login attempts are audited as single
login events.
"""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import ConnDep, CurrentContext
from app.audit.events import audit_events, event
from app.authz.tokens import DevTokenValidator

_HASHER = PasswordHasher()
# Same generic 401 for unknown user and wrong password; a dummy verify keeps
# the two paths close in timing so the message is not the only protection.
_DUMMY_HASH = _HASHER.hash("timing-equaliser")

router = APIRouter(prefix="/api/v1", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class AccessToken(BaseModel):
    access_token: str
    token_type: str


class UnitCrumb(BaseModel):
    path: str
    name: str


class Me(BaseModel):
    username: str
    display_name: str
    role: str
    unit_path: str
    unit_breadcrumb: list[UnitCrumb]
    clearance_code: str | None
    clearance_rank: int
    compartments: list[str]
    permissions: list[str]
    data_scope: str


@router.post("/auth/login", response_model=AccessToken)
def login(body: LoginRequest, conn: ConnDep) -> AccessToken:
    row = conn.execute(
        text("SELECT id, password_hash, is_active FROM users WHERE username = :username"),
        {"username": body.username},
    ).first()
    is_active = row is not None and bool(row.is_active)
    stored_hash = row.password_hash if is_active else _DUMMY_HASH
    try:
        _HASHER.verify(stored_hash, body.password)
        password_ok = is_active
    except (Argon2Error, ValueError):
        password_ok = False
    if not password_ok:
        audit_events(
            [event(body.username, "login", "auth", "deny", reasons=["invalid credentials"])]
        )
        raise HTTPException(
            status_code=401,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    audit_events([event(body.username, "login", "auth", "allow", user_id=str(row.id))])
    # The dev login issues dev tokens explicitly; with Keycloak, login leaves this service.
    return AccessToken(
        access_token=DevTokenValidator().issue_token(body.username),
        token_type="bearer",
    )


@router.get("/me", response_model=Me)
def me(ctx: CurrentContext, conn: ConnDep) -> Me:
    """UI-facing identity read: exactly the context fields the shell needs.

    `unit_breadcrumb` resolves the caller's unit path to readable unit names
    (oldest ancestor first) so the top bar can show "EIB Group > EIB Stratoc >
    Stratoc Site Team 4"; `permissions` is what the nav may offer — the server still
    enforces every action itself (SPEC 7.1).
    """
    breadcrumb = [
        UnitCrumb(path=str(row.path), name=str(row.name))
        for row in conn.execute(
            text(
                "SELECT path, name FROM units"
                " WHERE starts_with(:unit_path, path) ORDER BY length(path)"
            ),
            {"unit_path": ctx.unit_path},
        ).all()
    ]
    return Me(
        username=ctx.username,
        display_name=ctx.display_name,
        role=ctx.role,
        unit_path=ctx.unit_path,
        unit_breadcrumb=breadcrumb,
        clearance_code=ctx.clearance_code,
        clearance_rank=ctx.clearance_rank,
        compartments=sorted(ctx.compartments),
        permissions=sorted(ctx.permissions),
        data_scope=ctx.data_scope,
    )

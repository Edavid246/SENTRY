"""The SPEC 7.4 demo users' access contexts, hand-authored and independent of app.seed.

The RLS-only, filter-only and endpoint layers all check against these, so a divergence
anywhere in seed -> token -> AccessContext shows up as a failure. `ctx_for` is the other
direction: the context the real token validator resolves for a logged-in user.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.authz.context import AccessContext, permissions_for_role
from app.authz.tokens import get_token_validator

from support.http import auth_header

CONTEXTS: dict[str, dict] = {
    "owner": {
        "clearance_rank": 3,
        "compartments": ["UAS-OPS", "FORENSICS", "CLIENT-A", "CLIENT-B", "CLIENT-C", "CLIENT-D"],
        "unit_path": "/eib-group/",
        "data_scope": "standard",
    },
    "logistics.head": {
        "clearance_rank": 2,
        "compartments": [],
        "unit_path": "/eib-group/stratoc/",
        "data_scope": "standard",
    },
    "coo": {
        "clearance_rank": 1,
        "compartments": [],
        "unit_path": "/eib-group/stratoc/site-4/",
        "data_scope": "standard",
    },
    "briech.lead": {
        "clearance_rank": 2,
        "compartments": ["UAS-OPS", "CLIENT-A"],
        "unit_path": "/eib-group/briech/",
        "data_scope": "standard",
    },
    "group.it": {
        "clearance_rank": -1,
        "compartments": [],
        "unit_path": "/group-it/",
        "data_scope": "none",
    },
    "group.audit": {
        "clearance_rank": 1,
        "compartments": [],
        "unit_path": "/group-audit/",
        "data_scope": "audit",
    },
}

USERNAMES = sorted(CONTEXTS)

ROLES: dict[str, str] = {
    "owner": "commander",
    "logistics.head": "logistics",
    "coo": "training",
    "briech.lead": "uas_ops",
    "group.it": "sysadmin",
    "group.audit": "auditor",
}

CLEARANCE_CODES: dict[str, str | None] = {
    "owner": "secret",
    "logistics.head": "confidential",
    "coo": "restricted",
    "briech.lead": "confidential",
    "group.it": None,
    "group.audit": "restricted",
}


def access_context(username: str) -> AccessContext:
    """Build the SPEC 7.4 AccessContext by hand (independent of app.seed).

    unit_id is a deterministic placeholder: LocalPolicy.row_filter never
    reads it (the unit path is what the filter uses), so inventing one here
    keeps this layer free of database lookups.
    """
    hand = CONTEXTS[username]
    role = ROLES[username]
    return AccessContext(
        user_id=uuid5(NAMESPACE_URL, f"test-user:{username}"),
        username=username,
        display_name=username,
        role=role,
        unit_id=uuid5(NAMESPACE_URL, f"test-unit:{username}"),
        unit_path=hand["unit_path"],
        clearance_code=CLEARANCE_CODES[username],
        clearance_rank=hand["clearance_rank"],
        compartments=frozenset(hand["compartments"]),
        data_scope=hand["data_scope"],
        permissions=permissions_for_role(role),
        session_id=f"filter-only:{username}",
        token_id=f"filter-only:{username}",
        auth_method="test",
    )


def ctx_for(client, app_engine, username: str) -> AccessContext:
    """Log in through the API and resolve the token the way a request does."""
    token = auth_header(client, username)["Authorization"].split(" ", 1)[1]
    with app_engine.connect() as conn:
        return get_token_validator().validate(token, conn=conn)

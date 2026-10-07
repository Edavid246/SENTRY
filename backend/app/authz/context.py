"""Access context: the frozen, fully-resolved facts for one request (SPEC 7.1).

Built at authentication time from the user, unit, clearance and compartments;
policies and RLS read it, nothing mutates it mid-request. permissions derive
from the organizational role (SPEC 7.1 "Permissions"); an unknown role gets
no permissions (fail closed).
"""

from dataclasses import dataclass
from uuid import UUID

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "commander": frozenset({"read", "query", "retrieve", "answer", "run_correlation"}),
    "logistics": frozenset({"read", "query", "retrieve", "answer"}),
    "training": frozenset({"read", "query", "retrieve", "answer"}),
    "uas_ops": frozenset({"read", "query", "retrieve", "answer"}),
    "sysadmin": frozenset({"manage", "read_audit"}),
    "auditor": frozenset({"read_audit"}),
}


def permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


@dataclass(frozen=True, slots=True)
class AccessContext:
    user_id: UUID
    username: str
    display_name: str
    role: str
    unit_id: UUID
    unit_path: str
    clearance_code: str | None
    clearance_rank: int
    compartments: frozenset[str]
    data_scope: str
    permissions: frozenset[str]
    session_id: str
    token_id: str
    auth_method: str

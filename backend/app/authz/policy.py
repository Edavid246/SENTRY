"""Policy layer (SPEC 7.3): the Policy protocol and its local implementation.

LocalPolicy encodes the literal SPEC 7.1 rule proven by the RLS-only tests:

    row visible  <=>  data_scope = 'standard'
                  AND clearance_rank >= row classification rank
                  AND row.compartments <= ctx.compartments
                  AND row unit path startswith ctx.unit_path (strictly downward)

row_filter returns a parameterized SQL predicate: bound parameters only,
never value interpolation, and both array sides cast explicitly to text[] —
the lesson from the step-3 RLS migration (no operator between varchar[]
and text[]).
"""

from dataclasses import dataclass
from typing import Any, Protocol

from app.authz.context import AccessContext
from app.db import format_array

RESOURCE_TABLES: dict[str, str] = {
    "document": "documents",
    "chunk": "chunks",
    "record": "canonical_records",
}
KNOWN_RESOURCES: frozenset[str] = frozenset(RESOURCE_TABLES) | {"audit"}
DATA_ACTIONS: frozenset[str] = frozenset({"read", "query", "retrieve", "answer", "view_record"})


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RowFilter:
    where_sql: str
    params: dict[str, Any]


class Policy(Protocol):
    def decide(self, ctx: AccessContext, action: str, resource: str) -> Decision: ...

    def row_filter(self, ctx: AccessContext, resource: str) -> RowFilter: ...


class LocalPolicy:
    """Pure-Python policy behind the Policy protocol (OPA is stubbed — docs/STUBS.md)."""

    def decide(self, ctx: AccessContext, action: str, resource: str) -> Decision:
        reasons: list[str] = []
        if resource not in KNOWN_RESOURCES:
            reasons.append(f"unknown resource type '{resource}'")
        if action not in ctx.permissions:
            reasons.append(f"action '{action}' not granted by role '{ctx.role}'")
        if action in DATA_ACTIONS and ctx.data_scope != "standard":
            reasons.append(f"data_scope '{ctx.data_scope}' does not permit data actions")
        return Decision(allowed=not reasons, reasons=tuple(reasons))

    def row_filter(self, ctx: AccessContext, resource: str) -> RowFilter:
        try:
            table = RESOURCE_TABLES[resource]
        except KeyError:
            raise ValueError(f"no row filter for resource '{resource}'") from None
        where_sql = f"""
            (
                :data_scope = 'standard'
                AND :clearance_rank >= (
                    SELECT cl.rank FROM classification_levels cl
                    WHERE cl.code = {table}.classification_code
                )
                AND {table}.compartments::text[] <@ CAST(:compartments AS text[])
                AND EXISTS (
                    SELECT 1 FROM units u
                    WHERE u.id = {table}.unit_id
                      AND starts_with(u.path, :unit_path)
                )
            )
        """
        params = {
            "data_scope": ctx.data_scope,
            "clearance_rank": int(ctx.clearance_rank),
            "compartments": format_array(ctx.compartments),
            "unit_path": ctx.unit_path,
        }
        return RowFilter(where_sql=where_sql, params=params)

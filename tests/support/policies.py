"""Policy fakes, installed at `app.authz.scope.get_policy` (the one place the policy is read)."""

from __future__ import annotations

from app.authz.context import AccessContext
from app.authz.policy import Decision, Policy, RowFilter
from app.authz.scope import Requirement

WITHHELD = "withheld by the test policy"


class Withholding:
    """The real policy, except that it denies the given (action, resource) pairs to everyone.

    Stands in for a future role that has, say, `read` on dashboards but not `query` on records.
    """

    def __init__(self, inner: Policy, *denied: Requirement) -> None:
        self.inner = inner
        self.denied = set(denied)

    def decide(self, ctx: AccessContext, action: str, resource: str) -> Decision:
        if (action, resource) in self.denied:
            return Decision(allowed=False, reasons=(WITHHELD,))
        return self.inner.decide(ctx, action, resource)

    def row_filter(self, ctx: AccessContext, resource: str) -> RowFilter:
        return self.inner.row_filter(ctx, resource)

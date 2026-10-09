"""LocalPolicy.decide: role permission + data-scope gates (pure, no database).

decide answers "may this action run at all"; row_filter answers "which rows"
(test_filter_only). Together they are the Policy layer the endpoints call in
step 6.
"""

from dataclasses import replace

import pytest
from app.authz.context import permissions_for_role
from app.authz.policy import LocalPolicy
from test_filter_only import access_context
from test_rls_only import USERNAMES

POLICY = LocalPolicy()

OPERATIONAL_USERS = ["owner", "logistics.head", "coo", "briech.lead"]


@pytest.mark.parametrize("username", OPERATIONAL_USERS)
def test_operational_roles_may_read_data(username: str) -> None:
    decision = POLICY.decide(access_context(username), "read", "document")
    assert decision.allowed, decision.reasons


@pytest.mark.parametrize("username", OPERATIONAL_USERS)
def test_operational_roles_may_query_and_retrieve(username: str) -> None:
    ctx = access_context(username)
    assert POLICY.decide(ctx, "query", "chunk").allowed
    assert POLICY.decide(ctx, "retrieve", "record").allowed
    assert POLICY.decide(ctx, "answer", "document").allowed


def test_sysadmin_cannot_touch_data() -> None:
    decision = POLICY.decide(access_context("group.it"), "read", "document")
    assert not decision.allowed
    assert any("not granted" in reason for reason in decision.reasons)
    assert any("data_scope" in reason for reason in decision.reasons)


def test_sysadmin_may_manage() -> None:
    assert POLICY.decide(access_context("group.it"), "manage", "document").allowed


def test_auditor_is_audit_only() -> None:
    ctx = access_context("group.audit")
    assert POLICY.decide(ctx, "read_audit", "audit").allowed
    assert not POLICY.decide(ctx, "read", "document").allowed
    assert not POLICY.decide(ctx, "query", "record").allowed


def test_non_standard_scope_blocks_data_actions() -> None:
    # A role that has 'read' but a non-standard scope must still be denied.
    ctx = replace(access_context("owner"), data_scope="audit")
    decision = POLICY.decide(ctx, "read", "document")
    assert not decision.allowed
    assert any("does not permit data actions" in reason for reason in decision.reasons)


def test_unknown_action_denied() -> None:
    decision = POLICY.decide(access_context("owner"), "delete", "document")
    assert not decision.allowed


def test_unknown_resource_denied() -> None:
    decision = POLICY.decide(access_context("owner"), "read", "banana")
    assert not decision.allowed
    assert any("unknown resource" in reason for reason in decision.reasons)


def test_row_filter_unknown_resource_raises() -> None:
    with pytest.raises(ValueError, match="no row filter"):
        POLICY.row_filter(access_context("owner"), "banana")


def test_unknown_role_gets_no_permissions() -> None:
    assert permissions_for_role("intruder") == frozenset()


def test_every_demo_role_resolves() -> None:
    for username in USERNAMES:
        assert access_context(username).permissions

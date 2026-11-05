"""Ancestor scope and tenant-command regression contracts."""

from __future__ import annotations

import uuid

import pytest

from billing_platform.authz import Scope, ScopePath
from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import ValidationFailedError
from billing_platform.field_policy import FieldPolicyRule, resolve_field_effect
from billing_platform.idempotency import CommandIdentity


def test_nearest_department_rule_overrides_ancestor():
    company, parent, child = (uuid.uuid4() for _ in range(3))
    target = ScopePath(company, child, (parent,))
    assert target.includes(Scope("department", parent))
    rules = [
        FieldPolicyRule("name", "read", "deny", Scope("department", parent)),
        FieldPolicyRule("name", "read", "allow", Scope("department", child)),
    ]
    assert resolve_field_effect(rules, field_key="name", access="read", target=target) == "allow"
    rules.append(FieldPolicyRule("name", "read", "deny", Scope("department", child)))
    assert resolve_field_effect(rules, field_key="name", access="read", target=target) == "deny"


@pytest.mark.parametrize("case", ["missing_child", "sentinel", "duplicate", "self", "depth"])
def test_invalid_department_ancestry_is_rejected(case):
    company, parent, child = (uuid.uuid4() for _ in range(3))
    ancestors = (parent,)
    if case == "missing_child":
        child = None
    if case == "sentinel":
        ancestors = (SCOPE_ALL,)
    if case == "duplicate":
        ancestors = (parent, parent)
    if case == "self":
        ancestors = (child,)
    if case == "depth":
        ancestors = tuple(uuid.uuid4() for _ in range(6))
    with pytest.raises(ValidationFailedError):
        ScopePath(company, child, ancestors)


def test_tenant_command_has_distinct_digest_and_still_rejects_zero_company():
    tenant, actor, company = (uuid.uuid4() for _ in range(3))

    def command(cid):
        return CommandIdentity(tenant, cid, actor, "identity.role_assignment.regrant", "review", {})

    assert command(None).digest() != command(company).digest()
    with pytest.raises(ValueError):
        command(SCOPE_ALL)


def test_department_audit_scope_requires_and_preserves_company():
    from billing_platform.outbox import audit_payload

    company, department, actor = (uuid.uuid4() for _ in range(3))
    values = {
        "action": "department.updated",
        "entity_type": "department",
        "entity_id": department,
        "actor_user_id": actor,
        "department_id": department,
    }
    with pytest.raises(ValueError):
        audit_payload(**values)
    payload = audit_payload(**values, company_id=company)
    assert payload["company_id"] == str(company) and payload["department_id"] == str(department)

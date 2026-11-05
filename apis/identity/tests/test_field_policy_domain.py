"""Field-policy resolution, tested with no database (docs/field-permissions.md §6)."""

from __future__ import annotations

import uuid

import pytest
from billing_platform.authz import Scope, ScopePath
from billing_platform.errors import PermissionDeniedError

from identity.domain.field_policy import (
    FieldPolicyRule,
    assert_fields_writable,
    denied_fields,
    resolve_field_effect,
)

_COMPANY = uuid.uuid4()
_TARGET = ScopePath(company_id=_COMPANY)


def _rule(field: str, effect: str, scope: Scope, access: str = "write") -> FieldPolicyRule:
    return FieldPolicyRule(field_key=field, access=access, effect=effect, scope=scope)


def test_default_is_allow() -> None:
    assert resolve_field_effect([], field_key="price", access="write", target=_TARGET) == "allow"


def test_tenant_deny_blocks_the_field() -> None:
    rules = [_rule("price", "deny", Scope("tenant"))]
    assert resolve_field_effect(rules, field_key="price", access="write", target=_TARGET) == "deny"


def test_more_specific_scope_overrides_broader() -> None:
    """A company-scope allow overrides a tenant-scope deny."""
    rules = [
        _rule("price", "deny", Scope("tenant")),
        _rule("price", "allow", Scope("company", _COMPANY)),
    ]
    assert resolve_field_effect(rules, field_key="price", access="write", target=_TARGET) == "allow"


def test_deny_wins_at_equal_specificity() -> None:
    rules = [
        _rule("price", "allow", Scope("tenant")),
        _rule("price", "deny", Scope("tenant")),
    ]
    assert resolve_field_effect(rules, field_key="price", access="write", target=_TARGET) == "deny"


def test_read_and_write_are_separate() -> None:
    rules = [_rule("price", "deny", Scope("tenant"), access="read")]
    # A read-deny does not deny writing.
    assert resolve_field_effect(rules, field_key="price", access="write", target=_TARGET) == "allow"


def test_assert_fields_writable_only_flags_changed_denied_fields() -> None:
    rules = [_rule("unit_price", "deny", Scope("tenant"))]
    # Changing an unrelated field is fine.
    assert_fields_writable(["quantity"], rules=rules, target=_TARGET)
    # Changing the denied field raises, and names it.
    with pytest.raises(PermissionDeniedError) as exc:
        assert_fields_writable(["quantity", "unit_price"], rules=rules, target=_TARGET)
    assert "unit_price" in str(exc.value)
    assert denied_fields(["unit_price"], rules=rules, access="write", target=_TARGET) == [
        "unit_price"
    ]


def test_policy_on_another_company_does_not_reach_this_one() -> None:
    other = uuid.uuid4()
    rules = [_rule("price", "deny", Scope("company", other))]
    assert resolve_field_effect(rules, field_key="price", access="write", target=_TARGET) == "allow"

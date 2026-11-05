"""Edge-branch coverage for the domain helpers — error paths and guards (CLAUDE.md §7,
the 90% floor on ``domain/``)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.authz import ScopePath
from billing_platform.errors import PermissionDeniedError, ValidationFailedError

from identity.domain import department_tree, system_roles
from identity.domain.authorization import (
    Actor,
    AssignmentChange,
    assert_role_composition_allowed,
)
from identity.domain.field_registry import COMPANY_ENTITY_TYPE, register_native_fields
from identity.domain.system_roles import SystemRole, _validate_catalogue

# --- department_tree error branches -------------------------------------------


def test_child_path_rejects_a_malformed_prefix() -> None:
    with pytest.raises(ValidationFailedError):
        department_tree.child_path("no-slashes", uuid.UUID(int=1))


def test_rewritten_path_rejects_a_path_outside_the_subtree() -> None:
    with pytest.raises(ValidationFailedError):
        department_tree.rewritten_path(old_prefix="/a/", new_prefix="/b/", path="/c/d/")


# --- field_registry idempotency -----------------------------------------------


def test_register_native_fields_is_idempotent() -> None:
    register_native_fields()
    register_native_fields()  # second call is a no-op, not a double-register error
    from billing_platform.fields import registry

    assert COMPANY_ENTITY_TYPE in registry.entity_types()


# --- system_roles helpers -----------------------------------------------------


def test_get_unknown_system_role_raises() -> None:
    with pytest.raises(KeyError):
        system_roles.get("no_such_role")


def test_read_permissions_are_all_dot_read() -> None:
    reads = system_roles.read_permissions()
    assert reads
    assert all(key.rsplit(".", 1)[-1] == "read" for key in reads)
    assert "audit.read_security" not in reads  # a distinct authority, not a resource read


def _role(key: str, perms: set[str], *, scope_hint: str = "company") -> SystemRole:
    return SystemRole(
        key=key,
        name=key.title(),
        description="d",
        scope_hint=scope_hint,
        permissions=frozenset(perms),
    )


@pytest.mark.parametrize(
    "roles",
    [
        (_role("dup", {"invoice.read"}), _role("dup", {"invoice.read"})),  # duplicate keys
        (_role("Bad Key", {"invoice.read"}),),  # malformed key
        (_role("weird", {"invoice.read"}, scope_hint="galaxy"),),  # bad scope_hint
        (_role("empty", set()),),  # grants nothing
        (_role("typo", {"invoice.reed"}),),  # unknown permission
        (_role("risky", {"invoice.create", "invoice.approve"}),),  # separation-of-duties pair
        (_role("tenant_auditor", {"invoice.read"}),),  # auditor missing most reads
    ],
)
def test_validate_catalogue_rejects_a_bad_catalogue(roles: tuple[SystemRole, ...]) -> None:
    """Every boot guard fires on a crafted bad catalogue (the real one is validated at
    import). These are the failure modes that would otherwise be invisible at runtime."""
    with pytest.raises(ValueError):
        _validate_catalogue(roles)


# --- authorization guard branches ---------------------------------------------


def test_assignment_change_rejects_unknown_subject_type() -> None:
    with pytest.raises(ValidationFailedError):
        AssignmentChange(
            subject_type="robot",
            subject_id=uuid.UUID(int=5),
            role_permissions=frozenset(),
            target=ScopePath(),
        )


def test_assignment_change_rejects_sentinel_subject() -> None:
    with pytest.raises(ValidationFailedError):
        AssignmentChange(
            subject_type="user",
            subject_id=uuid.UUID(int=0),  # SCOPE_ALL is not a subject
            role_permissions=frozenset(),
            target=ScopePath(),
        )


def test_compose_role_without_manage_is_denied() -> None:
    actor = Actor(user_id=uuid.UUID(int=7), grants=())  # holds nothing
    with pytest.raises(PermissionDeniedError):
        assert_role_composition_allowed(
            ["invoice.read"], actor=actor, target=ScopePath(), on_date=dt.date(2026, 5, 1)
        )

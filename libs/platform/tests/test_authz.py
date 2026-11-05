"""Permission resolution — and, above all, object-level scope.

The load-bearing test in this file is
``test_a_company_scoped_grant_does_not_reach_another_company``. Holding
``invoice.post`` says nothing about *whose* invoice, and a check that stops at the
key is the most likely real vulnerability in this system (CLAUDE.md §5.2). Every
other test here exists to keep that one honest: the scope types, the ancestry path,
the validity window and the revocation flag are all inputs to it.

No database and no ORM: resolution takes plain value objects built from the caller's
own rows, which is what lets the whole authorization model be tested exhaustively
in milliseconds.
"""

from __future__ import annotations

import datetime as dt
import inspect
import uuid

import pytest

from billing_platform.authz import (
    SCOPE_HINTS,
    SCOPE_TYPES,
    TENANT_SCOPE,
    Grant,
    Scope,
    ScopePath,
    assert_permitted,
    decode_grants,
    encode_grants,
    grant_from_wire,
    grant_to_wire,
    has_permission,
    resolve_permissions,
)
from billing_platform.constants import SCOPE_ALL
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.ids import uuid7

COMPANY_A = uuid7()
COMPANY_B = uuid7()
DEPARTMENT_A1 = uuid7()
DEPARTMENT_A2 = uuid7()

TODAY = dt.date(2026, 9, 3)
APRIL = dt.date(2026, 4, 1)
MARCH_31 = dt.date(2027, 3, 31)


def grant(
    *permissions: str,
    scope: Scope = TENANT_SCOPE,
    valid_from: dt.date = APRIL,
    valid_to: dt.date | None = None,
    is_active: bool = True,
) -> Grant:
    """One assignment, stated as briefly as a test can state it."""
    return Grant(
        permissions=frozenset(permissions),
        scope=scope,
        valid_from=valid_from,
        valid_to=valid_to,
        is_active=is_active,
    )


# --- scope ---------------------------------------------------------------------


def test_the_scope_types_are_the_documented_three_broadest_first() -> None:
    """docs/identity-schema.md §5.3. The order *is* the containment order, so
    reordering this tuple would silently invert which grant is broader."""
    assert SCOPE_TYPES == ("tenant", "company", "department")


def test_the_scope_hints_add_platform_to_the_scope_types() -> None:
    """``role.scope_hint`` is UI guidance on the assignment form, never enforcement
    (docs/identity-schema.md §5.1). ``platform`` is a hint with no matching ``Scope``
    and deliberately never becomes one — a platform-scope *assignment* would be a
    cross-tenant grant, so a platform role is assigned at tenant scope like any other.
    Derived from ``SCOPE_TYPES`` so a new scope type cannot become unhintable."""
    assert SCOPE_HINTS == {"platform", *SCOPE_TYPES}
    assert not SCOPE_HINTS - {"platform", *SCOPE_TYPES}
    with pytest.raises(ValidationFailedError):
        Scope("platform")


def test_breadth_orders_scopes_from_broadest_to_narrowest() -> None:
    assert TENANT_SCOPE.breadth < Scope("company", COMPANY_A).breadth
    assert Scope("company", COMPANY_A).breadth < Scope("department", DEPARTMENT_A1).breadth


def test_a_tenant_scope_carries_the_sentinel_rather_than_a_null() -> None:
    """MariaDB treats NULLs inside a unique key as distinct, and the assignment's
    unique key contains ``scope_id`` (docs/identity-db-plan.md §2). Two tenant-scope
    assignments of one role would both insert."""
    assert TENANT_SCOPE.scope_id == SCOPE_ALL


def test_an_unknown_scope_type_is_refused() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        Scope("region", COMPANY_A)

    assert raised.value.extra["fields"] == {"scope_type": "not one of tenant, company, department"}


def test_a_tenant_scope_may_not_name_an_object() -> None:
    """A tenant-scope grant applies to the whole tenant; an id alongside it means the
    caller meant company scope and the grant would silently be tenant-wide."""
    with pytest.raises(ValidationFailedError) as raised:
        Scope("tenant", COMPANY_A)

    assert raised.value.extra["fields"] == {"scope_id": "must be omitted at tenant scope"}


def test_a_company_scope_must_name_the_company() -> None:
    """Defaulting to the sentinel would turn a company grant into a tenant-wide one —
    the exact escalation the sentinel exists to make expressible, not accidental."""
    with pytest.raises(ValidationFailedError) as raised:
        Scope("company")

    assert raised.value.extra["fields"] == {"scope_id": "required at company scope"}


def test_a_department_scope_must_name_the_department() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        Scope("department")

    assert raised.value.extra["fields"] == {"scope_id": "required at department scope"}


def test_a_scope_is_frozen_and_hashable() -> None:
    """Hashable because containment is set membership on the target's ancestry, and
    frozen because a scope handed to a resolver must not be mutable by anything that
    holds a reference to it."""
    assert Scope("company", COMPANY_A) == Scope("company", COMPANY_A)
    assert len({Scope("company", COMPANY_A), Scope("company", COMPANY_A)}) == 1
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError is not public
        Scope("company", COMPANY_A).scope_id = COMPANY_B  # type: ignore[misc]


# --- the object's ancestry -----------------------------------------------------


def test_a_tenant_wide_object_has_one_scope() -> None:
    assert ScopePath().scopes() == (TENANT_SCOPE,)


def test_a_company_object_is_reachable_from_the_tenant_or_the_company() -> None:
    assert ScopePath(company_id=COMPANY_A).scopes() == (
        TENANT_SCOPE,
        Scope("company", COMPANY_A),
    )


def test_a_department_object_lists_its_whole_ancestry_broadest_first() -> None:
    assert ScopePath(company_id=COMPANY_A, department_id=DEPARTMENT_A1).scopes() == (
        TENANT_SCOPE,
        Scope("company", COMPANY_A),
        Scope("department", DEPARTMENT_A1),
    )


def test_a_department_path_must_name_its_company() -> None:
    """A department always belongs to a company. A path with the department alone
    would make a company-scoped grant look as though it did not apply, and the
    company admin would be denied access to their own department's records."""
    with pytest.raises(ValidationFailedError) as raised:
        ScopePath(department_id=DEPARTMENT_A1)

    assert raised.value.extra["fields"] == {"company_id": "required when department_id is given"}


def test_the_sentinel_is_not_an_object() -> None:
    """``SCOPE_ALL`` in a target path would mean "the object that is every object",
    and every company-scoped grant would match it."""
    with pytest.raises(ValidationFailedError) as raised:
        ScopePath(company_id=SCOPE_ALL)

    assert raised.value.extra["fields"] == {"company_id": "must be a real id"}


def test_the_sentinel_is_refused_as_a_department_too() -> None:
    with pytest.raises(ValidationFailedError) as raised:
        ScopePath(company_id=COMPANY_A, department_id=SCOPE_ALL)

    assert raised.value.extra["fields"] == {"department_id": "must be a real id"}


def test_a_tenant_grant_reaches_every_object_in_the_tenant() -> None:
    for target in (
        ScopePath(),
        ScopePath(company_id=COMPANY_A),
        ScopePath(company_id=COMPANY_B, department_id=uuid7()),
    ):
        assert target.includes(TENANT_SCOPE)


def test_a_company_grant_does_not_reach_the_tenant_itself() -> None:
    """Narrower never reaches broader: a company admin editing tenant settings is
    §1.5's third escalation guard as a data question."""
    assert not ScopePath().includes(Scope("company", COMPANY_A))


def test_a_department_grant_does_not_reach_the_whole_company() -> None:
    assert not ScopePath(company_id=COMPANY_A).includes(Scope("department", DEPARTMENT_A1))


def test_a_company_scoped_grant_does_not_reach_another_company() -> None:
    """**CLAUDE.md §5.2.** Both scopes are ``company`` and equally broad, and one of
    them still must not reach the other's rows. Comparing only ``scope_type`` — the
    plausible-looking shortcut — passes every other test in this file and opens the
    breach this one exists to catch."""
    theirs = ScopePath(company_id=COMPANY_B)

    assert not theirs.includes(Scope("company", COMPANY_A))
    assert theirs.includes(Scope("company", COMPANY_B))


def test_a_sibling_departments_grant_does_not_reach_this_department() -> None:
    target = ScopePath(company_id=COMPANY_A, department_id=DEPARTMENT_A1)

    assert not target.includes(Scope("department", DEPARTMENT_A2))


# --- the validity window and revocation ---------------------------------------


def test_a_grant_inside_its_window_is_in_force() -> None:
    assert grant("invoice.read").in_force(target=ScopePath(), on_date=TODAY)


def test_a_grant_is_in_force_on_its_first_and_last_day() -> None:
    """Inclusive at both ends: an auditor whose access runs to the 31st has it on the
    31st, and an exclusive bound would deny a day of legitimate work."""
    window = grant("audit.read", valid_from=APRIL, valid_to=MARCH_31)

    assert window.in_force(target=ScopePath(), on_date=APRIL)
    assert window.in_force(target=ScopePath(), on_date=MARCH_31)


def test_a_grant_is_not_in_force_before_it_starts_or_after_it_ends() -> None:
    window = grant("audit.read", valid_from=APRIL, valid_to=MARCH_31)

    assert not window.in_force(target=ScopePath(), on_date=dt.date(2026, 3, 31))
    assert not window.in_force(target=ScopePath(), on_date=dt.date(2027, 4, 1))


def test_an_open_ended_grant_never_lapses() -> None:
    assert grant("invoice.read").in_force(target=ScopePath(), on_date=dt.date(2099, 1, 1))


def test_a_revoked_grant_is_not_in_force_inside_its_window() -> None:
    """``is_active`` is revocation and takes effect the moment it is written; the
    window is scheduled elevation. Both must pass, so neither can override the other
    in the permissive direction — which is what keeps two date-shaped mechanisms on
    one row unambiguous (rule 4.12, docs/identity-schema.md §5.3)."""
    revoked = grant("period.close", valid_to=MARCH_31, is_active=False)

    assert not revoked.in_force(target=ScopePath(), on_date=TODAY)


def test_an_active_grant_outside_its_window_is_still_not_in_force() -> None:
    """The other direction of the same pair. A lapsed assignment left ``is_active``
    is the year-end auditor nobody remembered to revoke."""
    lapsed = grant("audit.read", valid_from=APRIL, valid_to=dt.date(2026, 8, 31))

    assert lapsed.is_active
    assert not lapsed.in_force(target=ScopePath(), on_date=TODAY)


def test_a_grant_is_frozen() -> None:
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError is not public
        grant("invoice.read").is_active = False  # type: ignore[misc]


# --- resolution ----------------------------------------------------------------


def test_resolution_is_the_union_of_every_grant_in_force() -> None:
    """Additive by design (docs/roles-permissions.md §1.1): one person can be a clerk
    in one company and a viewer in another without a third role being invented."""
    resolved = resolve_permissions(
        [
            grant("invoice.read", "invoice.create", scope=Scope("company", COMPANY_A)),
            grant("report.read"),
        ],
        target=ScopePath(company_id=COMPANY_A),
        on_date=TODAY,
    )

    assert resolved == {"invoice.read", "invoice.create", "report.read"}


def test_resolution_drops_a_grant_scoped_to_another_company() -> None:
    resolved = resolve_permissions(
        [
            grant("invoice.post", scope=Scope("company", COMPANY_A)),
            grant("invoice.read", scope=Scope("company", COMPANY_B)),
        ],
        target=ScopePath(company_id=COMPANY_B),
        on_date=TODAY,
    )

    assert resolved == {"invoice.read"}


def test_resolution_reaches_a_department_from_its_company() -> None:
    resolved = resolve_permissions(
        [grant("invoice.post", scope=Scope("company", COMPANY_A))],
        target=ScopePath(company_id=COMPANY_A, department_id=DEPARTMENT_A1),
        on_date=TODAY,
    )

    assert resolved == {"invoice.post"}


def test_resolution_drops_a_lapsed_grant() -> None:
    resolved = resolve_permissions(
        [
            grant("audit.read", valid_from=APRIL, valid_to=dt.date(2026, 8, 31)),
            grant("report.read"),
        ],
        target=ScopePath(),
        on_date=TODAY,
    )

    assert resolved == {"report.read"}


def test_resolution_with_no_grants_is_empty_rather_than_an_error() -> None:
    """A user with no assignment is the normal state of a newly invited user
    (docs/roles-permissions.md §7). It has to resolve to nothing, not to a failure a
    route might mistake for a server error."""
    assert resolve_permissions([], target=ScopePath(), on_date=TODAY) == frozenset()


def test_resolution_returns_a_frozenset() -> None:
    """Cached per request and read by several checks; a mutable set would let one
    caller's ``add`` grant the next one a permission."""
    resolved = resolve_permissions([grant("report.read")], target=ScopePath(), on_date=TODAY)

    assert isinstance(resolved, frozenset)


# --- the check callers actually make ------------------------------------------


def test_has_permission_is_true_only_for_the_object_in_hand() -> None:
    grants = [grant("invoice.post", scope=Scope("company", COMPANY_A))]

    assert has_permission(
        grants, "invoice.post", target=ScopePath(company_id=COMPANY_A), on_date=TODAY
    )
    assert not has_permission(
        grants, "invoice.post", target=ScopePath(company_id=COMPANY_B), on_date=TODAY
    )


def test_an_unknown_required_permission_raises_rather_than_denying() -> None:
    """A typo in a route's declared permission must not become a permanent,
    plausible-looking 403 — nobody would think to grep the catalogue for it."""
    with pytest.raises(ValueError, match="not in the code catalogue"):
        has_permission([grant("invoice.post")], "invoice.postt", target=ScopePath(), on_date=TODAY)


def test_the_unknown_permission_failure_names_the_check() -> None:
    with pytest.raises(ValueError, match="named by a permission check"):
        has_permission([], "invoice.publish", target=ScopePath(), on_date=TODAY)


def test_assert_permitted_passes_for_a_grant_in_force() -> None:
    assert_permitted(
        [grant("invoice.post", scope=Scope("company", COMPANY_A))],
        "invoice.post",
        target=ScopePath(company_id=COMPANY_A),
        on_date=TODAY,
    )


def test_no_grants_at_all_is_a_403() -> None:
    """Deny by default (CLAUDE.md §5.1)."""
    with pytest.raises(PermissionDeniedError) as raised:
        assert_permitted([], "invoice.post", target=ScopePath(), on_date=TODAY)

    assert raised.value.status_code == 403
    assert raised.value.code == "permission_denied"


def test_the_right_permission_on_the_wrong_company_is_a_403() -> None:
    """**The test the exit criterion names** (docs/identity-db-plan.md, Phase 5), one
    layer below the route: the actor holds the key and is refused because the object
    is not theirs."""
    with pytest.raises(PermissionDeniedError):
        assert_permitted(
            [grant("invoice.post", scope=Scope("company", COMPANY_A))],
            "invoice.post",
            target=ScopePath(company_id=COMPANY_B),
            on_date=TODAY,
        )


def test_the_denial_names_the_permission_and_nothing_else() -> None:
    """A client needs to know what to ask for. It does not get the object, the actor,
    or which grants were considered — a denial that explains itself in detail is a
    scope-probing tool (CLAUDE.md §5.8)."""
    with pytest.raises(PermissionDeniedError) as raised:
        assert_permitted(
            [grant("invoice.read", scope=Scope("company", COMPANY_A))],
            "invoice.post",
            target=ScopePath(company_id=COMPANY_B),
            on_date=TODAY,
        )

    message = raised.value.message

    assert message == "this action requires invoice.post"
    assert str(COMPANY_A) not in message
    assert str(COMPANY_B) not in message


def test_the_envelope_carries_no_field_detail_for_a_denial() -> None:
    """403 is not 422: there is no field to correct, and inventing one would tell the
    caller which part of the object made them fail."""
    envelope = None
    try:
        assert_permitted([], "report.export", target=ScopePath(), on_date=TODAY)
    except PermissionDeniedError as denied:
        envelope = denied.envelope(trace_id="t-1")

    assert envelope is not None
    assert envelope.error.fields is None
    assert envelope.error.code == "permission_denied"
    assert envelope.error.trace_id == "t-1"


def test_resolution_never_takes_a_tenant_id() -> None:
    """Isolation is the session-level filter (CLAUDE.md §5.3), so the grants a caller
    holds are already its own tenant's. A ``tenant_id`` parameter here would read as
    the isolation check while duplicating the one that cannot be forgotten — and a
    reviewer would then have to prove it was passed correctly at every call site."""
    for function in (resolve_permissions, has_permission, assert_permitted):
        assert "tenant_id" not in inspect.signature(function).parameters


def test_nothing_here_takes_a_session() -> None:
    """Grants are passed in, never queried (CLAUDE.md invariant 7): a query from
    inside a permission check would be a second data path with no tenant scope of its
    own, and inside a money transaction a synchronous cross-service call."""
    forbidden = {"session", "db", "connection", "engine"}
    for function in (resolve_permissions, has_permission, assert_permitted):
        assert not set(inspect.signature(function).parameters) & forbidden


def test_a_target_is_required_and_has_no_default() -> None:
    """The design point of the module. A default target would make
    ``assert_permitted(grants, "invoice.post")`` compile, read as complete, and check
    only the key — CLAUDE.md §5.2 in one forgotten argument."""
    for function in (resolve_permissions, has_permission, assert_permitted):
        target = inspect.signature(function).parameters["target"]
        assert target.default is inspect.Parameter.empty
        assert target.kind is inspect.Parameter.KEYWORD_ONLY


def test_a_scope_id_is_a_uuid_not_a_string() -> None:
    """``BINARY(16)`` on both sides. A string here would compare unequal to the
    persisted value and every company-scoped grant would silently stop matching."""
    assert isinstance(Scope("company", COMPANY_A).scope_id, uuid.UUID)


# --- wire codec -------------------------------------------------------------
#
# The codec feeds both the permission cache and the gateway's signed context, so a
# grant must survive the round trip byte-for-meaning: the tenant-scope sentinel, the
# open-ended validity window, the revocation flag.


def test_grant_round_trips_through_wire() -> None:
    original = grant(
        "invoice.post",
        "invoice.read",
        scope=Scope("company", COMPANY_A),
        valid_from=APRIL,
        valid_to=MARCH_31,
        is_active=True,
    )
    assert grant_from_wire(grant_to_wire(original)) == original


def test_tenant_scope_id_is_null_on_the_wire_and_the_sentinel_in_memory() -> None:
    """The API boundary speaks ``null``; the resolver speaks ``SCOPE_ALL``. A tenant
    grant that leaked a real id here would read as a company grant on the way back."""
    wire = grant_to_wire(grant("company.read", scope=TENANT_SCOPE))
    assert wire["scope_id"] is None
    assert grant_from_wire(wire).scope.scope_id == SCOPE_ALL


def test_encode_decode_preserves_grants_and_groups() -> None:
    groups = {COMPANY_A, COMPANY_B}  # any uuids; group ids are opaque here
    grants = (
        grant("company.read", scope=Scope("company", COMPANY_A)),
        grant("role.assign", scope=TENANT_SCOPE, valid_to=None, is_active=False),
    )
    decoded_grants, decoded_groups = decode_grants(encode_grants(grants, groups))
    assert decoded_grants == grants
    assert decoded_groups == frozenset(groups)


def test_encode_is_stable_regardless_of_permission_order() -> None:
    """A stable encoding means an identical authority set produces an identical cache
    value and an identical signed context — no spurious cache misses or signatures."""
    a = grant("b.read", "a.read", scope=TENANT_SCOPE)
    b = grant("a.read", "b.read", scope=TENANT_SCOPE)
    assert encode_grants([a], []) == encode_grants([b], [])


def test_decode_rejects_a_malformed_payload() -> None:
    """A poisoned or truncated cache entry must raise, so the caller treats it as a
    miss and re-resolves rather than trusting garbage."""
    with pytest.raises((ValueError, KeyError)):
        decode_grants('{"grants":[{"scope_type":"company"}],"groups":[]}')
    with pytest.raises(ValueError):
        decode_grants("not json")

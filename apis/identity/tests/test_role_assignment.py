"""``role_assignment`` — the triple, the sentinel in the unique key, and the two windows.

The resolution logic is tested with no database at all, in ``libs/platform``'s
``test_authz.py``. What is tested here is the storage it reads: one row per
``(subject, role, scope)``, a tenant-scope grant that cannot be written twice, and a
system role that stays assignable across the ``tenant_id`` mismatch. The last test in the
file closes the loop by resolving real rows through ``billing_platform.authz``.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.authz import Grant, Scope, ScopePath, resolve_permissions
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.testing import table_of
from sqlalchemy import UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import (
    ASSIGNMENT_SCOPE_TYPES,
    SUBJECT_TYPES,
    Role,
    RoleAssignment,
    RolePermission,
    Tenant,
)
from tests.factories import (
    build_role,
    build_role_assignment,
    build_role_permission,
    build_user,
    seed_system_role,
    seed_two_companies,
    seed_two_tenants,
)

TODAY = dt.date(2026, 9, 3)


async def _one_role_and_user_per_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> tuple[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, uuid.UUID]]:
    """``((role_a, user_a), (role_b, user_b))`` — the minimum an assignment needs."""
    role_a, role_b, user_a, user_b = uuid7(), uuid7(), uuid7(), uuid7()
    await seed_two_tenants(session, tenant_a, tenant_b)
    with unfiltered():
        session.add_all(
            [
                build_role(tenant_id=tenant_a, role_id=role_a, key="alpha_clerk"),
                build_role(tenant_id=tenant_b, role_id=role_b, key="beta_clerk"),
                build_user(tenant_id=tenant_a, user_id=user_a, email="asha@alpha.example"),
                build_user(tenant_id=tenant_b, user_id=user_b, email="bo@beta.example"),
            ]
        )
        await session.commit()
    return (role_a, user_a), (role_b, user_b)


# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_assignments(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Deliberately **not** ``__tenant_shared__``, unlike ``role``: a tenant may assign a
    shipped role, but the assignment is that tenant's own row. This is the table that says
    who can do what."""
    (role_a, user_a), (role_b, user_b) = await _one_role_and_user_per_tenant(
        session, tenant_a, tenant_b
    )

    with unfiltered():
        session.add_all(
            [
                build_role_assignment(tenant_id=tenant_a, role_id=role_a, subject_id=user_a),
                build_role_assignment(tenant_id=tenant_b, role_id=role_b, subject_id=user_b),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        subjects = (await session.execute(select(RoleAssignment.subject_id))).scalars().all()

    assert subjects == [user_a]


async def test_the_other_tenants_assignment_is_not_reachable_by_id(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Reading it is a map of who holds what in another business; writing it would be
    granting yourself their permissions."""
    (role_a, user_a), (role_b, user_b) = await _one_role_and_user_per_tenant(
        session, tenant_a, tenant_b
    )
    theirs = build_role_assignment(tenant_id=tenant_b, role_id=role_b, subject_id=user_b)

    with unfiltered():
        session.add_all(
            [
                theirs,
                build_role_assignment(tenant_id=tenant_a, role_id=role_a, subject_id=user_a),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(RoleAssignment).where(RoleAssignment.id == theirs.id))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(RoleAssignment.id)))).scalar_one()

    assert found is None
    assert counted == 1


async def test_an_assignment_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    (role_a, user_a), _ = await _one_role_and_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role_assignment(tenant_id=tenant_a, role_id=role_a, subject_id=user_a))
        await session.commit()

    with pytest.raises(TenantContextError):
        await session.execute(select(RoleAssignment))


async def test_every_assignment_tenant_id_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """§1.4's compensating control. No sentinel exception here: unlike ``role``, every
    assignment belongs to exactly one real tenant."""
    (role_a, user_a), (role_b, user_b) = await _one_role_and_user_per_tenant(
        session, tenant_a, tenant_b
    )

    with unfiltered():
        session.add_all(
            [
                build_role_assignment(tenant_id=tenant_a, role_id=role_a, subject_id=user_a),
                build_role_assignment(tenant_id=tenant_b, role_id=role_b, subject_id=user_b),
            ]
        )
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(RoleAssignment.tenant_id))).scalars().all())

    assert owners
    assert owners <= tenants
    assert SCOPE_ALL not in owners


# --- the unique key and the sentinel ------------------------------------------


def test_the_shortened_unique_key_names_the_columns_it_no_longer_lists() -> None:
    """The name this convention would produce —
    ``uq_role_assignment_subject_type_subject_id_role_id_scope_type_scope_id`` — is 70
    characters, past the 64-character limit (docs/identity-db-plan.md §1.3). Each
    ``<thing>_type, <thing>_id`` pair collapses to ``<thing>``, so the name stops being
    the record of what is constrained and this test becomes it."""
    key = next(
        constraint
        for constraint in table_of(RoleAssignment).constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_role_assignment_subject_role_scope"
    )

    assert [column.name for column in key.columns] == [
        "subject_type",
        "subject_id",
        "role_id",
        "scope_type",
        "scope_id",
    ]
    assert len("uq_role_assignment_subject_role_scope") <= 64


async def test_one_subject_cannot_hold_one_role_tenant_wide_twice(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**The reason ``scope_id`` is NOT NULL** (docs/identity-db-plan.md §2). With the
    doc's nullable column MariaDB would treat the two NULLs as distinct and this would
    insert — leaving two grants of the same role, each needing its own revocation, one of
    which somebody will miss."""
    (role_a, user_a), _ = await _one_role_and_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role_assignment(tenant_id=tenant_a, role_id=role_a, subject_id=user_a))
        await session.commit()

        session.add(
            build_role_assignment(
                tenant_id=tenant_a, role_id=role_a, subject_id=user_a, grant_reason="again"
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_one_subject_may_hold_one_role_in_two_companies(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The narrower scopes are what make an assignment repeatable, and this is the shape
    docs/roles-permissions.md §1.1 exists for: one person, clerk in two companies, no
    third role invented for them."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    second_company = uuid7()
    role_a, user_a = uuid7(), uuid7()

    with unfiltered():
        session.add_all(
            [
                build_role(tenant_id=tenant_a, role_id=role_a, key="alpha_clerk"),
                build_user(tenant_id=tenant_a, user_id=user_a, email="asha@alpha.example"),
            ]
        )
        await session.commit()
        session.add_all(
            [
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=role_a,
                    subject_id=user_a,
                    scope_type="company",
                    scope_id=company_a,
                ),
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=role_a,
                    subject_id=user_a,
                    scope_type="company",
                    scope_id=second_company,
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        counted = (await session.execute(select(func.count(RoleAssignment.id)))).scalar_one()

    assert counted == 2


# --- the foreign keys, and the two deliberately missing -----------------------


async def test_an_assignment_must_name_a_real_role(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    (_, user_a), _ = await _one_role_and_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role_assignment(tenant_id=tenant_a, role_id=uuid7(), subject_id=user_a))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_tenant_may_assign_a_system_role_despite_the_tenant_mismatch(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**Why this foreign key is plain and not composite** like ``role_permission``'s. The
    assignment sits at ``tenant_a`` and the role at ``SCOPE_ALL``, so requiring the two to
    agree would make all twelve shipped roles unassignable — the constraint would read as
    a tightening and land as an outage."""
    (_, user_a), _ = await _one_role_and_user_per_tenant(session, tenant_a, tenant_b)
    system_role_id = await seed_system_role(session, key="billing_clerk")

    with unfiltered():
        session.add(
            build_role_assignment(tenant_id=tenant_a, role_id=system_role_id, subject_id=user_a)
        )
        await session.commit()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(RoleAssignment))).scalar_one()

    assert found.tenant_id == tenant_a
    assert found.role_id == system_role_id


def test_the_polymorphic_columns_carry_no_foreign_key() -> None:
    """``subject_id`` points at ``user`` or ``user_group`` by ``subject_type``, and
    ``scope_id`` at ``company`` or ``department`` — or at neither, when it holds the
    sentinel. No single constraint expresses that, so both are resolved in ``domain/``
    before the row is written and never trusted from the request."""
    columns = table_of(RoleAssignment).c

    assert columns.subject_id.foreign_keys == set()
    assert columns.scope_id.foreign_keys == set()
    assert columns.role_id.foreign_keys != set()


def test_the_documented_subject_and_scope_types_are_the_ones_the_code_knows() -> None:
    """A role is granted to a user or a group, never to a company — that is a *scope*, the
    other half of the triple. Conflating them would make "everyone in company A" a grant
    that silently follows company A's membership."""
    assert SUBJECT_TYPES == {"user", "user_group"}
    assert ASSIGNMENT_SCOPE_TYPES == {"tenant", "company", "department"}


# --- revocation and the window ------------------------------------------------


def test_the_table_carries_both_date_mechanisms_deliberately() -> None:
    """Rule 4.12 forbids two *competing* lifecycles; these do not compete.
    ``is_active`` false is **revocation**, which must take effect the moment it is written
    and cannot be expressed as a date. The window is **scheduled elevation** — the
    year-end auditor whose access lapses on a date rather than when someone remembers.
    Both must pass for a grant to be in force, so neither can override the other in the
    permissive direction."""
    columns = set(table_of(RoleAssignment).c.keys())

    assert {"is_active", "valid_from", "valid_to"} <= columns
    assert "status" not in columns


async def test_a_revoked_and_a_lapsed_assignment_both_survive_as_rows(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Neither mechanism deletes anything. An access review a year later asks who held
    what and when, and a deleted row answers nothing."""
    (role_a, user_a), _ = await _one_role_and_user_per_tenant(session, tenant_a, tenant_b)
    other_role = uuid7()

    with unfiltered():
        session.add(build_role(tenant_id=tenant_a, role_id=other_role, key="alpha_auditor"))
        await session.commit()
        session.add_all(
            [
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=role_a,
                    subject_id=user_a,
                    is_active=False,
                    deactivated_at=dt.datetime(2026, 7, 1, tzinfo=dt.UTC),
                ),
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=other_role,
                    subject_id=user_a,
                    valid_to=dt.date(2026, 8, 31),
                ),
            ]
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(RoleAssignment))).scalars().all()

    assert len(rows) == 2
    revoked = next(row for row in rows if not row.is_active)
    lapsed = next(row for row in rows if row.valid_to is not None)
    assert revoked.deactivated_at is not None
    assert lapsed.is_active is True


# --- the rows the resolver reads ----------------------------------------------


async def test_stored_rows_resolve_to_the_permissions_the_resolver_reports(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The join this schema exists to serve, end to end: assignment → role → permission
    keys → ``resolve_permissions``.

    Three grants are stored for one user — a system role tenant-wide, a tenant role on
    company A, and a tenant role on company B — and the resolution for company A returns
    the first two only. ``scope_id = SCOPE_ALL`` maps straight onto ``Scope("tenant")``,
    which is the whole reason the sentinel is the stored value rather than NULL.
    """
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    company_b_of_a = uuid7()
    user_a, clerk, viewer = uuid7(), uuid7(), uuid7()
    system_role_id = await seed_system_role(
        session, key="tenant_auditor", permission_key="audit.read"
    )

    with unfiltered():
        session.add_all(
            [
                build_user(tenant_id=tenant_a, user_id=user_a, email="asha@alpha.example"),
                build_role(tenant_id=tenant_a, role_id=clerk, key="alpha_clerk"),
                build_role(tenant_id=tenant_a, role_id=viewer, key="alpha_viewer"),
            ]
        )
        await session.commit()
        session.add_all(
            [
                build_role_permission(
                    tenant_id=tenant_a, role_id=clerk, permission_key="invoice.create"
                ),
                build_role_permission(
                    tenant_id=tenant_a, role_id=viewer, permission_key="invoice.read"
                ),
                build_role_assignment(
                    tenant_id=tenant_a, role_id=system_role_id, subject_id=user_a
                ),
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=clerk,
                    subject_id=user_a,
                    scope_type="company",
                    scope_id=company_a,
                ),
                build_role_assignment(
                    tenant_id=tenant_a,
                    role_id=viewer,
                    subject_id=user_a,
                    scope_type="company",
                    scope_id=company_b_of_a,
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (
            (
                await session.execute(
                    select(RoleAssignment).where(RoleAssignment.subject_id == user_a)
                )
            )
            .scalars()
            .all()
        )
        keys_by_role: dict[uuid.UUID, set[str]] = {}
        for role_id, key in await session.execute(
            select(RolePermission.role_id, RolePermission.permission_key)
        ):
            keys_by_role.setdefault(role_id, set()).add(key)

    grants = [
        Grant(
            permissions=frozenset(keys_by_role.get(row.role_id, set())),
            scope=Scope(row.scope_type, row.scope_id),
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            is_active=row.is_active,
        )
        for row in rows
    ]

    assert resolve_permissions(grants, target=ScopePath(company_id=company_a), on_date=TODAY) == {
        "audit.read",
        "invoice.create",
    }
    assert resolve_permissions(grants, target=ScopePath(), on_date=TODAY) == {"audit.read"}


async def test_a_role_with_no_permissions_resolves_to_nothing_rather_than_everything(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """An empty bundle is a real state — a tenant creating a role before composing it —
    and it has to mean *no permissions*. The failure this guards is a resolver that read
    "no rows" as "unconstrained"."""
    (role_a, user_a), _ = await _one_role_and_user_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role_assignment(tenant_id=tenant_a, role_id=role_a, subject_id=user_a))
        await session.commit()

    with tenant_scope(tenant_a):
        row = (await session.execute(select(RoleAssignment))).scalar_one()
        keys = (
            (
                await session.execute(
                    select(RolePermission.permission_key).where(
                        RolePermission.role_id == row.role_id
                    )
                )
            )
            .scalars()
            .all()
        )
        role = (await session.execute(select(Role).where(Role.id == row.role_id))).scalar_one()

    assert role.is_active
    assert keys == []
    assert (
        resolve_permissions(
            [
                Grant(
                    permissions=frozenset(keys),
                    scope=Scope(row.scope_type, row.scope_id),
                    valid_from=row.valid_from,
                )
            ],
            target=ScopePath(),
            on_date=TODAY,
        )
        == frozenset()
    )

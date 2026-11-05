"""``user`` — isolation, the two unique keys that disagree about NULL, and the tombstone.

The two keys are the reason this file is longer than the pattern needs.
``uq_user_tenant_id_email`` is per tenant, so the same address must insert twice in two
tenants. ``uq_user_authentik_sub`` is global and nullable, so one subject must **not**
insert twice across tenants while any number of NULLs must — the opposite of every other
nullable unique key in this schema (docs/identity-db-plan.md §2).
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.testing import table_of
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import USER_STATUSES, USER_TYPES, Tenant, User
from tests.factories import (
    build_department,
    build_user,
    seed_two_companies,
    seed_two_tenants,
)

# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_users(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_user(tenant_id=tenant_a, email="asha@alpha.example"),
                build_user(tenant_id=tenant_b, email="bo@beta.example"),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(User))).scalars().all()

    assert [row.email for row in rows] == ["asha@alpha.example"]


async def test_the_other_tenants_user_is_not_reachable_by_id(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The highest-value read to block on this table: a user row names a real person,
    their manager and their job title."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    theirs = build_user(tenant_id=tenant_b, email="bo@beta.example")

    with unfiltered():
        session.add_all([theirs, build_user(tenant_id=tenant_a)])
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(User).where(User.id == theirs.id))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(User.id)))).scalar_one()

    assert found is None
    assert counted == 1


async def test_a_user_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_user(tenant_id=tenant_a))
        await session.commit()

    with pytest.raises(TenantContextError):
        await session.execute(select(User))


async def test_every_user_tenant_id_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The compensating control for ``tenant_id`` carrying no foreign key
    (docs/identity-db-plan.md §1.4)."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_user(tenant_id=tenant_a, email="asha@alpha.example"),
                build_user(tenant_id=tenant_b, email="bo@beta.example"),
            ]
        )
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(User.tenant_id))).scalars().all())

    assert owners
    assert owners <= tenants


# --- email: unique per tenant -------------------------------------------------


async def test_two_tenants_may_hold_the_same_email_address(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """docs/identity-schema.md §4.1. A consultant working for two customers is one
    address and two different people-in-context, and this single constraint is what
    stands between this model and a global ``principal`` (docs/org-model.md §4.3)."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_user(tenant_id=tenant_a, email="shared@example.com"),
                build_user(tenant_id=tenant_b, email="shared@example.com"),
            ]
        )
        await session.commit()

        counted = (await session.execute(select(func.count(User.id)))).scalar_one()

    assert counted == 2


async def test_one_tenant_cannot_hold_the_same_email_twice(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Two rows for one address means an invitation, a password reset and a lookup by
    email each resolve to whichever row is read first."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_user(tenant_id=tenant_a, email="asha@alpha.example"))
        await session.commit()

        session.add(build_user(tenant_id=tenant_a, email="asha@alpha.example"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# --- authentik_sub: unique globally, and NULL means "not yet" -----------------


async def test_one_authentik_subject_cannot_belong_to_two_users(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Across tenants, deliberately. The OIDC callback resolves by subject alone, so
    two rows sharing one would make a single login resolve to either of two accounts —
    in two different tenants."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_user(tenant_id=tenant_a, email="asha@alpha.example", authentik_sub="sub-1")
        )
        await session.commit()

        session.add(build_user(tenant_id=tenant_b, email="bo@beta.example", authentik_sub="sub-1"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_many_invited_users_coexist_with_no_subject_at_all(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """MariaDB treating NULLs inside a unique key as distinct is **wanted** here, and is
    the reverse of the sentinel case in docs/identity-db-plan.md §2: an invited user has
    no Authentik account yet, and provisioning one would mean creating a login for
    somebody who may never accept."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_user(tenant_id=tenant_a, email=f"invitee{n}@alpha.example", status="invited")
                for n in range(3)
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        subjects = (await session.execute(select(User.authentik_sub))).scalars().all()

    assert subjects == [None, None, None]


# --- the foreign keys, and the one deliberately missing -----------------------


async def test_a_reporting_manager_must_be_a_real_user(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_user(tenant_id=tenant_a, reporting_manager_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_user_may_report_to_another_user(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The self-referential key, which is what makes the FK worth having at all."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    manager_id = uuid7()

    with unfiltered():
        session.add(
            build_user(tenant_id=tenant_a, user_id=manager_id, email="manager@alpha.example")
        )
        await session.commit()
        session.add(
            build_user(
                tenant_id=tenant_a, email="report@alpha.example", reporting_manager_id=manager_id
            )
        )
        await session.commit()

    with tenant_scope(tenant_a):
        counted = (await session.execute(select(func.count(User.id)))).scalar_one()

    assert counted == 2


async def test_a_default_company_must_be_a_real_company(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_user(tenant_id=tenant_a, default_company_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_default_department_id_now_carries_the_deferred_foreign_key(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Phase 6 (revision 0020) adds the FK that revision 0014 deferred: the cycle
    ``user.default_department_id`` → ``department`` → ``company`` is now closed the
    intended direction (docs/identity-db-plan.md §1.5, §6). This is the rewrite the
    old ``..._no_foreign_key_yet`` test's docstring predicted.

    The constraint now names ``department.id`` and is enforced — a user may point only
    at a department that exists in its tenant."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    fks = table_of(User).c.default_department_id.foreign_keys
    assert {fk.column.table.name for fk in fks} == {"department"}

    dept_id = uuid7()
    with unfiltered():
        session.add(
            build_department(tenant_id=tenant_a, company_id=company_a, department_id=dept_id)
        )
        await session.flush()
        session.add(
            build_user(
                tenant_id=tenant_a, default_company_id=company_a, default_department_id=dept_id
            )
        )
        await session.commit()


# --- lifecycle and the tombstone ----------------------------------------------


def test_the_table_declares_exactly_one_lifecycle_mechanism() -> None:
    """Rule 4.12. ``status`` is the mechanism; the ``deactivated_*`` trio is evidence for
    one of its values, not a second switch. An ``is_active`` alongside it would make
    "can this person sign in" a question with two answers."""
    columns = set(table_of(User).c.keys())

    assert "status" in columns
    assert not columns & {"is_active", "valid_from", "valid_to"}


def test_the_documented_types_and_statuses_are_the_ones_the_code_knows() -> None:
    """``user_type`` decides which surface a principal sees and is **never** an
    authorization input (docs/roles-permissions.md §1.3) — what they may do comes from
    ``role_assignment`` alone."""
    assert USER_TYPES == {
        "platform_admin",
        "tenant_user",
        "customer_portal_user",
        "service_account",
    }
    assert USER_STATUSES == {"invited", "active", "suspended", "deactivated"}


def test_the_table_holds_no_credential_of_any_kind() -> None:
    """Credentials live in Authentik. A password hash, MFA secret, session or recovery
    code here would make this table a second authentication authority that can disagree
    with the first — and the disagreement would be resolved by whichever code path ran
    (CLAUDE.md §5.9)."""
    columns = set(table_of(User).c.keys())
    forbidden = {
        "password",
        "password_hash",
        "mfa_secret",
        "totp_secret",
        "recovery_codes",
        "session_token",
        "refresh_token",
        "api_key",
    }

    assert not columns & forbidden


async def test_anonymization_tombstones_the_pii_and_keeps_the_row(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """CLAUDE.md invariant 12: anonymize users, never delete them. A user who posted an
    invoice is referenced from the ledger forever, so ``id`` and ``employee_code``
    survive — they are what makes the remaining audit trail resolvable — while the name,
    address and phone do not."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    user_id = uuid7()

    with unfiltered():
        session.add(
            build_user(
                tenant_id=tenant_a,
                user_id=user_id,
                email="asha@alpha.example",
                employee_code="EMP-0041",
                phone="9820000000",
            )
        )
        await session.commit()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        found.first_name = "Removed"
        found.last_name = None
        found.display_name = "Removed user"
        found.email = f"anonymized+{user_id}@invalid"
        found.phone = None
        found.status = "deactivated"
        found.deactivated_at = dt.datetime(2026, 9, 3, tzinfo=dt.UTC)
        found.anonymized_at = dt.datetime(2026, 9, 3, tzinfo=dt.UTC)
        await session.commit()
        session.expunge_all()

        again = (await session.execute(select(User).where(User.id == user_id))).scalar_one()

    assert again.id == user_id
    assert again.employee_code == "EMP-0041"
    assert again.anonymized_at is not None
    assert "asha" not in again.email
    assert again.phone is None


async def test_display_preferences_round_trip_and_carry_no_precision(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A user may set a date format and a locale; a user may **not** set
    ``amount_precision``, ``quantity_precision`` or ``rounding_mode``, which change
    computed totals and are company-level and frozen once anything has posted
    (docs/company.md §4.5). Two users must never see different totals for one
    document."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_user(tenant_id=tenant_a, locale="en-IN", date_format="dd-MM-yyyy", theme="dark")
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(User))).scalar_one()

    assert (found.locale, found.date_format, found.theme) == ("en-IN", "dd-MM-yyyy", "dark")
    assert not set(table_of(User).c.keys()) & {
        "amount_precision",
        "quantity_precision",
        "rounding_mode",
    }


async def test_custom_fields_round_trip_as_a_mapping(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Store, validate, display, report — never price, tax, post or route approvals from
    one (CLAUDE.md invariant 14)."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_user(tenant_id=tenant_a, custom_fields={"cost_centre": "CC-12"}))
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(User))).scalar_one()

    assert found.custom_fields == {"cost_centre": "CC-12"}

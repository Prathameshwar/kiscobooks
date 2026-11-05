"""``company_address`` — isolation, the jurisdiction pair, and one-primary-per-type.

The composite foreign key matters more here than on `company`. A shipping address's
``state_code`` **is** the place of supply on an outbound invoice, so an impossible
pair does not merely look wrong in a print-out — it decides CGST+SGST versus IGST,
and the resulting return is filed against the wrong state.
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

from identity.models import ADDRESS_TYPES, CompanyAddress, Tenant
from tests.factories import build_company_address, seed_two_companies

# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_addresses(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_address(tenant_id=tenant_a, company_id=company_a, city="Mumbai"),
                build_company_address(tenant_id=tenant_b, company_id=company_b, city="Chennai"),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyAddress))).scalars().all()

    assert [row.city for row in rows] == ["Mumbai"]
    assert "Chennai" not in {row.city for row in rows}


async def test_knowing_the_other_addresss_id_is_not_enough(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """An address holds a customer-facing postal address and a registered office —
    the sort of row a cross-tenant read leaks quietly and usefully."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    theirs = build_company_address(tenant_id=tenant_b, company_id=company_b)

    with unfiltered():
        session.add_all([theirs, build_company_address(tenant_id=tenant_a, company_id=company_a)])
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(CompanyAddress).where(CompanyAddress.id == theirs.id))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(CompanyAddress.id)))).scalar_one()

    assert found is None
    assert counted == 1


async def test_an_address_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_address(tenant_id=tenant_a, company_id=company_a))
        await session.commit()

    with pytest.raises(TenantContextError):
        await session.execute(select(CompanyAddress))


async def test_every_address_tenant_id_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The compensating control for ``tenant_id`` carrying no foreign key
    (docs/identity-db-plan.md §1.4), which the plan requires **per tenant-scoped
    table** — only `company` had one."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_address(tenant_id=tenant_a, company_id=company_a),
                build_company_address(tenant_id=tenant_b, company_id=company_b),
            ]
        )
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(CompanyAddress.tenant_id))).scalars().all())

    assert owners
    assert owners <= tenants


# --- the jurisdiction foreign key ---------------------------------------------


async def test_a_shipping_address_in_an_impossible_state_is_rejected(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """`fk_company_address_country_code_state_code`. This pair is the place of supply,
    so the database refuses it rather than trusting a form's dropdown."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_company_address(
                tenant_id=tenant_a,
                company_id=company_a,
                address_type="shipping",
                country_code="IN",
                state_code="US-CA",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_an_address_must_belong_to_a_real_company(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_address(tenant_id=tenant_a, company_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# --- primary, types and lifecycle ---------------------------------------------


async def test_two_primary_addresses_of_one_type_are_not_stopped_by_the_database(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**Documents a gap the schema cannot close.**

    "One primary per type" needs a unique key over ``(company_id, type)`` restricted
    to ``is_primary = 1``, and MariaDB has no partial unique index. So the rule lives
    in `domain/`, and this test asserts the database's *silence* — otherwise the
    missing constraint reads as an oversight and the `domain/` check as redundant.
    """
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_address(
                    tenant_id=tenant_a,
                    company_id=company_a,
                    address_type="billing",
                    is_primary=True,
                ),
                build_company_address(
                    tenant_id=tenant_a,
                    company_id=company_a,
                    address_type="billing",
                    is_primary=True,
                    line1="2 Nariman Point",
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        primaries = (
            await session.execute(
                select(func.count(CompanyAddress.id)).where(CompanyAddress.is_primary.is_(True))
            )
        ).scalar_one()

    assert primaries == 2, "the database allows it; domain/ is the only thing that does not"


async def test_several_addresses_of_different_types_coexist(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """No unique key on ``(company_id, type)`` either: a company legitimately has
    many shipping addresses, and many branches."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_address(tenant_id=tenant_a, company_id=company_a, address_type=kind)
                for kind in sorted(ADDRESS_TYPES)
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyAddress))).scalars().all()

    assert {row.type for row in rows} == ADDRESS_TYPES


async def test_a_deactivated_address_keeps_its_row_and_its_actor(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """`DeactivableMixin`, not a delete: a posted invoice printed this address, so the
    row has to remain readable (invariant 12). Deactivation only removes it from the
    pick list for new documents."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    actor = uuid7()

    with unfiltered():
        session.add(
            build_company_address(
                tenant_id=tenant_a,
                company_id=company_a,
                is_active=False,
                deactivated_at=dt.datetime(2026, 8, 1, 9, 30, tzinfo=dt.UTC),
                deactivated_by=actor,
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyAddress))).scalar_one()

    assert found.is_active is False
    assert found.deactivated_by == actor
    assert found.deactivated_at is not None
    assert found.deactivated_at.tzinfo is not None, "timestamps come back UTC-aware"


def test_the_table_declares_exactly_one_lifecycle_mechanism() -> None:
    """Rule 4.12. `is_active` here — an address does not affect a computed amount
    retroactively, so it needs no validity dates and carries no `status`."""
    columns = set(table_of(CompanyAddress).c.keys())

    assert "is_active" in columns
    assert not columns & {"status", "valid_from", "valid_to"}


def test_the_documented_address_types_are_the_ones_the_code_knows() -> None:
    assert ADDRESS_TYPES == {"registered", "billing", "shipping", "branch"}


def test_the_type_index_leads_with_company_id() -> None:
    """docs/identity-schema.md §3.5, and the exception to §1.7 is deliberate: an index
    supporting `fk_company_address_company_id` must begin with that column or InnoDB
    invents a second, invisible one — and `company_id` functionally determines
    `tenant_id`, so the tenant-filtered query can still use it."""
    index = next(
        ix
        for ix in table_of(CompanyAddress).indexes
        if ix.name == "ix_company_address_company_id_type"
    )

    assert [column.name for column in index.columns] == ["company_id", "type"]

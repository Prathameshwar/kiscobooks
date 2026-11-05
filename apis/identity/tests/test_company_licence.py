"""``company_licence`` — isolation, the renewal key, and the expiry sweep's index.

The gate itself — whether a document may be posted — is tested with no database in
`libs/platform/tests/test_statutory.py`. What is tested here is the storage it reads:
a renewal is a new row rather than an edit, several licences of one kind coexist
because a licence is per premises, and the cross-tenant expiry index exists.

That last one is the odd column out on this table. Every other index here leads with
`company_id`; ``ix_company_licence_valid_to`` deliberately leads with neither
`tenant_id` nor `company_id`, because the Beat job asks "what expires soon" across
every tenant at once.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.statutory import Licence, assert_company_can_issue, resolve_licence
from billing_platform.testing import table_of
from sqlalchemy import UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import CompanyLicence, Tenant
from tests.factories import build_company_address, build_company_licence, seed_two_companies

APRIL = dt.date(2026, 4, 1)

# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_licences(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_licence(
                    tenant_id=tenant_a, company_id=company_a, number="MH-MUM-20B-0001"
                ),
                build_company_licence(
                    tenant_id=tenant_b, company_id=company_b, number="KA-BLR-20B-0002"
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyLicence))).scalars().all()

    assert [row.number for row in rows] == ["MH-MUM-20B-0001"]
    assert "KA-BLR-20B-0002" not in {row.number for row in rows}


async def test_the_other_tenants_licence_is_not_reachable_by_id(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Which licences a competitor holds is what it is permitted to trade in, and the
    premises address says where from."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    theirs = build_company_licence(tenant_id=tenant_b, company_id=company_b)

    with unfiltered():
        session.add_all([theirs, build_company_licence(tenant_id=tenant_a, company_id=company_a)])
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(CompanyLicence).where(CompanyLicence.id == theirs.id))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(CompanyLicence.id)))).scalar_one()

    assert found is None
    assert counted == 1


async def test_a_licence_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_licence(tenant_id=tenant_a, company_id=company_a))
        await session.commit()

    with pytest.raises(TenantContextError):
        await session.execute(select(CompanyLicence))


async def test_every_licence_tenant_id_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The compensating control for ``tenant_id`` carrying no foreign key
    (docs/identity-db-plan.md §1.4)."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_licence(tenant_id=tenant_a, company_id=company_a),
                build_company_licence(tenant_id=tenant_b, company_id=company_b),
            ]
        )
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(CompanyLicence.tenant_id))).scalars().all())

    assert owners
    assert owners <= tenants


async def test_a_licence_must_belong_to_a_real_company(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_licence(tenant_id=tenant_a, company_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# --- the table's own keys -----------------------------------------------------


async def test_the_same_licence_cannot_be_added_twice_from_the_same_date(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """`uq_company_licence_company_id_kind_number_valid_from`."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_licence(tenant_id=tenant_a, company_id=company_a))
        await session.commit()

        session.add(build_company_licence(tenant_id=tenant_a, company_id=company_a))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_renewal_is_a_new_row_with_the_same_number(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The reason ``valid_from`` is in the key: an authority reissues the *same* licence
    number for the next term, so the number repeats and the start date distinguishes
    them. Editing the old row instead would change what an already-posted invoice
    printed."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_licence(
                    tenant_id=tenant_a, company_id=company_a, valid_to=dt.date(2031, 3, 31)
                ),
                build_company_licence(
                    tenant_id=tenant_a,
                    company_id=company_a,
                    valid_from=dt.date(2031, 4, 1),
                    valid_to=dt.date(2036, 3, 31),
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyLicence))).scalars().all()

    assert len({row.number for row in rows}) == 1
    assert len(rows) == 2


async def test_several_licences_of_one_kind_may_be_valid_at_once(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A licence is per premises, which is why ``resolve_licence`` *chooses* rather than
    treating two matches as ambiguous the way a tax registration does."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_licence(
                    tenant_id=tenant_a, company_id=company_a, number="MH-MUM-20B-0001"
                ),
                build_company_licence(
                    tenant_id=tenant_a, company_id=company_a, number="MH-PUN-20B-0002"
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        counted = (await session.execute(select(func.count(CompanyLicence.id)))).scalar_one()

    assert counted == 2


async def test_two_companies_may_hold_the_same_licence_number(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_licence(tenant_id=tenant_a, company_id=company_a),
                build_company_licence(tenant_id=tenant_b, company_id=company_b),
            ]
        )
        await session.commit()

        counted = (await session.execute(select(func.count(CompanyLicence.id)))).scalar_one()

    assert counted == 2


def test_the_unique_key_names_its_columns() -> None:
    key = next(
        constraint
        for constraint in table_of(CompanyLicence).constraints
        if isinstance(constraint, UniqueConstraint)
    )

    assert key.name == "uq_company_licence_company_id_kind_number_valid_from"
    assert [column.name for column in key.columns] == [
        "company_id",
        "kind",
        "number",
        "valid_from",
    ]


def test_kind_carries_no_foreign_key() -> None:
    """Kinds are code, and the profile also carries what each one ``gates`` — a `kind`
    table would let a tenant invent a licence that permits nothing."""
    assert table_of(CompanyLicence).c.kind.foreign_keys == set()


def test_the_resolution_index_leads_with_company_id() -> None:
    """§1.7's two exceptions: it supports `fk_company_licence_company_id`, and
    `company_id` functionally determines `tenant_id`."""
    index = next(
        ix
        for ix in table_of(CompanyLicence).indexes
        if ix.name == "ix_company_licence_company_id_kind_valid_from_valid_to"
    )

    assert [column.name for column in index.columns] == [
        "company_id",
        "kind",
        "valid_from",
        "valid_to",
    ]


def test_the_expiry_sweep_index_leads_with_neither_tenant_nor_company() -> None:
    """**The one index on this table that is not per company.** The Beat job asks "what
    expires soon" across every tenant, runs under ``unfiltered()`` by construction, and
    is its only reader — so leading with `tenant_id` would make it useless for the query
    it exists for."""
    index = next(
        ix for ix in table_of(CompanyLicence).indexes if ix.name == "ix_company_licence_valid_to"
    )

    assert [column.name for column in index.columns] == ["valid_to"]


async def test_the_expiry_sweep_reads_across_tenants_under_unfiltered(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The index has a reader, and this is its shape: one query, every tenant, ordered
    by expiry. It is only ever run by the Beat job — a request path doing this is the
    cross-tenant read the filter exists to prevent, which is why ``unfiltered()`` has to
    be written explicitly."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_licence(
                    tenant_id=tenant_a, company_id=company_a, valid_to=dt.date(2026, 10, 31)
                ),
                build_company_licence(
                    tenant_id=tenant_b, company_id=company_b, valid_to=dt.date(2026, 9, 30)
                ),
            ]
        )
        await session.commit()

        expiring = (
            (
                await session.execute(
                    select(CompanyLicence)
                    .where(CompanyLicence.valid_to <= dt.date(2026, 12, 31))
                    .order_by(CompanyLicence.valid_to)
                )
            )
            .scalars()
            .all()
        )

    assert [row.valid_to for row in expiring] == [dt.date(2026, 9, 30), dt.date(2026, 10, 31)]
    assert {row.tenant_id for row in expiring} == {tenant_a, tenant_b}


async def test_the_premises_address_must_be_a_real_address(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_company_licence(
                tenant_id=tenant_a, company_id=company_a, premises_address_id=uuid7()
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_licence_may_name_the_premises_it_covers(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    branch = build_company_address(
        tenant_id=tenant_a, company_id=company_a, address_type="branch", is_primary=False
    )

    with unfiltered():
        session.add(branch)
        await session.commit()
        session.add(
            build_company_licence(
                tenant_id=tenant_a, company_id=company_a, premises_address_id=branch.id
            )
        )
        await session.commit()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyLicence))).scalar_one()

    assert found.premises_address_id == branch.id


# --- lifecycle and what the gate reads ----------------------------------------


def test_the_table_declares_exactly_one_lifecycle_mechanism() -> None:
    """Rule 4.12, and dates rather than a boolean because the licence printed on a
    document is the one valid on its ``posting_date`` — a reprint of an old invoice must
    show the licence that was in force then, not the current one."""
    columns = set(table_of(CompanyLicence).c.keys())

    assert {"valid_from", "valid_to"} <= columns
    assert not columns & {"status", "is_active", "deactivated_at", "deactivated_by"}


async def test_a_licence_round_trips_with_its_reminder_lead_time(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """``renewal_reminder_days`` is a ``SMALLINT`` day count, not a date: the reminder is
    computed from the expiry, so storing a second date would let the two disagree."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_company_licence(
                tenant_id=tenant_a,
                company_id=company_a,
                issuing_authority="Maharashtra FDA",
                renewal_reminder_days=90,
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyLicence))).scalar_one()

    assert found.renewal_reminder_days == 90
    assert found.issuing_authority == "Maharashtra FDA"
    assert found.issued_on == dt.date(2026, 3, 20)


async def test_stored_licences_feed_the_posting_gate_unchanged(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The seam between this table and ``billing_platform.statutory``: a service maps its
    replicated rows to value objects and the gate decides. Tested here because a column
    renamed on one side and not the other would leave both unit suites green."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        premises = build_company_address(tenant_id=tenant_a, company_id=company_a)
        session.add(premises)
        session.add(
            build_company_licence(
                tenant_id=tenant_a,
                company_id=company_a,
                valid_to=dt.date(2026, 9, 30),
                premises_address_id=premises.id,
            )
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyLicence))).scalars().all()

    replicated = [
        Licence(
            kind=row.kind,
            number=row.number,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            is_primary=row.is_primary,
            premises_address_id=row.premises_address_id,
        )
        for row in rows
    ]

    assert_company_can_issue(
        replicated,
        country_code="IN",
        posting_date=APRIL,
        line_gates=("scheduled_drug",),
        operation="WHOLESALE",
        premises_address_id=premises.id,
        drug_class="OTHER_THAN_C_C1_X",
    )
    found = resolve_licence(replicated, kind="drug_licence_20b", posting_date=APRIL)
    assert found is not None
    assert found.number == "MH-MUM-20B-4471"


async def test_a_document_dated_after_the_licence_lapsed_is_refused(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The whole reason this table gates rather than decorates: the same stored row
    permits an April posting and refuses an October one."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        premises = build_company_address(tenant_id=tenant_a, company_id=company_a)
        session.add(premises)
        session.add(
            build_company_licence(
                tenant_id=tenant_a,
                company_id=company_a,
                valid_to=dt.date(2026, 9, 30),
                premises_address_id=premises.id,
            )
        )
        await session.commit()

    with tenant_scope(tenant_a):
        row = (await session.execute(select(CompanyLicence))).scalar_one()

    replicated = [
        Licence(
            kind=row.kind,
            number=row.number,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            premises_address_id=row.premises_address_id,
        )
    ]

    with pytest.raises(ConflictError):
        assert_company_can_issue(
            replicated,
            country_code="IN",
            posting_date=dt.date(2026, 10, 1),
            line_gates=("scheduled_drug",),
            operation="WHOLESALE",
            premises_address_id=premises.id,
            drug_class="OTHER_THAN_C_C1_X",
        )

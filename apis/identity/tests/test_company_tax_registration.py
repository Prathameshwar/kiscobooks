"""``company_tax_registration`` — isolation, the validity key, and what resolution reads.

The date arithmetic itself is tested with no database at all, in
`libs/platform/tests/test_statutory.py`. What is tested here is the storage those
rules depend on: rows survive a round trip with their windows intact, the unique key
stops an exact duplicate, ``jurisdiction_code`` carries no foreign key because no
single target covers both a state and a country, and — the highest-value test on this
table — a competitor's GSTIN is unreachable.

A leaked registration row is a leaked GSTIN, a legal name, and a registered address
in one read, which is a filing identity rather than a piece of configuration.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.statutory import TaxRegistration, resolve_tax_registration
from billing_platform.testing import table_of
from sqlalchemy import UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import CompanyTaxRegistration, Tenant
from tests.factories import (
    build_company_address,
    build_company_tax_registration,
    seed_two_companies,
)

SEPTEMBER_30 = dt.date(2026, 9, 30)
OCTOBER = dt.date(2026, 10, 1)

# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_registrations(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_tax_registration(
                    tenant_id=tenant_a, company_id=company_a, number="27AAAPA1234A1ZT"
                ),
                build_company_tax_registration(
                    tenant_id=tenant_b,
                    company_id=company_b,
                    jurisdiction_code="KA",
                    number="29BBBPB5678B1ZU",
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyTaxRegistration))).scalars().all()

    assert [row.number for row in rows] == ["27AAAPA1234A1ZT"]
    assert "29BBBPB5678B1ZU" not in {row.number for row in rows}


async def test_the_other_tenants_registration_is_not_reachable_by_id(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A GSTIN is a public-facing number, but the row it sits in carries the legal name
    as registered and the registered address, which together are a filing identity."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    theirs = build_company_tax_registration(tenant_id=tenant_b, company_id=company_b)

    with unfiltered():
        session.add_all(
            [
                theirs,
                build_company_tax_registration(tenant_id=tenant_a, company_id=company_a),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(
                select(CompanyTaxRegistration).where(CompanyTaxRegistration.id == theirs.id)
            )
        ).scalar_one_or_none()

    assert found is None


async def test_an_aggregate_over_registrations_is_filtered_too(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The leak that a row-level test misses: ``COUNT`` reveals how many states a
    competitor is registered in, which is its footprint."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_tax_registration(tenant_id=tenant_a, company_id=company_a),
                build_company_tax_registration(tenant_id=tenant_b, company_id=company_b),
                build_company_tax_registration(
                    tenant_id=tenant_b,
                    company_id=company_b,
                    jurisdiction_code="KA",
                    number="29BBBPB5678B1ZU",
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        counted = (
            await session.execute(select(func.count(CompanyTaxRegistration.id)))
        ).scalar_one()

    assert counted == 1


async def test_a_registration_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """No scope is a bug, never "show everything" — the one case where a default would
    return every tenant's rows."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_tax_registration(tenant_id=tenant_a, company_id=company_a))
        await session.commit()

    with pytest.raises(TenantContextError):
        await session.execute(select(CompanyTaxRegistration))


async def test_every_registration_tenant_id_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The compensating control for ``tenant_id`` carrying no foreign key
    (docs/identity-db-plan.md §1.4). The FK is omitted on purpose, so the "does the
    tenant exist" half it would have covered is a test — one per tenant-scoped table."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_tax_registration(tenant_id=tenant_a, company_id=company_a),
                build_company_tax_registration(tenant_id=tenant_b, company_id=company_b),
            ]
        )
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set(
            (await session.execute(select(CompanyTaxRegistration.tenant_id))).scalars().all()
        )

    assert owners
    assert owners <= tenants


# --- the table's own keys -----------------------------------------------------


async def test_a_registration_must_belong_to_a_real_company(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_tax_registration(tenant_id=tenant_a, company_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_the_same_system_jurisdiction_and_start_date_cannot_repeat(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """`uq_company_tax_registration_class_jurisdiction_valid_from`. It stops an
    exact duplicate and nothing more — the overlap rule is `domain/`'s, because no
    database can express "no two rows with intersecting date ranges"."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_tax_registration(tenant_id=tenant_a, company_id=company_a))
        await session.commit()

        session.add(
            build_company_tax_registration(
                tenant_id=tenant_a, company_id=company_a, number="27AAAPA1234A2ZS"
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_different_registration_classes_may_start_on_the_same_day(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Regression: the key once omitted the class, so a regular GSTIN and a
    TDS-deductor registration in one state could not share a start date although the
    overlap rule lets them coexist (revision 0063)."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_tax_registration(tenant_id=tenant_a, company_id=company_a),
                build_company_tax_registration(
                    tenant_id=tenant_a,
                    company_id=company_a,
                    regime="tds_deductor",
                    number="27MUMA12345B1D5",
                    is_primary=False,
                ),
            ]
        )
        await session.commit()

        rows = (
            await session.scalars(
                select(CompanyTaxRegistration).where(CompanyTaxRegistration.company_id == company_a)
            )
        ).all()
    assert sorted(row.registration_class for row in rows) == ["supplier", "tds_deductor"]


async def test_a_later_start_date_is_a_separate_row(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """This is how a regime change is recorded: close the old window, open a new row.
    The key has to permit it or the change could not be stored at all."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_tax_registration(
                    tenant_id=tenant_a, company_id=company_a, regime="composition"
                ),
                build_company_tax_registration(
                    tenant_id=tenant_a,
                    company_id=company_a,
                    valid_from=OCTOBER,
                    number="27AAAPA1234A2ZS",
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        counted = (
            await session.execute(select(func.count(CompanyTaxRegistration.id)))
        ).scalar_one()

    assert counted == 2


async def test_two_states_may_be_registered_on_the_same_date(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """India issues one GSTIN per state and a company may hold several at once, which
    is why ``jurisdiction_code`` is in the key."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_tax_registration(tenant_id=tenant_a, company_id=company_a),
                build_company_tax_registration(
                    tenant_id=tenant_a,
                    company_id=company_a,
                    jurisdiction_code="KA",
                    number="29AAAPA1234A1ZP",
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        counted = (
            await session.execute(select(func.count(CompanyTaxRegistration.id)))
        ).scalar_one()

    assert counted == 2


async def test_two_companies_may_hold_the_same_jurisdiction_and_date(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_tax_registration(tenant_id=tenant_a, company_id=company_a),
                build_company_tax_registration(tenant_id=tenant_b, company_id=company_b),
            ]
        )
        await session.commit()

        counted = (
            await session.execute(select(func.count(CompanyTaxRegistration.id)))
        ).scalar_one()

    assert counted == 2


def test_the_unique_key_is_named_within_mariadbs_identifier_limit() -> None:
    """MariaDB caps an identifier at 64 characters, and the convention's generated name
    would be 74. The shortening rule (docs/identity-db-plan.md §1.3) drops `company_id`
    — the table prefix already says the row is company-owned — and the `_code` suffix."""
    key = next(
        constraint
        for constraint in table_of(CompanyTaxRegistration).constraints
        if isinstance(constraint, UniqueConstraint)
    )

    assert key.name == "uq_company_tax_registration_class_jurisdiction_valid_from"
    assert len(key.name) <= 64
    assert [column.name for column in key.columns] == [
        "company_id",
        "tax_system",
        "registration_class",
        "jurisdiction_code",
        "valid_from",
    ]


def test_every_declared_name_on_the_table_fits_mariadbs_limit() -> None:
    """Asserted over the whole table rather than the one name that overflowed: the next
    index added here is very likely to be long too, and MariaDB rejects it at migration
    time with no way to shorten it afterwards."""
    table = table_of(CompanyTaxRegistration)
    names = [index.name for index in table.indexes] + [
        constraint.name for constraint in table.constraints if constraint.name
    ]

    assert "fk_company_tax_registration_registered_address_id" in {
        constraint.name for constraint in table.foreign_key_constraints
    }
    for name in names:
        assert len(str(name)) <= 64, f"{name} is {len(str(name))} characters"


def test_the_resolution_index_leads_with_company_id() -> None:
    """§1.7's two exceptions: it supports `fk_company_tax_registration_company_id`, so
    it must begin with that column or InnoDB invents a second invisible index — and
    `company_id` functionally determines `tenant_id`, so the filtered query still uses
    it."""
    index = next(
        ix
        for ix in table_of(CompanyTaxRegistration).indexes
        if ix.name == "ix_company_tax_registration_jurisdiction_validity"
    )

    assert [column.name for column in index.columns] == [
        "company_id",
        "jurisdiction_code",
        "valid_from",
        "valid_to",
    ]


def test_jurisdiction_code_carries_no_foreign_key() -> None:
    """It holds a **state** code in India and a **country** code in the UK, and no
    single target covers both. The check that replaces the FK is
    ``assert_jurisdiction_code_allowed``."""
    assert table_of(CompanyTaxRegistration).c.jurisdiction_code.foreign_keys == set()


def test_tax_system_and_regime_carry_no_foreign_key() -> None:
    """Invariant 13's shape: both are code catalogues (``billing_platform.tax``). A
    table would let a tenant invent a regime no posting path can interpret."""
    table = table_of(CompanyTaxRegistration)

    assert table.c.tax_system.foreign_keys == set()
    assert table.c.regime.foreign_keys == set()


async def test_the_registered_address_must_be_a_real_address(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_company_tax_registration(
                tenant_id=tenant_a, company_id=company_a, registered_address_id=uuid7()
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_registration_may_point_at_a_company_address(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    address = build_company_address(tenant_id=tenant_a, company_id=company_a)

    with unfiltered():
        session.add(address)
        await session.commit()
        session.add(
            build_company_tax_registration(
                tenant_id=tenant_a, company_id=company_a, registered_address_id=address.id
            )
        )
        await session.commit()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyTaxRegistration))).scalar_one()

    assert found.registered_address_id == address.id


# --- lifecycle ----------------------------------------------------------------


def test_the_table_declares_exactly_one_lifecycle_mechanism() -> None:
    """Rule 4.12, and dates are the only defensible choice here: ``regime`` decides
    whether tax may be charged at all, so it affects a computed amount and must resolve
    by ``posting_date``. With `is_active` instead, reprinting an August invoice after an
    October change would show the wrong regime on a document already filed."""
    columns = set(table_of(CompanyTaxRegistration).c.keys())

    assert {"valid_from", "valid_to"} <= columns
    assert not columns & {"status", "is_active", "deactivated_at", "deactivated_by"}


async def test_a_closed_window_survives_a_round_trip(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """``valid_to`` is a business date, never a datetime — a registration ends on a day,
    not at an instant, and a datetime would make the answer depend on a timezone."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_company_tax_registration(
                tenant_id=tenant_a, company_id=company_a, valid_to=SEPTEMBER_30
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyTaxRegistration))).scalar_one()

    assert found.valid_from == dt.date(2026, 4, 1)
    assert found.valid_to == SEPTEMBER_30
    assert isinstance(found.valid_to, dt.date)
    assert not isinstance(found.valid_to, dt.datetime)


async def test_stored_rows_feed_the_resolver_unchanged(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The seam between this table and ``billing_platform.statutory``: the rows a
    service replicates are mapped to value objects and resolved by ``posting_date``.
    Tested here because a column renamed on one side and not the other would leave both
    unit suites green."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_tax_registration(
                    tenant_id=tenant_a,
                    company_id=company_a,
                    regime="composition",
                    valid_to=SEPTEMBER_30,
                ),
                build_company_tax_registration(
                    tenant_id=tenant_a,
                    company_id=company_a,
                    valid_from=OCTOBER,
                    number="27AAAPA1234A2ZS",
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyTaxRegistration))).scalars().all()

    replicated = [
        TaxRegistration(
            tax_system=row.tax_system,
            regime=row.regime,
            number=row.number,
            jurisdiction_code=row.jurisdiction_code,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            is_primary=row.is_primary,
            legal_name_on_registration=row.legal_name_on_registration,
        )
        for row in rows
    ]

    august = resolve_tax_registration(
        replicated, jurisdiction_code="MH", posting_date=dt.date(2026, 8, 20)
    )
    november = resolve_tax_registration(
        replicated, jurisdiction_code="MH", posting_date=dt.date(2026, 11, 20)
    )

    assert august is not None
    assert august.regime == "composition"
    assert november is not None
    assert november.regime == "regular"


async def test_verification_is_recorded_as_a_reference_and_a_timestamp(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """``verified_by`` is a user id and ``verification_reference`` is a portal
    reference — never the portal response, which would put a third party's data in this
    row."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    verifier = uuid7()

    with unfiltered():
        session.add(
            build_company_tax_registration(
                tenant_id=tenant_a,
                company_id=company_a,
                verified_at=dt.datetime(2026, 4, 2, 9, 30, tzinfo=dt.UTC),
                verified_by=verifier,
                verification_reference="GSTN-SEARCH-8831",
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyTaxRegistration))).scalar_one()

    assert found.verified_at is not None
    assert found.verified_at.tzinfo is not None
    assert found.verified_by == verifier
    assert found.verification_reference == "GSTN-SEARCH-8831"

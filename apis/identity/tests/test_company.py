"""``company`` — isolation, its keys, and the jurisdiction foreign key.

The isolation block reuses the pattern ``test_tenant.py`` established, written out
rather than called: an isolation test that reads as a call to something else is one
nobody checks. This table gets the simpler ``tenant_id`` form.

The composite foreign key has its own block. It is the reason revision 0006 carries
a unique key on ``(country_code, code)`` that looks redundant against its primary
key, and if these tests were missing that constraint would eventually be
"simplified" away — taking with it the only thing making ``IN`` + ``US-CA``
unrepresentable rather than merely unlikely.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from billing_platform.constants import MONEY_SCALE
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.db.types import Money
from billing_platform.ids import uuid7
from billing_platform.testing import table_of
from sqlalchemy import String, func, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import (
    BUSINESS_NATURES,
    COMPANY_STATUSES,
    ENTITY_TYPES,
    PRECISION_MAX,
    PRECISION_MIN,
    ROUNDING_MODES,
    TAX_TREATMENTS,
    VISIBILITIES,
    Company,
    Tenant,
)
from tests.factories import (
    build_company,
    build_country,
    build_state,
    seed_two_companies,
    seed_two_tenants,
)

# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_company(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(Company))).scalars().all()

    assert [row.display_name for row in rows] == ["Alpha Ltd"]


async def test_the_other_tenants_company_is_absent(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(Company))).scalars().all()

    assert all(row.tenant_id == tenant_a for row in rows)
    assert "Beta Ltd" not in {row.display_name for row in rows}


async def test_knowing_the_other_companys_id_is_not_enough(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """§5.2. A company id travels in URLs, so the filter is what protects the row —
    not the difficulty of guessing it."""
    _, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(Company).where(Company.id == company_b))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(Company.id)))).scalar_one()

    assert found is None
    assert counted == 1, "an aggregate must see one company too, not every company"


async def test_a_company_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)

    with pytest.raises(TenantContextError):
        await session.execute(select(Company))


async def test_every_company_tenant_id_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The compensating control for ``tenant_id`` carrying no foreign key
    (docs/identity-db-plan.md §1.4). An FK proves the tenant exists; it does nothing
    about querying the wrong one, which is what the filter is for — so this test
    covers the half the FK would have."""
    await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(Company.tenant_id))).scalars().all())

    assert owners <= tenants


# --- the jurisdiction foreign key ---------------------------------------------


async def test_a_company_in_an_impossible_state_is_rejected(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """`fk_company_country_code_state_code`. `IN` with a Californian state code is
    refused by the database, not by a form — and `state_code` decides whether every
    issued invoice is intra-state or inter-state GST."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, state_code="US-CA"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_company_in_a_known_state_is_accepted(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The other half of the pair: the constraint must not reject a valid one."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, country_code="IN", state_code="MH"))
        await session.commit()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(Company))).scalar_one()

    assert (found.country_code, found.state_code) == ("IN", "MH")


async def test_the_state_code_alone_is_not_enough(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A state code valid in one country is invalid in another. This is exactly the
    case a single-column FK to ``state.code`` would have let through."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(
            build_country(
                code="GB",
                iso3="GBR",
                numeric_code="826",
                name="United Kingdom",
                official_name="United Kingdom of Great Britain and Northern Ireland",
                phone_prefix="+44",
            )
        )
        await session.flush()
        session.add(
            build_state(code="ENG", country_code="GB", name="England", tax_jurisdiction_code=None)
        )
        await session.flush()
        # `MH` exists, and `GB` exists, but not together.
        session.add(build_company(tenant_id=tenant_a, country_code="GB", state_code="MH"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_company_with_an_unknown_base_currency_is_rejected(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, base_currency="ZZZ"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_reporting_currency_may_be_null(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """NULL means "same as base". A second copy of the base currency would be a value
    to keep in sync for no benefit."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, reporting_currency=None))
        await session.commit()

    with tenant_scope(tenant_a):
        assert (await session.execute(select(Company))).scalar_one().reporting_currency is None


# --- the table's own keys -----------------------------------------------------


async def test_two_companies_in_one_tenant_cannot_share_a_code(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """`uq_company_tenant_id_code`. The code is embedded in document numbers, so a
    duplicate would produce two documents numbered identically."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, code="MAIN"))
        await session.commit()

        session.add(build_company(tenant_id=tenant_a, code="MAIN", display_name="Second"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_two_tenants_may_both_use_the_same_code(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The unique key is scoped to the tenant, and it has to be: "MAIN" is the
    obvious first code every tenant will choose."""
    await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        codes = (await session.execute(select(Company.code))).scalars().all()

    assert codes == ["MAIN", "MAIN"]


async def test_a_parent_company_must_exist(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """`fk_company_parent_company_id`, self-referencing."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, parent_company_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_parent_in_another_tenant_is_not_stopped_by_the_database(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**Documents a gap the schema cannot close.**

    The foreign key proves the parent row exists; it cannot prove it belongs to the
    same tenant, and a cross-tenant parent would be a §5.2 object-scope breach that
    no `WHERE` clause would catch. This test exists so the `domain/` check that does
    close it is never mistaken for redundant — asserting the database's *silence*,
    not its approval.
    """
    _, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, code="CHILD", parent_company_id=company_b))
        await session.commit()

    with tenant_scope(tenant_a):
        child = (await session.execute(select(Company).where(Company.code == "CHILD"))).scalar_one()
        reachable = (
            await session.execute(select(Company).where(Company.id == company_b))
        ).scalar_one_or_none()

    assert (
        child.parent_company_id == company_b
    ), "the database accepts a cross-tenant parent; domain/ must reject it on write"
    assert reachable is None, "and the session filter still hides the parent row itself"


async def test_print_template_id_needs_no_table(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """Templates live outside `identity`. A cross-service foreign key is what the
    architecture forbids, so the absence is a decision, not an oversight."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, print_template_id=uuid7()))
        await session.commit()

    assert table_of(Company).c.print_template_id.foreign_keys == set()


# --- money and precision ------------------------------------------------------


async def test_a_money_column_returns_a_decimal(session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """Invariant 1, asserted on the **type**. Driver float coercion for DECIMAL is
    silent, and a float cash-receipt ceiling would compare wrongly at the boundary —
    which is the only place it is ever compared."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(
            build_company(
                tenant_id=tenant_a,
                cash_receipt_limit=Decimal("200000.0000"),
                credit_limit_default=Decimal("50000.5000"),
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(Company))).scalar_one()

    assert isinstance(found.cash_receipt_limit, Decimal)
    assert isinstance(found.credit_limit_default, Decimal)
    assert found.credit_limit_default == Decimal("50000.5000")


async def test_a_float_amount_is_refused_at_the_boundary(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """`Money` rejects it on bind rather than storing a rounded value. A float that
    made it in would be undetectable afterwards — which is why the refusal happens at
    the column, not in a validator someone can forget to call."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered(), pytest.raises(StatementError) as raised:
        session.add(build_company(tenant_id=tenant_a, cash_receipt_limit=200000.0))
        await session.flush()
    await session.rollback()

    assert isinstance(raised.value.orig, TypeError), "SQLAlchemy wraps the bind refusal"
    assert "use Decimal" in str(raised.value.orig)


def test_the_precision_columns_are_display_scales_not_storage_scales() -> None:
    """docs/company.md §4.5. Storage is DECIMAL(19,4) whatever these say; reading
    them as storage scales is how a subledger stops tying."""
    assert (PRECISION_MIN, PRECISION_MAX) == (0, MONEY_SCALE), (
        "the display ceiling is the storage scale: a company may not ask to show more "
        "decimals than are kept"
    )
    for name in ("credit_limit_default", "cash_receipt_limit"):
        # That `Money` pins DECIMAL(19,4) and guarantees a `Decimal` back is
        # `libs/platform`'s test. What is asserted here is that these two columns use
        # it, rather than a `Numeric` narrowed to `amount_precision`.
        assert isinstance(table_of(Company).c[name].type, Money)


# --- lifecycle and catalogues -------------------------------------------------


def test_the_table_declares_exactly_one_lifecycle_mechanism() -> None:
    """Rule 4.12. `status` here, so no `is_active` and no validity dates."""
    columns = set(table_of(Company).c.keys())

    assert "status" in columns
    assert not columns & {"is_active", "deactivated_at", "valid_from", "valid_to"}


def test_first_posted_at_is_nullable_and_is_a_timestamp() -> None:
    """The gate for every immutable field. Nullable because the pre-posting window is
    exactly when those fields are meant to be editable."""
    column = table_of(Company).c.first_posted_at

    assert column.nullable
    assert column.name.endswith("_at")


def test_the_documented_catalogues_are_the_ones_the_code_knows() -> None:
    assert COMPANY_STATUSES == {"active", "suspended", "closed"}
    assert ENTITY_TYPES == {
        "pvt_ltd",
        "llp",
        "partnership",
        "sole_prop",
        "public",
        "trust",
        "branch",
    }
    assert BUSINESS_NATURES == {
        "trading",
        "manufacturing",
        "service",
        "distribution",
        "retail",
    }
    assert ROUNDING_MODES == {"half_up", "half_even", "down"}
    assert TAX_TREATMENTS == {"inclusive", "exclusive"}
    assert VISIBILITIES == {"listed", "unlisted"}


async def test_a_suspended_company_keeps_its_row(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """`suspended` blocks new documents and leaves history fully readable
    (docs/company.md §5.4). It is never a delete — invariant 12."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, status="suspended"))
        await session.commit()

    with tenant_scope(tenant_a):
        assert (await session.execute(select(Company))).scalar_one().status == "suspended"


async def test_an_unlisted_company_is_still_returned_to_an_authorized_reader(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Invariant 17: `visibility` is a **display preference, not access control**. It
    must not filter anything out at the data layer, or audit rows and tenant-wide
    reports would quietly lose companies."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, visibility="unlisted"))
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(Company))).scalars().all()

    assert [row.visibility for row in rows] == ["unlisted"]


async def test_custom_fields_round_trip_as_a_mapping(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Stored, and that is all. **No domain logic reads this** (invariant 14) — never
    priced, taxed, posted, or used to route an approval."""
    await seed_two_tenants(session, tenant_a, uuid7())

    with unfiltered():
        session.add(build_company(tenant_id=tenant_a, custom_fields={"legacy_ref": "AC-1"}))
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(Company))).scalar_one()

    assert found.custom_fields == {"legacy_ref": "AC-1"}


def test_the_dsc_column_holds_a_thumbprint_not_a_key() -> None:
    """§5.9. 64 characters is a SHA-256 hex fingerprint; a certificate or a PFX blob
    would need orders of magnitude more, so the width itself is the guard."""
    column_type = table_of(Company).c.dsc_thumbprint.type
    assert isinstance(column_type, String)
    assert column_type.length == 64

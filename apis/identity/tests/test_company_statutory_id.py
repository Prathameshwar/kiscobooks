"""``company_statutory_id`` — isolation, the last-four key, and the AADHAAR rule at rest.

The load-bearing test in this file is
`test_a_restricted_identifier_is_stored_without_its_full_value`: it reads the persisted
column back and asserts the full number is not there. Every other layer — the profile,
the domain gate, the API — exists to keep that true, and this is the only place it is
checked against an actual row (CLAUDE.md §5.10).

Two other things are settled here. ``value_last4`` is NOT NULL for *every* kind, a
deliberate departure from docs/identity-schema.md §3.7, because MariaDB treats NULLs
inside a unique key as distinct (docs/identity-db-plan.md §2). And the table carries
both `is_active` and ``valid_to`` without breaking rule 4.12 — one is the lifecycle,
the other is a date printed on a certificate.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.jurisdiction import prepare_statutory_value
from billing_platform.testing import table_of
from sqlalchemy import UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import CompanyStatutoryId, Tenant
from tests.factories import build_company_statutory_id, seed_two_companies

#: A syntactically valid twelve-digit number that is not a real AADHAAR and is not a
#: secret (CLAUDE.md §5.9). The point of using a full-length one is that the test can
#: then assert it is absent from the row.
FAKE_AADHAAR = "123456789012"

# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_statutory_ids(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_statutory_id(
                    tenant_id=tenant_a, company_id=company_a, value="AAAPA1234A"
                ),
                build_company_statutory_id(
                    tenant_id=tenant_b, company_id=company_b, value="BBBPB5678B"
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyStatutoryId))).scalars().all()

    assert [row.value for row in rows] == ["AAAPA1234A"]
    assert "BBBPB5678B" not in {row.value for row in rows}


async def test_the_other_tenants_statutory_id_is_not_reachable_by_id(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The worst row on the platform to leak: a PAN identifies the taxpayer, and for a
    proprietorship it identifies a person."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    theirs = build_company_statutory_id(tenant_id=tenant_b, company_id=company_b)

    with unfiltered():
        session.add_all(
            [theirs, build_company_statutory_id(tenant_id=tenant_a, company_id=company_a)]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(
                select(CompanyStatutoryId).where(CompanyStatutoryId.id == theirs.id)
            )
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(CompanyStatutoryId.id)))).scalar_one()

    assert found is None
    assert counted == 1


async def test_a_statutory_id_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_statutory_id(tenant_id=tenant_a, company_id=company_a))
        await session.commit()

    with pytest.raises(TenantContextError):
        await session.execute(select(CompanyStatutoryId))


async def test_every_statutory_id_tenant_id_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The compensating control for ``tenant_id`` carrying no foreign key
    (docs/identity-db-plan.md §1.4)."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_statutory_id(tenant_id=tenant_a, company_id=company_a),
                build_company_statutory_id(tenant_id=tenant_b, company_id=company_b),
            ]
        )
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(CompanyStatutoryId.tenant_id))).scalars().all())

    assert owners
    assert owners <= tenants


async def test_a_statutory_id_must_belong_to_a_real_company(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_statutory_id(tenant_id=tenant_a, company_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# --- the AADHAAR rule, at rest ------------------------------------------------


async def test_a_restricted_identifier_is_stored_without_its_full_value(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**CLAUDE.md §5.10 against a real row.** The API accepts a full number,
    ``prepare_statutory_value`` derives the last four, and what lands in the table is
    four digits and a verification reference. ``value`` being NULL is not a degraded
    case — it is the whole design of this table."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    stored = prepare_statutory_value("IN", "aadhaar", FAKE_AADHAAR)

    with unfiltered():
        session.add(
            build_company_statutory_id(
                tenant_id=tenant_a,
                company_id=company_a,
                kind="aadhaar",
                value=stored.value,
                value_last4=stored.value_last4,
                verification_reference="UIDAI-OTP-4471",
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyStatutoryId))).scalar_one()

    assert found.value is None
    assert found.value_last4 == "9012"
    assert found.verification_reference == "UIDAI-OTP-4471"


async def test_the_full_restricted_number_is_absent_from_every_column(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Asserted across the whole row rather than the one column it belongs in, so a
    later column — a note field, a holder name — cannot become the place it hides."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    stored = prepare_statutory_value("IN", "aadhaar", FAKE_AADHAAR)

    with unfiltered():
        session.add(
            build_company_statutory_id(
                tenant_id=tenant_a,
                company_id=company_a,
                kind="aadhaar",
                value=stored.value,
                value_last4=stored.value_last4,
                holder_name="Anita Rao",
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyStatutoryId))).scalar_one()

    text_columns = [
        value
        for value in (
            found.kind,
            found.value,
            found.value_last4,
            found.holder_name,
            found.verification_reference,
        )
        if value is not None
    ]

    assert all(FAKE_AADHAAR not in value for value in text_columns)


async def test_a_business_identifier_is_stored_in_full(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """PAN, TAN, CIN, EIN and GSTIN are business identifiers, print on invoices, and are
    kept whole. The rule is about *personal* identity numbers, not about statutory
    identifiers generally (CLAUDE.md §5.10)."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    stored = prepare_statutory_value("IN", "pan", "aaapa1234a")

    with unfiltered():
        session.add(
            build_company_statutory_id(
                tenant_id=tenant_a,
                company_id=company_a,
                value=stored.value,
                value_last4=stored.value_last4,
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyStatutoryId))).scalar_one()

    assert found.value == "AAAPA1234A"
    assert found.value_last4 == "234A"


# --- the table's own keys -----------------------------------------------------


def test_value_is_nullable_and_last4_is_not() -> None:
    """The deliberate departure from docs/identity-schema.md §3.7, which says
    ``value_last4`` is nullable. It is the last column of the unique key, and MariaDB
    treats NULLs inside a unique key as distinct (docs/identity-db-plan.md §2) — left
    NULL for unrestricted kinds, a company could store the same PAN twice and the
    constraint would enforce nothing at all for exactly the kinds that matter most."""
    table = table_of(CompanyStatutoryId)

    assert table.c.value.nullable is True
    assert table.c.value_last4.nullable is False


async def test_one_company_cannot_hold_the_same_identifier_twice(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """`uq_company_statutory_id_company_id_kind_value_last4`. Two PAN rows for one
    company means the answer to "what is their PAN" depends on which row is read
    first — and one of them could be the deactivated one."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_statutory_id(tenant_id=tenant_a, company_id=company_a))
        await session.commit()

        session.add(build_company_statutory_id(tenant_id=tenant_a, company_id=company_a))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_the_key_catches_a_duplicate_restricted_identifier_too(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The reason the key is on ``value_last4`` rather than ``value``: for a restricted
    kind ``value`` is NULL, so keying on it would let the same AADHAAR be added
    repeatedly with no way to notice."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    stored = prepare_statutory_value("IN", "aadhaar", FAKE_AADHAAR)

    with unfiltered():
        for _ in range(2):
            session.add(
                build_company_statutory_id(
                    tenant_id=tenant_a,
                    company_id=company_a,
                    kind="aadhaar",
                    value=stored.value,
                    value_last4=stored.value_last4,
                )
            )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_two_kinds_may_share_their_last_four_characters(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """``kind`` is in the key, so a PAN and a TAN ending the same way both insert. The
    known cost is narrower: two *different* values of **one** kind sharing their last
    four are falsely rejected, which is inherent in the documented key."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_statutory_id(
                    tenant_id=tenant_a, company_id=company_a, kind="pan", value="AAAPA1234A"
                ),
                build_company_statutory_id(
                    tenant_id=tenant_a, company_id=company_a, kind="tan", value="MUMA1234A"
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        counted = (await session.execute(select(func.count(CompanyStatutoryId.id)))).scalar_one()

    assert counted == 2


async def test_two_companies_may_each_hold_a_pan(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_statutory_id(tenant_id=tenant_a, company_id=company_a),
                build_company_statutory_id(tenant_id=tenant_b, company_id=company_b),
            ]
        )
        await session.commit()

        counted = (await session.execute(select(func.count(CompanyStatutoryId.id)))).scalar_one()

    assert counted == 2


def test_the_unique_key_omits_tenant_id_and_names_its_columns() -> None:
    """`company_id` already determines the tenant, so prefixing `tenant_id` would
    *weaken* the constraint: the same identifier could then insert twice under a
    mismatched `tenant_id`."""
    key = next(
        constraint
        for constraint in table_of(CompanyStatutoryId).constraints
        if isinstance(constraint, UniqueConstraint)
    )

    assert key.name == "uq_company_statutory_id_company_id_kind_value_last4"
    assert [column.name for column in key.columns] == ["company_id", "kind", "value_last4"]


def test_kind_carries_no_foreign_key() -> None:
    """Invariant 13's shape, the same argument as ``company_feature.feature_key``: kinds
    are code, so a `kind` table would let a tenant invent one no service knows how to
    validate, print, or treat as restricted."""
    assert table_of(CompanyStatutoryId).c.kind.foreign_keys == set()


def test_the_lookup_index_leads_with_company_id() -> None:
    """§1.7's two exceptions: it supports `fk_company_statutory_id_company_id`, and
    `company_id` functionally determines `tenant_id`."""
    index = next(
        ix
        for ix in table_of(CompanyStatutoryId).indexes
        if ix.name == "ix_company_statutory_id_company_id_kind"
    )

    assert [column.name for column in index.columns] == ["company_id", "kind"]


# --- one lifecycle, two date-shaped columns -----------------------------------


def test_is_active_is_the_lifecycle_and_valid_to_is_data() -> None:
    """**Rule 4.12, at its most easily misread.** The table has `is_active` *and*
    ``valid_to``, which looks like two mechanisms. It is not: an identifier does not
    affect a computed amount — it prints — so the boolean is the right mechanism, and
    ``valid_to`` is the expiry printed on the certificate. The proof is the absence of
    ``valid_from``: with no start date there is no window, so ``valid_to`` cannot be
    read as the date-validity form."""
    columns = set(table_of(CompanyStatutoryId).c.keys())

    assert "is_active" in columns
    assert "valid_to" in columns
    assert "valid_from" not in columns
    assert "status" not in columns


async def test_a_superseded_identifier_is_deactivated_rather_than_deleted(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Invariant 12: an invoice already printed with a PAN must still be able to explain
    where that number came from."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)
    deactivator = uuid7()

    with unfiltered():
        session.add(
            build_company_statutory_id(
                tenant_id=tenant_a,
                company_id=company_a,
                is_active=False,
                deactivated_at=dt.datetime(2026, 6, 1, 10, 0, tzinfo=dt.UTC),
                deactivated_by=deactivator,
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyStatutoryId))).scalar_one()

    assert found.is_active is False
    assert found.deactivated_at is not None
    assert found.deactivated_at.tzinfo is not None
    assert found.deactivated_by == deactivator
    assert found.value == "AAAPA1234A", "the value is kept; the row is only deactivated"


async def test_a_certificate_expiry_is_a_business_date(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A certificate expires on a day, not at an instant, so a datetime here would make
    the answer depend on a timezone (CLAUDE.md §4)."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_company_statutory_id(
                tenant_id=tenant_a,
                company_id=company_a,
                issued_on=dt.date(2026, 4, 1),
                valid_to=dt.date(2031, 3, 31),
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyStatutoryId))).scalar_one()

    assert found.issued_on == dt.date(2026, 4, 1)
    assert found.valid_to == dt.date(2031, 3, 31)
    assert not isinstance(found.valid_to, dt.datetime)

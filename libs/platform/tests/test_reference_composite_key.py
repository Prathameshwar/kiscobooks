"""``uq_state_country_code_code``: the key that makes a bad place of supply impossible.

`state.code` is already the primary key, so a unique key on `(country_code, code)`
adds no uniqueness and reads as duplication. It is not. It is the *target* of the
composite foreign key that `company` and `company_address` declare on
`(country_code, state_code)` in phase 3, and a foreign key needs a unique index over
exactly its referenced columns.

What that buys: `country_code='IN'` with `state_code='US-CA'` becomes
unrepresentable rather than merely unlikely (``docs/identity-schema.md`` §1.2). A
mismatched pair sets the tax jurisdiction for the whole document, so validation alone
is not enough — every write path would have to remember, and one that forgets is a
silently mis-taxed invoice.

``PlaceLike`` in ``tests/models.py`` stands in for those phase-3 tables so the key is
proven to carry a composite foreign key *now*, before anything depends on it. Without
it the key would look removable to the next person who reads the schema.
"""

from __future__ import annotations

import pytest
from sqlalchemy import UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from billing_platform.db.reference_models import Country, Currency, State
from billing_platform.ids import uuid7
from tests.helpers import table_of
from tests.models import PlaceLike


async def _two_jurisdictions(session: AsyncSession) -> None:
    """The smallest fixture that can express the mismatch: two countries, one state
    each. Written directly rather than by seeding, so the test states its own data."""
    session.add_all(
        [
            Currency(
                code="INR",
                numeric_code="356",
                name="Indian Rupee",
                symbol="₹",
                minor_unit=2,
                major_unit_name="Rupees",
                minor_unit_name="Paisa",
                minor_unit_name_plural="Paise",
                is_active=True,
            ),
            Currency(
                code="USD",
                numeric_code="840",
                name="US Dollar",
                symbol="$",
                minor_unit=2,
                major_unit_name="Dollars",
                minor_unit_name="Cent",
                minor_unit_name_plural="Cents",
                is_active=True,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            Country(
                code="IN",
                iso3="IND",
                numeric_code="356",
                name="India",
                official_name="Republic of India",
                default_currency_code="INR",
                phone_prefix="+91",
                subdivision_label="State",
                is_active=True,
            ),
            Country(
                code="US",
                iso3="USA",
                numeric_code="840",
                name="United States",
                official_name="United States of America",
                default_currency_code="USD",
                phone_prefix="+1",
                subdivision_label="State",
                is_active=True,
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            State(
                code="IN-MH",
                country_code="IN",
                name="Maharashtra",
                subdivision_type="State",
                tax_jurisdiction_code="27",
                is_active=True,
            ),
            State(
                code="US-CA",
                country_code="US",
                name="California",
                subdivision_type="State",
                tax_jurisdiction_code=None,
                is_active=True,
            ),
        ]
    )
    await session.commit()


def test_the_unique_key_covers_exactly_the_composite_foreign_key_columns() -> None:
    """Order matters as well as membership: a foreign key needs an index whose
    leading columns are exactly the referenced ones."""
    unique = [c for c in table_of(State).constraints if isinstance(c, UniqueConstraint)]

    assert len(unique) == 1
    assert unique[0].name == "uq_state_country_code_code"
    assert [column.name for column in unique[0].columns] == ["country_code", "code"]


def test_the_unique_key_also_serves_the_country_foreign_key() -> None:
    """``country_code`` leads it, so InnoDB uses this index for
    ``fk_state_country_code`` and creates no second index on the same prefix — which
    would otherwise appear as autogenerate drift on every later revision."""
    unique = next(c for c in table_of(State).constraints if isinstance(c, UniqueConstraint))

    assert next(column.name for column in unique.columns) == "country_code"


async def test_a_matching_country_and_state_pair_is_accepted(session: AsyncSession) -> None:
    await _two_jurisdictions(session)

    session.add(PlaceLike(id=uuid7(), country_code="IN", state_code="IN-MH"))
    await session.commit()

    stored = (await session.execute(select(PlaceLike))).scalars().all()
    assert [(row.country_code, row.state_code) for row in stored] == [("IN", "IN-MH")]


async def test_a_mismatched_country_and_state_pair_is_rejected_by_the_database(
    session: AsyncSession,
) -> None:
    """The phase 1 exit criterion. Rejected by the *database*, not by validation:
    both codes exist and both are individually valid, so nothing short of the
    composite key catches the pair."""
    await _two_jurisdictions(session)

    session.add(PlaceLike(id=uuid7(), country_code="IN", state_code="US-CA"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    assert (await session.execute(select(PlaceLike))).scalars().all() == []


async def test_a_state_in_an_unknown_country_is_rejected(session: AsyncSession) -> None:
    """``fk_state_country_code``. Without it, seeding in the wrong order would leave
    orphan subdivisions that no country dropdown ever shows."""
    await _two_jurisdictions(session)

    session.add(
        State(
            code="ZZ-01",
            country_code="ZZ",
            name="Nowhere",
            subdivision_type="State",
            tax_jurisdiction_code=None,
            is_active=True,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_a_country_with_an_unknown_currency_is_rejected(session: AsyncSession) -> None:
    """``fk_country_default_currency_code``. A country pre-selects this currency on
    company creation, and the company's base currency is immutable once anything is
    posted (invariant 16) — so a dangling code here is expensive later."""
    await _two_jurisdictions(session)

    session.add(
        Country(
            code="ZZ",
            iso3="ZZZ",
            numeric_code="999",
            name="Nowhere",
            official_name="Nowhere",
            default_currency_code="ZZZ",
            phone_prefix="+0",
            subdivision_label="Region",
            is_active=True,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

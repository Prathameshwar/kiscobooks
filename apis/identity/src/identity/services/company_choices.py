"""Public reference projections behind the company-setup permission boundary."""

from __future__ import annotations

from dataclasses import asdict
from typing import TypeVar

from billing_platform.errors import ConflictError
from billing_platform.jurisdiction import JURISDICTION_PROFILES
from billing_platform.tax import REGIMES
from pydantic import TypeAdapter
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.company_defaults import setup_defaults
from identity.models import Country, Currency, State
from identity.schemas.reference import (
    CountryChoice,
    CountrySetupDefaults,
    CurrencyChoice,
    StateChoice,
    TaxRegimeChoice,
    TaxRegistrationChoice,
)
from identity.schemas.reference_management import ReferenceOption, ReferenceOptions
from identity.services.reference_availability import selectable
from identity.services.reference_cache import ReferenceChoiceCache

R = TypeVar("R")
MAX_CHOICES = 1000


async def bounded(db: AsyncSession, statement: Select[tuple[R]]) -> list[R]:
    rows = list(await db.scalars(statement.limit(MAX_CHOICES + 1)))
    if len(rows) > MAX_CHOICES:
        raise ConflictError("reference catalogue exceeds the supported choice limit")
    return rows


async def countries(
    db: AsyncSession, cache: ReferenceChoiceCache | None = None
) -> list[CountryChoice]:
    if cache is not None:
        return await cache.resolve(
            db, "countries", TypeAdapter(list[CountryChoice]), lambda: countries(db)
        )
    rows = await bounded(
        db,
        select(Country)
        .where(Country.is_active.is_(True), selectable("country", Country.code))
        .order_by(Country.code),
    )
    return [
        CountryChoice(
            code=row.code,
            name=row.name,
            default_currency_code=row.default_currency_code,
            subdivision_label=row.subdivision_label,
            jurisdiction_supported=row.code in JURISDICTION_PROFILES,
            tax_systems=sorted(JURISDICTION_PROFILES[row.code].tax_systems_by_key())
            if row.code in JURISDICTION_PROFILES
            else [],
            tax_registration_options=[
                TaxRegistrationChoice(
                    tax_system=system,
                    jurisdiction_scope=JURISDICTION_PROFILES[row.code].tax_registration_is_per,
                    number_label="GSTIN"
                    if system == "gst_in"
                    else (
                        "VAT registration number"
                        if system.startswith("vat_")
                        else "Tax registration number"
                    ),
                    regimes=[
                        TaxRegimeChoice(value=key, label=value.label)
                        for key, value in REGIMES.get(system, {}).items()
                        if key not in {"unregistered", "not_registered"}
                    ],
                )
                for system in JURISDICTION_PROFILES[row.code].tax_systems_by_key()
                if REGIMES.get(system)
            ]
            if row.code in JURISDICTION_PROFILES
            else [],
            # Dependency order as the profile states it, not sorted: a form enabling
            # them in order never asks for a dependent before the feature it needs.
            default_features=list(
                JURISDICTION_PROFILES[row.code].default_features
                if row.code in JURISDICTION_PROFILES
                else ()
            ),
            # Suggestions for the setup form, from one table every client shares. A
            # country with no profile still gets the neutral set to review.
            setup_defaults=CountrySetupDefaults.model_validate(asdict(setup_defaults(row.code))),
        )
        for row in rows
    ]


async def states(
    db: AsyncSession, country_code: str, cache: ReferenceChoiceCache | None = None
) -> list[StateChoice]:
    if cache is not None:
        return await cache.resolve(
            db,
            "states:" + country_code,
            TypeAdapter(list[StateChoice]),
            lambda: states(db, country_code),
        )
    rows = await bounded(
        db,
        select(State)
        .where(
            State.country_code == country_code,
            State.is_active.is_(True),
            selectable("state", State.code),
        )
        .order_by(State.code),
    )
    return [StateChoice.model_validate(row) for row in rows]


async def currencies(
    db: AsyncSession, cache: ReferenceChoiceCache | None = None
) -> list[CurrencyChoice]:
    if cache is not None:
        return await cache.resolve(
            db, "currencies", TypeAdapter(list[CurrencyChoice]), lambda: currencies(db)
        )
    rows = await bounded(
        db,
        select(Currency)
        .where(Currency.is_active.is_(True), selectable("currency", Currency.code))
        .order_by(Currency.code),
    )
    return [CurrencyChoice.model_validate(row) for row in rows]


async def options(db: AsyncSession, cache: ReferenceChoiceCache | None = None) -> ReferenceOptions:
    if cache is not None:
        return await cache.resolve(
            db, "options", TypeAdapter(ReferenceOptions), lambda: options(db)
        )
    countries = await bounded(
        db,
        select(Country)
        .where(Country.is_active.is_(True), selectable("country", Country.code))
        .order_by(Country.name, Country.code),
    )
    currencies = await bounded(
        db,
        select(Currency)
        .where(Currency.is_active.is_(True), selectable("currency", Currency.code))
        .order_by(Currency.name, Currency.code),
    )
    return ReferenceOptions(
        countries=[ReferenceOption.model_validate(row) for row in countries],
        currencies=[ReferenceOption.model_validate(row) for row in currencies],
    )

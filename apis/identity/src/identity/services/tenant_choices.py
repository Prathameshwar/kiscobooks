"""Bounded global choices shared by authenticated tenant setup screens."""

from __future__ import annotations

from typing import TYPE_CHECKING

from billing_platform.errors import ConflictError
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Country, Currency, Language, State, Timezone
from identity.schemas.base import StrictModel
from identity.services.reference_availability import selectable

if TYPE_CHECKING:
    from identity.services.reference_cache import ReferenceChoiceCache


class TenantChoice(StrictModel):
    code: str
    name: str


class StateChoice(TenantChoice):
    country_code: str


class RegistrationChoices(StrictModel):
    countries: list[TenantChoice]
    states: list[StateChoice]


class TenantChoices(RegistrationChoices):
    currencies: list[TenantChoice]
    languages: list[TenantChoice]
    timezones: list[TenantChoice]


async def registration_choices(
    db: AsyncSession, cache: ReferenceChoiceCache | None = None
) -> RegistrationChoices:
    if cache is not None:
        return await cache.resolve(
            db, "registration", TypeAdapter(RegistrationChoices), lambda: registration_choices(db)
        )
    countries = list(
        await db.scalars(
            select(Country)
            .where(Country.is_active.is_(True), selectable("country", Country.code))
            .order_by(Country.name, Country.code)
            .limit(1001)
        )
    )
    if len(countries) > 1000:
        raise ConflictError("country reference catalogue exceeds the supported limit")
    states = list(
        await db.scalars(
            select(State)
            .join(Country, Country.code == State.country_code)
            .where(
                State.is_active.is_(True),
                Country.is_active.is_(True),
                selectable("state", State.code),
                selectable("country", Country.code),
            )
            .order_by(State.country_code, State.name, State.code)
            .limit(10001)
        )
    )
    if len(states) > 10000:
        raise ConflictError("state reference catalogue exceeds the supported limit")
    return RegistrationChoices(
        countries=[TenantChoice.model_validate(row) for row in countries],
        states=[StateChoice.model_validate(row) for row in states],
    )


async def choices(db: AsyncSession, cache: ReferenceChoiceCache | None = None) -> TenantChoices:
    if cache is not None:
        return await cache.resolve(db, "tenant", TypeAdapter(TenantChoices), lambda: choices(db))
    regions = await registration_choices(db)
    currencies = list(
        await db.scalars(
            select(Currency)
            .where(Currency.is_active.is_(True), selectable("currency", Currency.code))
            .order_by(Currency.code)
            .limit(1001)
        )
    )
    languages = list(
        await db.scalars(
            select(Language)
            .where(Language.is_active.is_(True), selectable("language", Language.code))
            .order_by(Language.name, Language.code)
            .limit(1001)
        )
    )
    timezones = list(
        await db.scalars(
            select(Timezone).where(Timezone.is_active.is_(True)).order_by(Timezone.code).limit(1001)
        )
    )
    if any(len(rows) > 1000 for rows in (currencies, languages, timezones)):
        raise ConflictError("tenant reference catalogue exceeds the supported limit")
    return TenantChoices(
        **regions.model_dump(),
        currencies=[TenantChoice.model_validate(row) for row in currencies],
        languages=[TenantChoice.model_validate(row) for row in languages],
        timezones=[TenantChoice.model_validate(row) for row in timezones],
    )

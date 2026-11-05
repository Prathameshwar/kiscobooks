"""Bounded read-only ISO choices for company setup. No reference-data CRUD.

Each list has a hard maximum of 1,000 entries, ordered by natural code. States
are always restricted to one country. These seeded lists contain no tenant data.
"""

from __future__ import annotations

from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.jurisdiction import profile
from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.dependencies import session
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import Country, Timezone
from identity.schemas.reference import (
    CountryChoice,
    CurrencyChoice,
    LicenceTypeChoice,
    StateChoice,
    TimezoneChoice,
)
from identity.services import company_choices
from identity.services.reference_availability import require_delivered

router = APIRouter(
    responses=ERROR_RESPONSES,
    route_class=StrictRoute,
    prefix="/v1/reference",
    tags=["Company setup references"],
)
_READ_PERMISSIONS = frozenset(
    {
        "company.create",
        "company.read",
        "company.update",
        "company.licence.manage",
        "warehouse.read",
        "warehouse.manage",
    }
)


def _authorize(current: Actor) -> None:
    # Any valid company scope may read global choices, but expired/future grants
    # must not satisfy even this read-only endpoint gate.
    today = utcnow().date()
    if not any(
        g.is_active
        and g.permissions & _READ_PERMISSIONS
        and g.valid_from <= today
        and (g.valid_to is None or today <= g.valid_to)
        for g in current.grants
    ):
        raise PermissionDeniedError("company setup access is required")


async def _country(db: AsyncSession, code: str) -> Country:
    await require_delivered(db, "country", code)
    country = await db.get(Country, code)
    if country is None or not country.is_active:
        raise ValidationFailedError(
            "invalid country", fields={"country_code": "unknown or inactive country"}
        )
    return country


@router.get("/countries", response_model=list[CountryChoice])
async def countries(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> list[CountryChoice]:
    """Active ISO countries; jurisdiction_supported identifies company setup support."""
    _authorize(current)
    return await company_choices.countries(db, request.app.state.reference_cache)


@router.get("/timezones", response_model=list[TimezoneChoice])
async def timezones(
    current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> list[TimezoneChoice]:
    """Bounded active IANA choices for company and warehouse forms."""
    from sqlalchemy import select

    _authorize(current)
    rows = await db.scalars(
        select(Timezone).where(Timezone.is_active.is_(True)).order_by(Timezone.code).limit(1000)
    )
    return [TimezoneChoice.model_validate(row) for row in rows]


@router.get("/countries/{country_code}/states", response_model=list[StateChoice])
async def states(
    request: Request,
    country_code: str = Path(pattern=r"^[A-Z]{2}$"),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> list[StateChoice]:
    """Active subdivisions of one active country, ordered by code."""
    _authorize(current)
    await _country(db, country_code)
    return await company_choices.states(db, country_code, request.app.state.reference_cache)


@router.get("/currencies", response_model=list[CurrencyChoice])
async def currencies(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> list[CurrencyChoice]:
    """Active currencies for base and optional reporting currency selection."""
    _authorize(current)
    return await company_choices.currencies(db, request.app.state.reference_cache)


@router.get("/countries/{country_code}/licence-types", response_model=list[LicenceTypeChoice])
async def licence_types(
    country_code: str = Path(pattern=r"^[A-Z]{2}$"),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> list[LicenceTypeChoice]:
    """Supported licence kinds; validity requirements describe platform validation."""
    _authorize(current)
    await _country(db, country_code)
    return [
        LicenceTypeChoice(
            kind=spec.kind,
            label=spec.label,
            valid_to_required=spec.has_expiry,
            prints_on_invoice=spec.prints_on_invoice,
        )
        for spec in sorted(profile(country_code).licences, key=lambda spec: spec.kind)
    ]

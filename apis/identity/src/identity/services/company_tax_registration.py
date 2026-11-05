"""Validated registration writes shared by initial setup and company settings.

Callers enforce authority and hold the company/tenant mutation locks. This service
never commits, so company creation, registration and their audit outboxes are atomic.
"""

import uuid

from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.jurisdiction import profile
from billing_platform.outbox import emit
from billing_platform.statutory import TaxRegistration
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor
from identity.domain.company_registration import assert_registration_writable, registration_class_of
from identity.models import Company, CompanyAddress, CompanyTaxRegistration, State
from identity.schemas.company_statutory import InitialTaxRegistration, TaxRegistrationCreate


async def _validate_address(
    db: AsyncSession, company_id: uuid.UUID, address_id: uuid.UUID | None
) -> None:
    if address_id is None:
        return
    row = await db.get(CompanyAddress, address_id)
    if row is None or row.company_id != company_id or not row.is_active:
        raise ValidationFailedError(
            "invalid registered address",
            fields={"registered_address_id": "must be an active address of this company"},
        )


async def _state_tax_codes(db: AsyncSession, country_code: str) -> dict[str, str | None]:
    """The country's state codes, each mapped to its GST state code (or ``None``)."""
    rows = await db.execute(
        select(State.code, State.tax_jurisdiction_code).where(State.country_code == country_code)
    )
    return dict(rows.tuples().all())


def _as_tax_registration(row: CompanyTaxRegistration) -> TaxRegistration:
    return TaxRegistration(
        tax_system=row.tax_system,
        regime=row.regime,
        number=row.number,
        jurisdiction_code=row.jurisdiction_code,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        is_primary=row.is_primary,
        legal_name_on_registration=row.legal_name_on_registration,
    )


async def _company_registrations(
    db: AsyncSession, company_id: uuid.UUID, *, exclude: uuid.UUID | None = None
) -> list[CompanyTaxRegistration]:
    rows = await db.scalars(
        select(CompanyTaxRegistration).where(CompanyTaxRegistration.company_id == company_id)
    )
    return [row for row in rows.all() if exclude is None or row.id != exclude]


async def create_registration(
    db: AsyncSession,
    current: Actor,
    company: Company,
    body: TaxRegistrationCreate,
) -> CompanyTaxRegistration:
    company_id = company.id
    await _validate_address(db, company_id, body.registered_address_id)
    incoming = TaxRegistration(
        tax_system=body.tax_system,
        regime=body.regime,
        number=body.number,
        jurisdiction_code=body.jurisdiction_code,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        is_primary=body.is_primary,
        legal_name_on_registration=body.legal_name_on_registration,
    )
    existing = [_as_tax_registration(r) for r in await _company_registrations(db, company_id)]
    number = assert_registration_writable(
        incoming=incoming,
        existing=existing,
        country_code=company.country_code,
        state_tax_codes=await _state_tax_codes(db, company.country_code),
    )
    now = utcnow()
    row = CompanyTaxRegistration(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company_id,
        tax_system=body.tax_system,
        regime=body.regime,
        registration_class=registration_class_of(incoming),
        number=number,
        jurisdiction_code=body.jurisdiction_code,
        legal_name_on_registration=body.legal_name_on_registration,
        registered_address_id=body.registered_address_id,
        is_primary=body.is_primary,
        verified_at=None,
        verified_by=None,
        verification_reference=None,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(row)
    emit(
        db,
        aggregate_type="company",
        aggregate_id=company_id,
        event_type="company.tax_registration_added",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            company_id=company_id,
            action="company.tax_registration_added",
            entity_type="company_tax_registration",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )
    await db.flush()
    return row


async def create_initial_registration(
    db: AsyncSession,
    current: Actor,
    company: Company,
    body: InitialTaxRegistration,
) -> CompanyTaxRegistration:
    jurisdiction = profile(company.country_code)
    incoming = TaxRegistrationCreate(
        **body.model_dump(),
        tax_system=company.default_tax_system,
        jurisdiction_code=company.state_code
        if jurisdiction.tax_registration_is_per == "state"
        else company.country_code,
        legal_name_on_registration=company.legal_name,
        is_primary=True,
    )
    try:
        return await create_registration(db, current, company, incoming)
    except ValidationFailedError as error:
        fields = error.extra.get("fields", {})
        raise ValidationFailedError(
            error.message,
            fields={"initial_tax_registration." + key: value for key, value in fields.items()},
        ) from error

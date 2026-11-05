"""A company's tax registrations, statutory IDs, licences and addresses.

All are company sub-resources, so every handler loads the company and checks the
object-level scope against it (CLAUDE.md §5.2) on top of the endpoint permission.

The statutory-ID path is the one that carries a legal exposure: a full AADHAAR/SSN
reaching the table is not a review nit, it is an offence (docs/company.md §4.3), so the
full value is discarded in ``domain/`` before the row is built, re-checked at the point
of persistence, and never placed in the response, the audit ``changes``, or a log line.
"""

from __future__ import annotations

import dataclasses
import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from billing_platform.statutory import Licence
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload, jsonable
from identity.api.auth import Actor, actor
from identity.api.common import load_company as _load_company
from identity.api.dependencies import session
from identity.api.listing import paged
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.domain.company_jurisdiction import assert_statutory_row_storable, plan_statutory_id
from identity.domain.company_registration import (
    assert_licence_writable,
    assert_registration_coexists,
    registration_changes,
)
from identity.models import (
    Company,
    CompanyAddress,
    CompanyLicence,
    CompanyStatutoryId,
    CompanyTaxRegistration,
    State,
)
from identity.schemas.base import Page
from identity.schemas.company_statutory import (
    AddressCreate,
    AddressItem,
    LicenceCreate,
    LicenceItem,
    StatutoryIdCreate,
    StatutoryIdItem,
    TaxRegistrationCreate,
    TaxRegistrationItem,
    TaxRegistrationUpdate,
)
from identity.services.company_tax_registration import (
    _as_tax_registration,
    _company_registrations,
    _validate_address,
    create_registration,
)

router = APIRouter(responses=ERROR_RESPONSES, route_class=StrictRoute, prefix="/v1")


async def _active_company(
    db: AsyncSession, current: Actor, company_id: uuid.UUID, permission: str
) -> Company:
    current.require(permission)
    company = await _load_company(db, company_id, for_update=True)
    current.require_scope(permission, target=ScopePath(company_id=company_id))
    if company.status != "active":
        raise ConflictError("Only active companies can receive new setup records.")
    return company


# --- tax registrations --------------------------------------------------------


@router.post(
    "/companies/{company_id}/tax-registrations",
    response_model=TaxRegistrationItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_tax_registration(
    company_id: uuid.UUID,
    body: TaxRegistrationCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyTaxRegistration:
    company = await _active_company(db, current, company_id, "company.tax_registration.manage")

    row = await create_registration(db, current, company, body)
    from identity.services.company_setup import refresh_accounting_defaults

    await refresh_accounting_defaults(db, current, company_id)
    return row


@router.get("/companies/{company_id}/tax-registrations", response_model=Page[TaxRegistrationItem])
async def list_tax_registrations(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    q: str | None = Query(default=None, min_length=2, max_length=100),
    registration_id: uuid.UUID | None = Query(default=None, alias="id"),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[TaxRegistrationItem]:
    current.require("company.read")
    await _load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    emit(
        db,
        aggregate_type="company",
        aggregate_id=company_id,
        event_type="company.tax_registrations_read",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            action="company.tax_registrations_read",
            entity_type="company_tax_registration",
            entity_id=company_id,
            actor_user_id=current.user_id,
            category="access",
            company_id=company_id,
        ),
    )
    statement = select(CompanyTaxRegistration).where(
        CompanyTaxRegistration.company_id == company_id
    )
    if q:
        statement = statement.where(
            CompanyTaxRegistration.number.startswith(q.strip(), autoescape=True)
        )
    if registration_id is not None:
        statement = statement.where(CompanyTaxRegistration.id == registration_id)
    return await paged(
        db,
        request,
        statement,
        model=CompanyTaxRegistration,
        schema=TaxRegistrationItem,
        limit=limit,
        cursor=cursor,
    )


@router.patch(
    "/companies/{company_id}/tax-registrations/{registration_id}",
    response_model=TaxRegistrationItem,
)
async def amend_tax_registration(
    company_id: uuid.UUID,
    registration_id: uuid.UUID,
    body: TaxRegistrationUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyTaxRegistration:
    current.require("company.tax_registration.manage")
    # The company row lock serializes every registration write for the company, so
    # the overlap and single-primary checks below see a stable set of rows.
    await _load_company(db, company_id, for_update=True)
    current.require_scope(
        "company.tax_registration.manage", target=ScopePath(company_id=company_id)
    )
    row = await db.get(CompanyTaxRegistration, registration_id)
    if row is None or row.company_id != company_id:
        raise NotFoundError("tax registration not found")

    incoming_values = body.model_dump(exclude_unset=True)
    # What the registration *is* — regime, number, jurisdiction, valid_from — is
    # immutable after create: 422 for every actor, judged on the diff in domain/.
    changes = registration_changes(
        {name: getattr(row, name) for name in incoming_values}, incoming_values
    )
    if not changes:
        return row
    if "registered_address_id" in changes:
        await _validate_address(db, company_id, changes["registered_address_id"])
    merged = dataclasses.replace(
        _as_tax_registration(row),
        **{
            name: value
            for name, value in changes.items()
            if name in {"valid_to", "is_primary", "legal_name_on_registration"}
        },
    )
    existing = [
        _as_tax_registration(r)
        for r in await _company_registrations(db, company_id, exclude=registration_id)
    ]
    assert_registration_coexists(incoming=merged, existing=existing)
    audit_changes = {
        name: {"from": jsonable(getattr(row, name)), "to": jsonable(value)}
        for name, value in changes.items()
    }
    for name, value in changes.items():
        setattr(row, name, value)
    row.updated_at = utcnow()
    row.updated_by = current.user_id
    emit(
        db,
        aggregate_type="company",
        aggregate_id=company_id,
        event_type="company.tax_registration_amended",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            company_id=company_id,
            action="company.tax_registration_amended",
            entity_type="company_tax_registration",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
            # The changed-field set. Values outside identity's audit allowlist
            # (legal name, address id) are redacted by `audit_payload`.
            changes=audit_changes,
        ),
    )
    await db.flush()
    return row


# --- statutory ids ------------------------------------------------------------


@router.post(
    "/companies/{company_id}/statutory-ids",
    response_model=StatutoryIdItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_statutory_id(
    company_id: uuid.UUID,
    body: StatutoryIdCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyStatutoryId:
    company = await _active_company(db, current, company_id, "company.statutory_id.manage")

    # Discard happens here, before anything is built: a restricted value returns
    # ``value=None`` and only ``value_last4``. The full number is never bound to a row.
    stored = plan_statutory_id(country_code=company.country_code, kind=body.kind, value=body.value)
    assert_statutory_row_storable(
        country_code=company.country_code,
        kind=body.kind,
        value=stored.value,
        value_last4=stored.value_last4,
    )
    duplicate = await db.scalar(
        select(CompanyStatutoryId.id).where(
            CompanyStatutoryId.company_id == company_id,
            CompanyStatutoryId.kind == body.kind,
            CompanyStatutoryId.value_last4 == stored.value_last4,
        )
    )
    if duplicate is not None:
        raise ConflictError("this statutory identifier is already recorded for the company")

    row = CompanyStatutoryId(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company_id,
        kind=body.kind,
        value=stored.value,
        value_last4=stored.value_last4,
        holder_name=body.holder_name,
        issued_on=body.issued_on,
        valid_to=body.valid_to,
        verified_at=None,
        verified_by=None,
        verification_reference=body.verification_reference,
        is_active=True,
        deactivated_at=None,
        deactivated_by=None,
    )
    db.add(row)
    emit(
        db,
        aggregate_type="company",
        aggregate_id=company_id,
        event_type="company.statutory_id_added",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            company_id=company_id,
            action="company.statutory_id_added",
            entity_type="company_statutory_id",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
            # The value is deliberately absent from the audit changes — the last four
            # and the kind are the most that may be recorded (CLAUDE.md §6.9).
            changes={
                "kind": {"from": None, "to": body.kind},
                "last4": {"from": None, "to": stored.value_last4},
            },
        ),
    )
    await db.flush()
    return row


@router.get("/companies/{company_id}/statutory-ids", response_model=Page[StatutoryIdItem])
async def list_statutory_ids(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[StatutoryIdItem]:
    current.require("company.read")
    await _load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    return await paged(
        db,
        request,
        select(CompanyStatutoryId).where(CompanyStatutoryId.company_id == company_id),
        model=CompanyStatutoryId,
        schema=StatutoryIdItem,
        limit=limit,
        cursor=cursor,
    )


# --- licences -----------------------------------------------------------------


@router.post(
    "/companies/{company_id}/licences",
    response_model=LicenceItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_licence(
    company_id: uuid.UUID,
    body: LicenceCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyLicence:
    company = await _active_company(db, current, company_id, "company.licence.manage")

    if body.premises_address_id is not None:
        premises = await db.get(CompanyAddress, body.premises_address_id)
        if premises is None or premises.company_id != company_id or not premises.is_active:
            raise ValidationFailedError(
                "invalid licence premises",
                fields={"premises_address_id": "must be an active address of this company"},
            )

    assert_licence_writable(
        incoming=Licence(
            kind=body.kind,
            number=body.number,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            is_primary=body.is_primary,
        ),
        country_code=company.country_code,
    )
    now = utcnow()
    row = CompanyLicence(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company_id,
        kind=body.kind,
        number=body.number,
        issuing_authority=body.issuing_authority,
        premises_address_id=body.premises_address_id,
        issued_on=body.issued_on,
        renewal_reminder_days=body.renewal_reminder_days,
        document_url=body.document_url,
        is_primary=body.is_primary,
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
        event_type="company.licence_added",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            company_id=company_id,
            action="company.licence_added",
            entity_type="company_licence",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )
    await db.flush()
    return row


@router.get("/companies/{company_id}/licences", response_model=Page[LicenceItem])
async def list_licences(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[LicenceItem]:
    current.require("company.read")
    await _load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    return await paged(
        db,
        request,
        select(CompanyLicence).where(CompanyLicence.company_id == company_id),
        model=CompanyLicence,
        schema=LicenceItem,
        limit=limit,
        cursor=cursor,
    )


# --- addresses ----------------------------------------------------------------


@router.post(
    "/companies/{company_id}/addresses",
    response_model=AddressItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_address(
    company_id: uuid.UUID,
    body: AddressCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyAddress:
    await _active_company(db, current, company_id, "company.update")
    from identity.models import Country
    from identity.services.reference_availability import lock_configuration, require_delivered

    await lock_configuration(db)

    country = await db.scalar(
        select(Country).where(Country.code == body.country_code).with_for_update()
    )
    state = await db.scalar(select(State).where(State.code == body.state_code).with_for_update())
    if country is None or not country.is_active or state is None or not state.is_active:
        raise ValidationFailedError("choose an active country and state")
    await require_delivered(db, "country", body.country_code)
    await require_delivered(db, "state", body.state_code)
    pair = await db.scalar(
        select(State.code).where(
            State.country_code == body.country_code, State.code == body.state_code
        )
    )
    if pair is None:
        raise ValidationFailedError(
            "unknown jurisdiction",
            fields={
                "state_code": f"{body.state_code!r} is not a subdivision of {body.country_code!r}"
            },
        )
    row = CompanyAddress(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company_id,
        type=body.type,
        label=body.label,
        line1=body.line1,
        line2=body.line2,
        city=body.city,
        state_code=body.state_code,
        postal_code=body.postal_code,
        country_code=body.country_code,
        is_primary=body.is_primary,
        is_active=True,
        deactivated_at=None,
        deactivated_by=None,
    )
    db.add(row)
    emit(
        db,
        aggregate_type="company",
        aggregate_id=company_id,
        event_type="company.address_added",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            company_id=company_id,
            action="company.address_added",
            entity_type="company_address",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )
    await db.flush()
    return row


@router.get("/companies/{company_id}/addresses", response_model=Page[AddressItem])
async def list_addresses(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[AddressItem]:
    current.require("company.read")
    await _load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    return await paged(
        db,
        request,
        select(CompanyAddress).where(CompanyAddress.company_id == company_id),
        model=CompanyAddress,
        schema=AddressItem,
        limit=limit,
        cursor=cursor,
    )

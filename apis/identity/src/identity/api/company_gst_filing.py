"""Scoped filing preferences; frequency and start are immutable."""

import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from billing_platform.tax import regimes_for
from fastapi import Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor, actor
from identity.api.common import load_company as _load_company
from identity.api.company_statutory import _active_company, router
from identity.api.dependencies import session
from identity.api.listing import paged
from identity.models.company_gst_filing import CompanyGstFilingPreference as Preference
from identity.models.company_tax_registration import CompanyTaxRegistration
from identity.schemas.base import Page
from identity.schemas.company_gst_filing import (
    GstFilingClose,
    GstFilingCreate,
    GstFilingItem,
    GstRegistrationSetup,
)
from identity.schemas.company_statutory import TaxRegistrationCreate
from identity.services import company_choices


@router.get("/companies/{company_id}/gst-registration-setup", response_model=GstRegistrationSetup)
async def registration_setup(
    company_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> GstRegistrationSetup:
    company = await _load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    india_gst = company.country_code == "IN" and company.default_tax_system == "gst_in"
    can_manage = False
    if india_gst and company.status == "active" and current.impersonation_id is None:
        try:
            current.require_scope(
                "company.tax_registration.manage", target=ScopePath(company_id=company_id)
            )
            can_manage = True
        except PermissionDeniedError:
            pass
    return GstRegistrationSetup(
        country_code=company.country_code,
        default_tax_system=company.default_tax_system,
        can_manage=can_manage,
        regimes={key: value.label for key, value in regimes_for("gst_in").items()}
        if india_gst
        else {},
        states=await company_choices.states(db, "IN", request.app.state.reference_cache)
        if india_gst
        else [],
        create_schema=TaxRegistrationCreate.model_json_schema() if india_gst else {},
    )


def audit(db: AsyncSession, current: Actor, company: uuid.UUID, row: Preference) -> None:
    emit(
        db,
        aggregate_type="company",
        aggregate_id=company,
        event_type="company.gst_filing_changed",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            company_id=company,
            action="company.gst_filing_changed",
            entity_type="company_gst_filing_preference",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )


@router.post(
    "/companies/{company_id}/gst-filing-preferences", response_model=GstFilingItem, status_code=201
)
async def create(
    company_id: uuid.UUID,
    body: GstFilingCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Preference:
    await _active_company(db, current, company_id, "company.tax_registration.manage")
    registration = await db.get(CompanyTaxRegistration, body.registration_id)
    if registration is None or registration.company_id != company_id:
        raise NotFoundError("GST registration not found")
    if registration.tax_system != "gst_in" or registration.regime not in {
        "regular",
        "sez_unit",
        "sez_developer",
        "casual_taxable_person",
    }:
        raise ValidationFailedError("this registration does not file GSTR-3B")
    rows = list(
        await db.scalars(
            select(Preference)
            .where(
                Preference.company_id == company_id,
                Preference.registration_id == body.registration_id,
            )
            .limit(201)
        )
    )
    if len(rows) >= 200:
        raise ConflictError("GST filing history exceeds its supported bound")
    if any(
        body.valid_from < (row.valid_to or body.valid_from.max)
        and row.valid_from < (body.valid_to or body.valid_from.max)
        for row in rows
    ):
        raise ConflictError("GST filing preferences overlap")
    now = utcnow()
    row = Preference(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company_id,
        **body.model_dump(),
        created_by=current.user_id,
        updated_by=current.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    audit(db, current, company_id, row)
    await db.flush()
    return row


@router.get("/companies/{company_id}/gst-filing-preferences", response_model=Page[GstFilingItem])
async def read(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[GstFilingItem]:
    await _load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    return await paged(
        db,
        request,
        select(Preference).where(Preference.company_id == company_id),
        model=Preference,
        schema=GstFilingItem,
        limit=limit,
        cursor=cursor,
    )


@router.patch(
    "/companies/{company_id}/gst-filing-preferences/{object_id}", response_model=GstFilingItem
)
async def close(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: GstFilingClose,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Preference:
    await _active_company(db, current, company_id, "company.tax_registration.manage")
    row = await db.get(Preference, object_id)
    if row is None or row.company_id != company_id:
        raise NotFoundError("GST filing preference not found")
    if row.valid_to is not None:
        if row.valid_to == body.valid_to:
            return row
        raise ConflictError("closed filing preference is immutable")
    GstFilingCreate.model_validate(
        {
            "registration_id": row.registration_id,
            "frequency": row.frequency,
            "valid_from": row.valid_from,
            "valid_to": body.valid_to,
        }
    )
    row.valid_to = body.valid_to
    row.updated_by = current.user_id
    row.updated_at = utcnow()
    audit(db, current, company_id, row)
    await db.flush()
    return row

"""Scoped profile history. Closed records and reporting inputs are immutable."""

import datetime as dt
import uuid
from decimal import Decimal

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
from fastapi import Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor, actor
from identity.api.common import load_company
from identity.api.company_statutory import _active_company, router
from identity.api.dependencies import session
from identity.api.listing import paged
from identity.models.company_gst_outward import CompanyGstOutwardProfile as Profile
from identity.models.company_tax_registration import CompanyTaxRegistration
from identity.schemas.base import Page
from identity.schemas.company_gst_outward import (
    GstOutwardProfileClose,
    GstOutwardProfileCreate,
    GstOutwardProfileItem,
    GstOutwardProfileSetup,
)


@router.get(
    "/companies/{company_id}/gst-outward-profile-setup", response_model=GstOutwardProfileSetup
)
async def setup(
    company_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> GstOutwardProfileSetup:
    company = await load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    can_manage = False
    if (
        company.country_code == "IN"
        and company.status == "active"
        and current.impersonation_id is None
    ):
        try:
            current.require_scope(
                "company.tax_registration.manage", target=ScopePath(company_id=company_id)
            )
            can_manage = True
        except PermissionDeniedError:
            pass
    return GstOutwardProfileSetup(
        can_manage=can_manage, create_schema=GstOutwardProfileCreate.model_json_schema()
    )


def audit(db: AsyncSession, current: Actor, row: Profile) -> None:
    emit(
        db,
        aggregate_type="company",
        aggregate_id=row.company_id,
        event_type="company.gst_outward_profile_changed",
        tenant_id=current.tenant_id,
        payload=audit_payload(
            company_id=row.company_id,
            action="company.gst_outward_profile_changed",
            entity_type="company_gst_outward_profile",
            entity_id=row.id,
            actor_user_id=current.user_id,
            category="admin",
        ),
    )


@router.post(
    "/companies/{company_id}/gst-outward-profiles",
    response_model=GstOutwardProfileItem,
    status_code=201,
)
async def create(
    company_id: uuid.UUID,
    body: GstOutwardProfileCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Profile:
    company = await _active_company(db, current, company_id, "company.tax_registration.manage")
    if current.impersonation_id:
        raise PermissionDeniedError("support impersonation cannot configure statutory profiles")
    registration = await db.get(CompanyTaxRegistration, body.registration_id)
    if registration is None or registration.company_id != company_id:
        raise NotFoundError("GST registration not found")
    if (
        company.country_code != "IN"
        or registration.tax_system != "gst_in"
        or registration.regime
        not in {"regular", "sez_unit", "sez_developer", "casual_taxable_person"}
    ):
        raise ValidationFailedError("select an Indian GSTIN with an outward-return obligation")
    rows = list(
        await db.scalars(
            select(Profile)
            .where(
                Profile.company_id == company_id, Profile.registration_id == body.registration_id
            )
            .limit(201)
        )
    )
    if len(rows) >= 200:
        raise ConflictError("GST reporting profile history exceeds its supported bound")
    if any(
        body.valid_from < (row.valid_to or dt.date.max)
        and row.valid_from < (body.valid_to or dt.date.max)
        for row in rows
    ):
        raise ConflictError("GST reporting profiles overlap")
    values = body.model_dump()
    values["annual_turnover"] = Decimal(body.annual_turnover)
    row = Profile(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company_id,
        **values,
        created_by=current.user_id,
        updated_by=current.user_id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(row)
    audit(db, current, row)
    await db.flush()
    return row


@router.get(
    "/companies/{company_id}/gst-outward-profiles", response_model=Page[GstOutwardProfileItem]
)
async def read(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[GstOutwardProfileItem]:
    await load_company(db, company_id)
    current.require_scope("company.read", target=ScopePath(company_id=company_id))
    return await paged(
        db,
        request,
        select(Profile).where(Profile.company_id == company_id),
        model=Profile,
        schema=GstOutwardProfileItem,
        limit=limit,
        cursor=cursor,
    )


@router.patch(
    "/companies/{company_id}/gst-outward-profiles/{object_id}", response_model=GstOutwardProfileItem
)
async def close(
    company_id: uuid.UUID,
    object_id: uuid.UUID,
    body: GstOutwardProfileClose,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Profile:
    await _active_company(db, current, company_id, "company.tax_registration.manage")
    if current.impersonation_id:
        raise PermissionDeniedError("support impersonation cannot configure statutory profiles")
    row = await db.get(Profile, object_id)
    if row is None or row.company_id != company_id:
        raise NotFoundError("GST reporting profile not found")
    if row.valid_to:
        if row.valid_to == body.valid_to:
            return row
        raise ConflictError("closed reporting profile is immutable")
    GstOutwardProfileCreate.model_validate(
        {
            "registration_id": row.registration_id,
            "annual_turnover": row.annual_turnover,
            "rule_14a": row.rule_14a,
            "valid_from": row.valid_from,
            "valid_to": body.valid_to,
            "reference": row.reference,
            "evidence_hash": row.evidence_hash,
        }
    )
    row.valid_to = body.valid_to
    row.updated_by = current.user_id
    row.updated_at = utcnow()
    audit(db, current, row)
    await db.flush()
    return row

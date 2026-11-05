"""Read-only withholding preview over the company's effective withholding masters."""

from __future__ import annotations

import datetime as dt
from typing import Any, cast

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.api.auth import Access
from accounting.domain.withholding import (
    CertificateTerms,
    ProfileTerms,
    RateTerms,
    resolve_withholding,
)
from accounting.models import masters as m
from accounting.resources import BY_NAME
from accounting.schemas.masters import WithholdingKind
from accounting.schemas.withholding import (
    WithholdingPreview,
    WithholdingPreviewPortion,
    WithholdingPreviewRequest,
)
from accounting.tasks.access import authorize
from accounting.tasks.finance_records import require_fields
from accounting.tasks.financial_commands import financial_context
from accounting.tasks.validation import require_withholding_feature

INPUTS = {
    "withholding_section": {"kind", "status"},
    "withholding_rate": {
        "section_id",
        "deductee_type",
        "rate_percent",
        "no_pan_rate_percent",
        "single_transaction_threshold",
        "aggregate_annual_threshold",
        "threshold_currency",
        "threshold_basis",
        "valid_from",
        "valid_to",
    },
    "party_withholding_profile": {
        "party_id",
        "kind",
        "deductible",
        "deductee_type",
        "pan_status",
        "valid_from",
        "valid_to",
    },
    "withholding_certificate": {
        "party_id",
        "section_id",
        "rate_percent",
        "amount_limit",
        "valid_from",
        "valid_to",
    },
}
# Overlap is rejected at write time; a larger result means the masters are corrupt.
LIMIT = 11


def require_preview_permission(access: Access) -> None:
    """Checked as a route dependency so a caller without access learns nothing from 422s."""
    authorize(access, BY_NAME["withholding_rate"], "read")


async def effective(
    db: AsyncSession, access: Access, model: Any, on: dt.date, **keys: Any
) -> list[Any]:
    statement = select(model).where(
        model.company_id == access.context.company_id,
        model.valid_from <= on,
        (model.valid_to.is_(None)) | (model.valid_to >= on),
        *(getattr(model, key) == value for key, value in keys.items()),
    )
    rows = list(await db.scalars(statement.order_by(model.id).limit(LIMIT)))
    if len(rows) >= LIMIT:
        raise ConflictError("withholding masters overlap on the posting date")
    for row in rows:
        require_fields(access, model.__tablename__, INPUTS[model.__tablename__], row=row)
    return rows


async def preview(
    db: AsyncSession, access: Access, body: WithholdingPreviewRequest
) -> WithholdingPreview:
    for name, fields in INPUTS.items():
        require_fields(access, name, fields)
    facts = financial_context(access)
    company = access.context.company_id
    section = await company_object(db, m.WithholdingSection, body.section_id, company_id=company)
    await company_object(db, m.Party, body.party_id, company_id=company)
    require_fields(access, "withholding_section", INPUTS["withholding_section"], row=section)
    require_withholding_feature(access, section.kind)
    if section.status != "ACTIVE":
        raise ConflictError("withholding section is not active")
    if body.currency != access.context.base_currency:
        raise ValidationFailedError("withholding is previewed in the company base currency")
    rates = await effective(db, access, m.WithholdingRate, body.posting_date, section_id=section.id)
    profiles = await effective(
        db,
        access,
        m.PartyWithholdingProfile,
        body.posting_date,
        party_id=body.party_id,
        kind=section.kind,
    )
    certificates = await effective(
        db,
        access,
        m.WithholdingCertificate,
        body.posting_date,
        party_id=body.party_id,
        section_id=section.id,
    )
    result = resolve_withholding(
        kind=section.kind,
        rates=[
            RateTerms(
                row.id,
                row.deductee_type,
                row.rate_percent,
                row.no_pan_rate_percent,
                row.single_transaction_threshold,
                row.aggregate_annual_threshold,
                row.threshold_basis,
                row.valid_from,
                row.valid_to,
            )
            for row in rates
        ],
        profiles=[
            ProfileTerms(
                row.id,
                row.kind,
                row.deductible,
                row.deductee_type,
                row.pan_status,
                row.valid_from,
                row.valid_to,
            )
            for row in profiles
        ],
        certificates=[
            CertificateTerms(
                row.id, row.rate_percent, row.amount_limit, row.valid_from, row.valid_to
            )
            for row in certificates
        ],
        posting_date=body.posting_date,
        amount=body.amount,
        ytd_amount=body.ytd_amount,
        ytd_withheld_base=body.ytd_withheld_base,
        certificate_consumed=body.certificate_consumed,
        precision=facts.amount_precision,
        rounding=facts.rounding_mode,
    )
    return WithholdingPreview(
        kind=cast(WithholdingKind, section.kind),
        party_id=body.party_id,
        section_id=section.id,
        posting_date=body.posting_date,
        applies=result.applies,
        reason=result.reason,
        profile_id=result.profile_id,
        rate_id=result.rate_id,
        certificate_id=result.certificate_id,
        threshold_crossed=result.threshold_crossed,
        currency=body.currency,
        base_amount=result.base_amount,
        withholding_amount=result.withholding_amount,
        portions=[
            WithholdingPreviewPortion(
                base_amount=portion.base_amount,
                rate_percent=portion.rate_percent,
                rate_source=portion.rate_source,
                amount=portion.amount,
            )
            for portion in result.portions
        ],
    )

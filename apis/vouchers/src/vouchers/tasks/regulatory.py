"""Indexed, date-resolved owner evidence for regulated voucher execution."""

import datetime as dt
import uuid

from billing_platform.errors import ConflictError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vouchers.domain.regulatory import (
    DealerLicenceSelection,
    RegulatorySelection,
    required_dealer_form,
)
from vouchers.models.core import VoucherItemRegulatoryProjection, VoucherPartyDrugLicenceProjection


async def effective(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, as_of: dt.date
) -> RegulatorySelection | None:
    rows = list(
        await db.scalars(
            select(VoucherItemRegulatoryProjection)
            .where(
                VoucherItemRegulatoryProjection.company_id == company_id,
                VoucherItemRegulatoryProjection.item_id == item_id,
                VoucherItemRegulatoryProjection.valid_from <= as_of,
                or_(
                    VoucherItemRegulatoryProjection.valid_to.is_(None),
                    VoucherItemRegulatoryProjection.valid_to >= as_of,
                ),
            )
            .limit(2)
        )
    )
    if len(rows) > 1:
        raise ConflictError("ambiguous regulatory classification source")
    if not rows:
        return None
    row = rows[0]
    return RegulatorySelection(
        classification_id=row.classification_id,
        source_version=row.source_version,
        item_id=row.item_id,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        product_kind=row.product_kind,
        licence_class=row.licence_class,
        prescription_schedule=row.prescription_schedule,
        source_sha256=row.source_sha256,
        food_category_code=row.food_category_code,
    )


async def effective_dealer_licence(
    db: AsyncSession,
    company_id: uuid.UUID,
    party_id: uuid.UUID,
    address_id: uuid.UUID,
    operation: str,
    licence_class: str,
    as_of: dt.date,
) -> DealerLicenceSelection | None:
    form = required_dealer_form(operation, licence_class)
    rows = list(
        await db.scalars(
            select(VoucherPartyDrugLicenceProjection)
            .where(
                VoucherPartyDrugLicenceProjection.company_id == company_id,
                VoucherPartyDrugLicenceProjection.party_id == party_id,
                VoucherPartyDrugLicenceProjection.address_id == address_id,
                VoucherPartyDrugLicenceProjection.licence_form == form,
                VoucherPartyDrugLicenceProjection.valid_from <= as_of,
                or_(
                    VoucherPartyDrugLicenceProjection.valid_to.is_(None),
                    VoucherPartyDrugLicenceProjection.valid_to >= as_of,
                ),
            )
            .limit(2)
        )
    )
    if len(rows) > 1:
        raise ConflictError("ambiguous counterparty dealer licence source")
    if not rows:
        return None
    row = rows[0]
    return DealerLicenceSelection(
        licence_id=row.licence_id,
        source_version=row.source_version,
        party_id=row.party_id,
        address_id=row.address_id,
        licence_form=row.licence_form,
        licence_number=row.licence_number,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        source_sha256=row.source_sha256,
    )

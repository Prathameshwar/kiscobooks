"""Resolve verified dealer permission at the actual party trading premises."""

import datetime as dt
import uuid

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from accounting.domain.pharmacy_licences import LicenceClass, Operation, required_form
from accounting.models.masters import Party, PartyAddress, PartyDrugLicence


async def effective_dealer_licence(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    party_id: uuid.UUID,
    address_id: uuid.UUID,
    operation: Operation,
    licence_class: LicenceClass,
    as_of: dt.date,
) -> PartyDrugLicence:
    form = required_form(operation, licence_class)
    party = await company_object(db, Party, party_id, company_id=company_id)
    address = await company_object(db, PartyAddress, address_id, company_id=company_id)
    if party.status != "ACTIVE" or address.status != "ACTIVE" or address.party_id != party.id:
        raise ConflictError("counterparty trading premises are unavailable")
    rows = list(
        await db.scalars(
            select(PartyDrugLicence)
            .where(
                PartyDrugLicence.company_id == company_id,
                PartyDrugLicence.party_id == party_id,
                PartyDrugLicence.address_id == address_id,
                PartyDrugLicence.licence_form == form,
                PartyDrugLicence.valid_from <= as_of,
                or_(PartyDrugLicence.valid_to.is_(None), PartyDrugLicence.valid_to >= as_of),
            )
            .limit(2)
        )
    )
    if len(rows) != 1:
        raise ConflictError("one effective reviewed counterparty drug licence is required")
    return rows[0]

"""Read-only company-namespace collision preflight; registration remains authoritative."""

from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.identifiers import normalized

from accounting.api.auth import Access
from accounting.models.stock_tracking import StockUnitIdentifier
from accounting.schemas.stock_tracking import SerialIdentityCheck
from accounting.stock_resources import SERIAL
from accounting.tasks.access import authorize, readable
from accounting.tasks.stock_tracking import assert_feature


async def check_identifiers(db: AsyncSession, access: Access, body: SerialIdentityCheck) -> None:
    authorize(access, SERIAL, "read")
    authorize(access, SERIAL, "manage")
    assert_feature(access, SERIAL)
    if "identifiers" not in readable(access, SERIAL):
        raise PermissionDeniedError("Serial identifiers must be readable")
    keys = [(entry.identifier_type, normalized(entry.value)) for entry in body.identifiers]
    model = StockUnitIdentifier
    found = set(
        await db.execute(
            select(model.identifier_type, model.normalized_value)
            .where(
                model.company_id == access.context.company_id,
                model.namespace_key == "COMPANY",
                tuple_(model.identifier_type, model.normalized_value).in_(set(keys)),
            )
            .limit(len(keys))
        )
    )
    errors = {
        f"identifiers.{index}.value": "This identifier is already registered in the company"
        for index, key in enumerate(keys)
        if key in found
    }
    if errors:
        raise ValidationFailedError("Serial identifiers already exist", fields=errors)

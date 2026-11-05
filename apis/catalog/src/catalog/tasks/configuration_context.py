"""One protected dated group lookup for configuration and product consumers."""

import datetime as dt
import uuid

from billing_platform.errors import ConflictError, PermissionDeniedError
from sqlalchemy import or_, select

from catalog.models.product_definitions import FamilyGroupAssignment
from catalog.tasks.configuration_access import ConfigurationAccess


async def family_group(
    access: ConfigurationAccess, family_id: uuid.UUID, as_of: dt.date
) -> FamilyGroupAssignment | None:
    context = await access.context(FamilyGroupAssignment)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("primary group selection is protected")
    rows = list(
        await access.db.scalars(
            select(FamilyGroupAssignment)
            .where(
                FamilyGroupAssignment.company_id == access.company,
                FamilyGroupAssignment.family_id == family_id,
                FamilyGroupAssignment.valid_from <= as_of,
                or_(
                    FamilyGroupAssignment.valid_to.is_(None),
                    FamilyGroupAssignment.valid_to >= as_of,
                ),
            )
            .limit(2)
        )
    )
    if len(rows) > 1:
        raise ConflictError("product has ambiguous primary group assignments")
    return rows[0] if rows else None

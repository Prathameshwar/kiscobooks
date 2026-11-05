"""Current authority and bounded dated classification evidence shared by product workflows."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.errors import ConflictError, PermissionDeniedError
from sqlalchemy import select

from catalog.domain.categories import cardinality
from catalog.models.classification import CategoryScheme, ItemCategory
from catalog.models.product_definitions import FamilyCategory
from catalog.tasks.configuration_access import ConfigurationAccess


async def rows(access: ConfigurationAccess, model: type[Any], *criteria: Any) -> list[Any]:
    context = await access.context(model)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("category dependencies require readable fields")
    result = list(
        await access.db.scalars(
            select(model)
            .where(model.company_id == access.company, *criteria)
            .order_by(model.id)
            .limit(10001)
        )
    )
    if len(result) > 10000:
        raise ConflictError("category dependency review exceeds its bounded capacity")
    for row in result:
        await access.require(row)
    return result


async def references(
    access: ConfigurationAccess, entries: list[Any], *, active: bool = True
) -> list[Any]:
    if active and len({entry.category_id for entry in entries}) != len(entries):
        raise ConflictError("effective category memberships must be distinct")
    result: dict[tuple[type[Any], uuid.UUID], Any] = {}
    grouped: dict[uuid.UUID, list[bool]] = {}
    for entry in entries:
        for model, object_id in (
            (CategoryScheme, entry.scheme_id),
            (ItemCategory, entry.category_id),
        ):
            key = (model, object_id)
            if key not in result:
                context = await access.context(model)
                if set(context.native.fields) - context.readable():
                    raise PermissionDeniedError("category reference fields are protected")
                value = await access.scoped(model, object_id)
                await access.require(value)
                if active and not value.is_active:
                    raise ConflictError("category membership references an inactive master")
                result[key] = value
        scheme, category = (
            result[CategoryScheme, entry.scheme_id],
            result[ItemCategory, entry.category_id],
        )
        if category.scheme_id != scheme.id:
            raise PermissionDeniedError("category belongs to another scheme")
        grouped.setdefault(scheme.id, []).append(entry.is_primary)
    if active:
        for scheme_id, flags in grouped.items():
            cardinality(result[CategoryScheme, scheme_id].membership_mode, flags)
    return list(result.values())


async def effective(
    access: ConfigurationAccess, family_id: uuid.UUID, as_of: dt.date
) -> tuple[list[Any], list[Any], list[str]]:
    entries = await rows(access, FamilyCategory, FamilyCategory.family_id == family_id)
    current = [
        row
        for row in entries
        if row.valid_from <= as_of and (row.valid_to is None or row.valid_to >= as_of)
    ]
    evidence = await references(access, current)
    required = await rows(
        access,
        CategoryScheme,
        CategoryScheme.is_active.is_(True),
        CategoryScheme.is_required.is_(True),
    )
    present = {row.scheme_id for row in current}
    missing = [
        "category_scheme:" + str(row.id)
        for row in required
        if row.is_required and row.id not in present
    ]
    return current, [*current, *evidence, *required], missing

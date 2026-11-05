"""Registered master ownership and protected mapping boundaries."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.access import company_object
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.option_sources import OPTION_SOURCES
from catalog.models.classification import ClassificationMaster
from catalog.models.tax import TaxCategory, TaxClassification, TaxRule
from catalog.models.units import PackType, UnitOfMeasure
from catalog.tasks.field_context import (
    MANAGE_PERMISSIONS,
    READ_PERMISSIONS,
    FieldContext,
    load_field_context,
)
from catalog.tasks.options import MODELS

Owner = ClassificationMaster | UnitOfMeasure | PackType | TaxCategory | TaxClassification | TaxRule
OWNERS = {source.entity: MODELS[key] for key, source in OPTION_SOURCES.items()}


async def owner_available(db: AsyncSession, actor: Actor, company: uuid.UUID, owner: Owner) -> bool:
    if isinstance(owner, TaxClassification):
        from catalog.tasks.configuration_access import ConfigurationAccess
        from catalog.tasks.pricing_commands import business_date
        from catalog.tasks.tax_history import withdrawn

        access = ConfigurationAccess(db, actor, company)
        await access.require(owner)
        today = business_date((await access.context(TaxClassification)).company.timezone)
        return (owner.__tablename__, owner.id) not in await withdrawn(
            access, resource=owner.__tablename__, target_id=owner.id
        ) and (owner.valid_to is None or owner.valid_to >= today)
    return owner.is_active


def owner_values(row: Owner, context: FieldContext) -> dict[str, Any]:
    native = {key: getattr(row, key) for key in context.native.fields}
    native.update(
        {
            "custom_field:" + key: value
            for key, value in (getattr(row, "custom_fields", None) or {}).items()
        }
    )
    return native


async def owner_access(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    *,
    writing: bool = False,
) -> FieldContext:
    if entity not in OWNERS:
        raise ValidationFailedError("unsupported Catalog mapping target")
    actor.require_scope(READ_PERMISSIONS[entity], target=ScopePath(company_id=company))
    context = await load_field_context(
        db,
        actor,
        company,
        entity,
        permission=MANAGE_PERMISSIONS[entity] if writing else None,
    )
    if "code" not in context.readable():
        raise PermissionDeniedError("master references require readable owner identity")
    return context


async def owner_context(
    db: AsyncSession,
    actor: Actor,
    company: uuid.UUID,
    entity: str,
    target_id: uuid.UUID,
    *,
    writing: bool = False,
) -> tuple[Owner, FieldContext]:
    context = await owner_access(db, actor, company, entity, writing=writing)
    row = await company_object(db, OWNERS[entity], target_id, company_id=company)
    return row, context


def disclosed_fields(context: FieldContext, native: dict[str, Any] | None = None) -> frozenset[str]:
    readable = context.readable(native)
    if (
        context.native.entity_type == "catalog.master_alias"
        and not {"alias", "canonical_value"} <= readable
    ):
        readable -= {"alias", "canonical_value"}
    return readable

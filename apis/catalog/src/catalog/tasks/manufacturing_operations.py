"""Operation identity and references, independent of financial/stock execution."""

import uuid
from collections.abc import Mapping
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ClassificationMaster
from catalog.models.manufacturing_operations import (
    ManufacturingOperation,
    ManufacturingOperationRevision,
)
from catalog.models.manufacturing_routes import ManufacturingRoute, ManufacturingRouteRevision
from catalog.models.products import Item, ProductFamily
from catalog.schemas.manufacturing_operations import OperationRevisionInput
from catalog.tasks.field_context import load_field_context


async def requirements(
    db: AsyncSession, actor: Actor, company: uuid.UUID, incoming: Mapping[str, Any]
) -> dict[str, Any]:
    body = OperationRevisionInput.model_validate(incoming)
    if body.service_item_id is not None:
        item_access = await load_field_context(db, actor, company, "catalog.item")
        family_access = await load_field_context(db, actor, company, "catalog.product_family")
        if (
            not {"family_id", "status"} <= item_access.readable()
            or not {"kind", "status"} <= family_access.readable()
        ):
            raise PermissionDeniedError(
                "operation service selection needs readable product kind and status"
            )
        item = await company_object(db, Item, body.service_item_id, company_id=company)
        family = await company_object(db, ProductFamily, item.family_id, company_id=company)
        if family.kind != "SERVICE" or item.status != "ACTIVE" or family.status != "ACTIVE":
            raise ValidationFailedError("choose an active service SKU for the operation")
    return body.model_dump()


async def validate_master(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    if (
        isinstance(row, ManufacturingOperation | ManufacturingRoute)
        and before
        and row.code != before["code"]
    ):
        revision_model = (
            ManufacturingOperationRevision
            if isinstance(row, ManufacturingOperation)
            else ManufacturingRouteRevision
        )
        parent_field = (
            revision_model.operation_id
            if revision_model is ManufacturingOperationRevision
            else ManufacturingRouteRevision.route_id
        )
        used = await db.scalar(
            select(revision_model.id)
            .where(
                revision_model.company_id == row.company_id,
                parent_field == row.id,
            )
            .limit(1)
        )
        if used is not None:
            raise ConflictError("referenced manufacturing identity is immutable")

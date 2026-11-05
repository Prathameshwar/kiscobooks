"""Commercial master relationships and lifecycle checks under the company lock."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from catalog.domain.classification import GroupNode, ParentInterval, validate_group_history
from catalog.domain.sources import SourceUnavailableError
from catalog.models.attributes import AttributeSet, AttributeSetRevision
from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import (
    Brand,
    BrandManufacturer,
    BrandSeries,
    Manufacturer,
    ManufacturerSite,
    ProductType,
    ProductTypeRevision,
)
from catalog.models.products import ProductFamily
from catalog.tasks.reference_locations import LOCATION_CODES, assert_reference_location


async def exists(db: AsyncSession, model: Any, *criteria: ColumnElement[bool]) -> bool:
    return await db.scalar(select(model.id).where(*criteria).limit(1)) is not None


async def validate_commercial(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any], *, today: dt.date
) -> None:
    """Only changed references require current owner records; old links retain history."""
    creating = not before
    activating = row.is_active and not before.get("is_active", False)
    code_changed = not creating and row.code != before["code"]
    deactivating = not row.is_active and before.get("is_active", False)
    if isinstance(row, Brand | Manufacturer):
        field = "owner_party_id" if isinstance(row, Brand) else "party_id"
        if getattr(row, field) is not None and (creating or getattr(row, field) != before[field]):
            raise SourceUnavailableError("Billing party references are not available yet")
    parent_model: type[ClassificationMaster] | None = None
    parent_id = None
    parent_field = ""
    if isinstance(row, Brand):
        parent_model, parent_id, parent_field = Brand, row.parent_brand_id, "parent_brand_id"
    elif isinstance(row, BrandSeries):
        parent_model, parent_id, parent_field = Brand, row.brand_id, "brand_id"
    elif isinstance(row, ManufacturerSite):
        parent_model, parent_id, parent_field = Manufacturer, row.manufacturer_id, "manufacturer_id"
    if (
        parent_model is not None
        and parent_id is not None
        and (creating or activating or parent_id != before.get(parent_field))
    ):
        parent = await company_object(db, parent_model, parent_id, company_id=row.company_id)
        if not parent.is_active:
            raise ConflictError("commercial parent is inactive")
    if isinstance(row, ManufacturerSite) and (
        creating or activating or any(getattr(row, f) != before.get(f) for f in LOCATION_CODES)
    ):
        await assert_reference_location(
            db, subject="site", country_code=row.country_code, state_code=row.state_code
        )
    if (
        isinstance(row, ProductType)
        and not creating
        and (code_changed or row.kind != before["kind"])
    ):
        if await exists(
            db,
            ProductTypeRevision,
            ProductTypeRevision.company_id == row.company_id,
            ProductTypeRevision.product_type_id == row.id,
        ):
            raise ConflictError("product type identity is immutable once a revision exists")
    if isinstance(row, ProductType) and activating:
        inactive_template = (
            select(ProductTypeRevision.id)
            .join(
                AttributeSetRevision,
                (AttributeSetRevision.company_id == ProductTypeRevision.company_id)
                & (AttributeSetRevision.id == ProductTypeRevision.attribute_set_revision_id),
            )
            .join(
                AttributeSet,
                (AttributeSet.company_id == AttributeSetRevision.company_id)
                & (AttributeSet.id == AttributeSetRevision.attribute_set_id),
            )
            .where(
                ProductTypeRevision.company_id == row.company_id,
                ProductTypeRevision.product_type_id == row.id,
                AttributeSet.is_active.is_(False),
            )
            .limit(1)
        )
        if await db.scalar(inactive_template) is not None:
            raise ConflictError("product type references an inactive attribute template")
    if not (code_changed or deactivating):
        return
    if isinstance(row, Brand | BrandSeries | ProductType):
        product_reference = (
            ProductFamily.brand_id == row.id
            if isinstance(row, Brand)
            else ProductFamily.series_id == row.id
            if isinstance(row, BrandSeries)
            else ProductFamily.product_type_revision_id.in_(
                select(ProductTypeRevision.id).where(
                    ProductTypeRevision.company_id == row.company_id,
                    ProductTypeRevision.product_type_id == row.id,
                )
            )
        )
        if await exists(
            db, ProductFamily, ProductFamily.company_id == row.company_id, product_reference
        ):
            raise ConflictError("commercial master is referenced by a product")
    if isinstance(row, Brand):
        for model, dependency_field in (
            (Brand, Brand.parent_brand_id),
            (BrandSeries, BrandSeries.brand_id),
        ):
            criteria: list[ColumnElement[bool]] = [
                model.company_id == row.company_id,
                dependency_field == row.id,
            ]
            if deactivating and not code_changed:
                criteria.append(model.is_active.is_(True))
            if await exists(db, model, *criteria):
                raise ConflictError("brand has dependent masters")
    if isinstance(row, Manufacturer):
        site_criteria = [
            ManufacturerSite.company_id == row.company_id,
            ManufacturerSite.manufacturer_id == row.id,
        ]
        if deactivating and not code_changed:
            site_criteria.append(ManufacturerSite.is_active.is_(True))
        if await exists(db, ManufacturerSite, *site_criteria):
            raise ConflictError("manufacturer has dependent sites")
    if isinstance(row, Brand | Manufacturer):
        relation_field = (
            BrandManufacturer.brand_id
            if isinstance(row, Brand)
            else BrandManufacturer.manufacturer_id
        )
        relation_criteria = [
            BrandManufacturer.company_id == row.company_id,
            relation_field == row.id,
        ]
        if deactivating and not code_changed:
            relation_criteria.append(
                or_(BrandManufacturer.valid_to.is_(None), BrandManufacturer.valid_to >= today)
            )
        if await exists(db, BrandManufacturer, *relation_criteria):
            raise ConflictError("commercial master has production relationships")


async def validate_brands(db: AsyncSession, row: Brand) -> None:
    rows = list(
        await db.scalars(select(Brand).where(Brand.company_id == row.company_id).limit(10001))
    )
    if len(rows) > 10000:
        raise ConflictError("brand hierarchy exceeds synchronous validation bounds")
    validate_group_history(
        tuple(GroupNode(item.id, item.company_id, "BOTH") for item in rows),
        tuple(ParentInterval(item.id, item.parent_brand_id, dt.date.min, None) for item in rows),
        company_id=row.company_id,
    )

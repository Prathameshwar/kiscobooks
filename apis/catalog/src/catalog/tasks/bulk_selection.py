"""Explicit indexed filters materialize a bounded immutable ID/version selection."""

import uuid
from collections import defaultdict
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.bulk import BulkBatch, BulkRecord, BulkTarget
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models import ProductFamily
from catalog.models.pricing import ItemPriceScope, ItemPriceSeries, PricePlan
from catalog.schemas.bulk import FilterStage
from catalog.tasks.bulk_registry import operation
from catalog.tasks.field_context import load_field_context

FILTERS = {
    "product_family": frozenset({"status", "kind", "brand_id", "product_type_revision_id"}),
    "item": frozenset({"status", "kind", "family_id", "base_unit_id"}),
    "unit_of_measure": frozenset({"dimension", "is_active"}),
    "item_price": frozenset({"series_id"}),
}


async def materialize(
    db: AsyncSession, actor: Actor, company: uuid.UUID, body: FilterStage
) -> BulkBatch:
    if not body.filters and not body.all_rows:
        raise ValidationFailedError("select indexed filters or explicitly select all rows")
    if not body.filters.keys() <= FILTERS[body.resource]:
        raise ValidationFailedError("unsupported bulk selection filter")
    if "expected_version" in body.data:
        raise ValidationFailedError("filter selection captures each target's own version")
    op = operation(body.resource, body.action)
    for permission in op.permissions:
        actor.require_scope(permission, target=ScopePath(company_id=company))
    context = await load_field_context(db, actor, company, "catalog." + body.resource)
    if not set(context.native.fields) <= context.readable():
        raise PermissionDeniedError("bulk selection requires readable target fields")
    model = op.model
    stmt = select(model.id, model.row_version).where(model.company_id == company)
    for key, value in body.filters.items():
        parsed: Any = value
        if key.endswith("_id"):
            try:
                parsed = uuid.UUID(str(value))
            except ValueError as exc:
                raise ValidationFailedError("selection identifier is invalid") from exc
        elif key == "is_active" and type(value) is not bool:
            raise ValidationFailedError("is_active requires a boolean")
        if body.resource == "item" and key == "kind":
            family_context = await load_field_context(db, actor, company, "catalog.product_family")
            if "kind" not in family_context.readable():
                raise PermissionDeniedError("family kind is protected")
            stmt = stmt.join(ProductFamily, model.family_id == ProductFamily.id).where(
                ProductFamily.company_id == company, ProductFamily.kind == parsed
            )
        else:
            stmt = stmt.where(getattr(model, key) == parsed)
    if body.resource == "item_price":
        for entity in (
            "catalog.price_plan",
            "catalog.item_price_series",
            "catalog.item_price_scope",
        ):
            dependency = await load_field_context(db, actor, company, entity)
            if not set(dependency.native.fields) <= dependency.readable():
                raise PermissionDeniedError("price selection dependencies are protected")
        purchases = (
            stmt.join(ItemPriceSeries, model.series_id == ItemPriceSeries.id)
            .join(PricePlan, ItemPriceSeries.plan_id == PricePlan.id)
            .where(
                ItemPriceSeries.company_id == company,
                PricePlan.company_id == company,
                PricePlan.purpose == "PURCHASE",
            )
            .limit(1)
        )
        if (await db.execute(purchases)).first() is not None:
            for permission in ("purchase_price.read", "purchase_price.manage"):
                actor.require_scope(permission, target=ScopePath(company_id=company))
    selected = list((await db.execute(stmt.order_by(model.id).limit(2001))).all())
    if not 1 <= len(selected) <= 2000:
        raise ValidationFailedError("selection must contain 1 to 2000 targets")
    price_items: dict[uuid.UUID, uuid.UUID] = {}
    if body.resource == "item_price":
        prices = await db.execute(
            select(model.id, ItemPriceScope.item_id)
            .join(ItemPriceSeries, model.series_id == ItemPriceSeries.id)
            .join(ItemPriceScope, ItemPriceSeries.price_scope_id == ItemPriceScope.id)
            .where(
                model.company_id == company,
                ItemPriceSeries.company_id == company,
                ItemPriceScope.company_id == company,
                model.id.in_([row.id for row in selected]),
            )
        )
        price_items = dict(prices.tuples().all())
    counts: dict[str, int] = defaultdict(int)
    records = []
    for index, (key, version) in enumerate(selected, 1):
        group = "sku-" + price_items[key].hex if key in price_items else "row-" + str(index)
        counts[group] += 1
        records.append(
            BulkRecord(
                key="row-" + str(index),
                change_set=group,
                resource=body.resource,
                action=body.action,
                target=BulkTarget(id=key),
                data={**body.data, "expected_version": version},
                clear_fields=body.clear_fields,
            )
        )
    if max(counts.values()) > 100:
        raise ValidationFailedError("one SKU's selected prices exceed the atomic change-set bound")
    return BulkBatch(
        mode="UPDATE_ONLY", atomicity=body.atomicity, on_error=body.on_error, records=records
    )

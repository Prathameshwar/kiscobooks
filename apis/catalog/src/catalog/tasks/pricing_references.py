"""Dated product declarations, explicit estimates and commercial restrictions."""

import uuid

from billing_platform.errors import ConflictError, ValidationFailedError

from catalog.domain.pricing import RateGrid
from catalog.models.classification import ItemGroup
from catalog.models.pricing import (
    CommercialGuardRule,
    CommercialPolicyScope,
    DiscountCeiling,
    ItemCommercialPolicy,
    ItemMrp,
    ItemReferenceCost,
    PricingRow,
)
from catalog.models.products import ProductFamily
from catalog.schemas.pricing import (
    CommercialInput,
    CommercialScopeInput,
    CostInput,
    DiscountInput,
    GuardInput,
    MrpInput,
)
from catalog.tasks.pricing_commands import PricingWork, product, row
from catalog.tasks.pricing_dimensions import validate_dimensions
from catalog.tasks.pricing_foundation import basis, currency, numeric, unit, values
from catalog.tasks.pricing_validation import settings


async def validate_reference(work: PricingWork, body: CostInput | MrpInput | GuardInput) -> None:
    await currency(work.access, body.currency)
    item, family, config = await settings(work.access, body.item_id, body.valid_from)
    revision, binding = await unit(
        work.access, body.item_id, body.unit_revision_id, body.valid_from
    )
    await validate_dimensions(
        work.access,
        config,
        base_unit_id=item.base_unit_id,
        unit_id=binding.unit_id,
        currency=body.currency,
    )
    basis(revision, body.price_basis_quantity)
    precision = await numeric(
        work.access,
        body.numeric_revision_id,
        body.item_id,
        body.unit_revision_id,
        body.currency,
        body.valid_from,
    )
    if body.amount is not None:
        RateGrid(precision.price_decimal_places, precision.price_increment).entered(body.amount)
    if isinstance(body, MrpInput):
        if family.kind != "GOODS" or config.pricing.mrp_mode == "DISABLED":
            raise ConflictError("product MRP requires eligible goods and enabled MRP configuration")
    if isinstance(body, CostInput | GuardInput) and body.estimate_kind is not None:
        if (body.estimate_kind == "SERVICE_ESTIMATE") != (family.kind == "SERVICE"):
            raise ValidationFailedError("estimate kind does not match goods/service ownership")
    if isinstance(body, GuardInput) and not item.sellable:
        raise ConflictError("selling-price guards require a sellable SKU")


async def create_cost(
    work: PricingWork, body: CostInput, object_id: uuid.UUID | None
) -> PricingRow:
    await validate_reference(work, body)
    await work.history(
        ItemReferenceCost,
        body,
        {
            key: getattr(body, key)
            for key in ("item_id", "unit_revision_id", "currency", "estimate_kind")
        },
    )
    return await work.new(ItemReferenceCost, **values(body))


async def create_mrp(work: PricingWork, body: MrpInput, object_id: uuid.UUID | None) -> PricingRow:
    await validate_reference(work, body)
    await work.history(
        ItemMrp,
        body,
        {
            key: getattr(body, key)
            for key in ("item_id", "unit_revision_id", "currency", "jurisdiction")
        },
    )
    return await work.new(ItemMrp, **values(body))


async def create_guard(
    work: PricingWork, body: GuardInput, object_id: uuid.UUID | None
) -> PricingRow:
    await validate_reference(work, body)
    await work.history(
        CommercialGuardRule,
        body,
        {
            key: getattr(body, key)
            for key in ("item_id", "unit_revision_id", "currency", "rule_kind")
        },
    )
    return await work.new(CommercialGuardRule, **values(body))


async def scope_owner(
    work: PricingWork, owner: CommercialScopeInput | CommercialPolicyScope
) -> uuid.UUID:
    if owner.owner_kind == "GROUP":
        assert owner.group_id is not None
        await work.access.reference(ItemGroup, owner.group_id)
        return owner.group_id
    if owner.owner_kind == "FAMILY":
        assert owner.family_id is not None
        await work.access.reference(ProductFamily, owner.family_id)
        return owner.family_id
    if owner.owner_kind == "SKU":
        assert owner.item_id is not None
        await product(work.access, owner.item_id)
        return owner.item_id
    return work.company


async def create_commercial_scope(
    work: PricingWork, body: CommercialScopeInput, object_id: uuid.UUID | None
) -> PricingRow:
    owner = await scope_owner(work, body)
    return await work.new(CommercialPolicyScope, **body.model_dump(), owner_id=owner)


async def create_discount(
    work: PricingWork, body: DiscountInput, object_id: uuid.UUID | None
) -> PricingRow:
    scope = await row(work.access, CommercialPolicyScope, body.scope_id)
    await scope_owner(work, scope)
    await work.history(DiscountCeiling, body, {"scope_id": body.scope_id})
    return await work.new(DiscountCeiling, **values(body))


async def create_commercial(
    work: PricingWork, body: CommercialInput, object_id: uuid.UUID | None
) -> PricingRow:
    item, _, _ = await settings(work.access, body.item_id, body.valid_from)
    if body.free_sale_allowed and not item.sellable:
        raise ConflictError("free-sale policy requires a sellable SKU")
    await work.history(ItemCommercialPolicy, body, {"item_id": body.item_id})
    return await work.new(ItemCommercialPolicy, **values(body))

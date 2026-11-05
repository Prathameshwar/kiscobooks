"""Protected, company-owned SKU/unit/tracking/route evidence for BOM publication."""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from billing_platform.errors import (
    ConflictError,
    FeatureNotEnabledError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.exact import RationalConversion
from billing_platform.money import MoneyError
from sqlalchemy import select

from catalog.domain.bom_definitions import PhysicalQuantity
from catalog.domain.units import QuantityRule
from catalog.models.commercial import ProductTypeRevision
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.manufacturing_operations import (
    ManufacturingOperation,
    ManufacturingOperationRevision,
)
from catalog.models.manufacturing_routes import (
    ManufacturingRoute,
    ManufacturingRouteRevision,
    ManufacturingRouteStep,
)
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.products import Item, ProductFamily
from catalog.models.units import UnitOfMeasure
from catalog.schemas.boms import BomDraftInput, LineInput
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.product_requirements import configuration, product_work
from catalog.tasks.product_unit_rules import unit_revisions


@dataclass(frozen=True)
class LineDependency:
    rule: PhysicalQuantity
    unit: QuantityRule
    base_unit: QuantityRule
    evidence: dict[str, Any]

    def validate(self, quantity: Any) -> Any:
        try:
            self.unit.validate(quantity)
            base = self.rule.validate(quantity)
            self.base_unit.validate(base)
            return base
        except MoneyError as exc:
            raise ValidationFailedError("quantity does not fit its pinned unit grid") from exc


async def goods(access: ConfigurationAccess, item_id: uuid.UUID) -> tuple[Item, ProductFamily]:
    item = await access.reference(Item, item_id)
    family = await access.reference(ProductFamily, item.family_id)
    if family.kind != "GOODS" or "DISCONTINUED" in {family.status, item.status}:
        raise ConflictError("BOM physical rows require current goods SKUs")
    return item, family


async def line_dependency(
    access: ConfigurationAccess, line: LineInput, as_of: dt.date
) -> LineDependency:
    item, family = await goods(access, line.item_id)
    if line.unit_revision_id is None:
        raise ConflictError(
            "publication requires an explicit fixed SKU unit revision on every line"
        )
    revision = await access.reference(ItemUnitRevision, line.unit_revision_id)
    binding = await access.reference(ItemUnitBinding, revision.binding_id)
    if binding.item_id != item.id:
        raise PermissionDeniedError("BOM unit revision belongs to another SKU")
    if (
        revision.conversion_mode != "FIXED"
        or revision.numerator is None
        or revision.denominator is None
    ):
        raise ConflictError("BOM definitions support exact fixed units only")
    if revision.valid_from > as_of or (revision.valid_to is not None and revision.valid_to < as_of):
        raise ConflictError("BOM unit revision does not apply on its definition date")
    work = await product_work(access.db, access.actor, access.company, item.id)
    effective = await configuration(work, as_of)
    template_id = effective.profiles.inventory_template_revision_id
    if template_id is None:
        raise ConflictError("BOM physical rows require a resolved stock inventory profile")
    inventory = await access.reference(InventoryProfileTemplateRevision, template_id)
    type_revision = await access.reference(ProductTypeRevision, family.product_type_revision_id)
    if "STOCK" not in type_revision.inventory_modes:
        raise ConflictError("BOM physical rows require stock-capable product types")
    tracking = (
        "BATCH_SERIAL"
        if inventory.lot_tracking and inventory.serial_tracking
        else "BATCH"
        if inventory.lot_tracking
        else "SERIAL"
        if inventory.serial_tracking
        else "NONE"
    )
    if tracking not in type_revision.tracking_modes or (
        type_revision.require_expiry and not inventory.expiry_required
    ):
        raise ConflictError("BOM stock tracking must satisfy the SKU product type")
    required = {"inventory"}
    if inventory.lot_tracking:
        required.add("batch_tracking")
    if inventory.serial_tracking:
        required.add("serial_tracking")
    if inventory.expiry_required:
        required.add("expiry_tracking")
    features = (await access.context(Item)).features
    for missing in sorted(required - features):
        raise FeatureNotEnabledError(
            "BOM SKU tracking requires enabled company capabilities", feature=missing
        )
    base_revisions = await unit_revisions(access, item.id, as_of, base=True, effective_only=True)
    if len(base_revisions) != 1:
        raise ConflictError("BOM publication requires one effective SKU base-unit definition")
    base_revision = base_revisions[0]
    base_binding = await access.reference(ItemUnitBinding, base_revision.binding_id)
    if (
        base_binding.unit_id != item.base_unit_id
        or base_revision.conversion_mode != "FIXED"
        or base_revision.numerator != base_revision.denominator
    ):
        raise ConflictError("BOM base-unit definition must be an exact identity conversion")
    unit = await access.reference(UnitOfMeasure, binding.unit_id)
    base = await access.reference(UnitOfMeasure, item.base_unit_id)
    if unit.dimension != base.dimension:
        raise ConflictError("BOM units must share the SKU base dimension")
    if base.dimension not in type_revision.unit_dimensions:
        raise ConflictError("BOM base unit must satisfy the SKU product type")
    if inventory.serial_tracking and (
        base.dimension != "COUNT"
        or base.decimal_places != 0
        or base_revision.quantity_decimal_places != 0
    ):
        raise ConflictError("serialized BOM stock requires whole-count base-unit definitions")
    rule = PhysicalQuantity(
        item.id,
        QuantityRule(revision.quantity_decimal_places, revision.quantity_increment),
        QuantityRule(base_revision.quantity_decimal_places, base_revision.quantity_increment),
        RationalConversion(revision.numerator, revision.denominator),
        inventory.serial_tracking,
        revision.fractional_entry,
    )
    return LineDependency(
        rule,
        QuantityRule(unit.decimal_places, unit.quantity_increment),
        QuantityRule(base.decimal_places, base.quantity_increment),
        {
            "item_id": str(item.id),
            "item_version": item.row_version,
            "unit_revision_id": str(revision.id),
            "base_unit_revision_id": str(base_revision.id),
            "inventory_template_revision_id": str(inventory.id),
            "serial_tracking": inventory.serial_tracking,
            "lot_tracking": inventory.lot_tracking,
            "expiry_required": inventory.expiry_required,
            "numerator": revision.numerator,
            "denominator": revision.denominator,
            "quantity_decimal_places": revision.quantity_decimal_places,
            "quantity_increment": str(revision.quantity_increment),
            "fractional_entry": revision.fractional_entry,
            "base_decimal_places": base_revision.quantity_decimal_places,
            "base_increment": str(base_revision.quantity_increment),
        },
    )


async def route_dependency(
    access: ConfigurationAccess, definition: BomDraftInput
) -> dict[str, Any] | None:
    if definition.route_revision_id is None:
        return None
    route = await access.reference(ManufacturingRouteRevision, definition.route_revision_id)
    await access.reference(ManufacturingRoute, route.route_id)
    if route.status != "PUBLISHED":
        raise ConflictError("BOM requires a published, nonretired manufacturing route")
    context = await access.context(ManufacturingRouteStep)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("BOM route steps require readable native fields")
    rows = list(
        await access.db.scalars(
            select(ManufacturingRouteStep)
            .where(
                ManufacturingRouteStep.company_id == access.company,
                ManufacturingRouteStep.revision_id == route.id,
            )
            .order_by(ManufacturingRouteStep.sequence)
            .limit(51)
        )
    )
    if len(rows) != route.step_count or not 1 <= len(rows) <= 50:
        raise ConflictError("BOM route step evidence is incomplete")
    evidence = []
    for row in rows:
        await access.require(row)
        operation = await access.reference(
            ManufacturingOperationRevision, row.operation_revision_id
        )
        await access.reference(ManufacturingOperation, operation.operation_id)
        if operation.status != "PUBLISHED":
            raise ConflictError("BOM route references an unavailable operation revision")
        evidence.append({"step_id": str(row.id), "operation_revision_id": str(operation.id)})
    allowed = {row.id for row in rows}
    if any(
        row.route_step_id is not None and row.route_step_id not in allowed
        for row in definition.components
    ):
        raise PermissionDeniedError("BOM component step belongs to another route revision")
    return {"revision_id": str(route.id), "steps": evidence}

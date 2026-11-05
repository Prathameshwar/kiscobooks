"""Protected definition completeness and independently pinned configuration selection."""

import datetime as dt
import uuid
from fractions import Fraction
from typing import Any, Literal, cast

from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.gateway import Actor
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.units import QuantityRule, validate_serial_rule
from catalog.models.commercial import ProductTypeRevision
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.product_definitions import (
    FamilyGroupAssignment,
    FamilyManufacturer,
    ItemBarcode,
    ItemUnitBinding,
    ItemUnitRevision,
    ProductConfigurationAdoption,
    ProductConfigurationAdoptionSource,
)
from catalog.models.products import Item, ProductFamily
from catalog.models.units import UnitOfMeasure
from catalog.schemas.configuration import EffectiveConfiguration, EffectiveQuery
from catalog.schemas.product_authoring import ProductRequirements
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_context import family_group
from catalog.tasks.configuration_resolution import resolve
from catalog.tasks.product_attributes import bounded
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.unit_consistency import validate_fixed_ratio, validate_measured_relation


async def product_work(
    db: AsyncSession, actor: Actor, company: uuid.UUID, item_id: uuid.UUID
) -> ProductWork:
    access = ConfigurationAccess(db, actor, company)
    item = await access.reference(Item, item_id)
    family = await access.reference(ProductFamily, item.family_id)
    return ProductWork(db, actor, company, family, item, access)


async def group_on(work: ProductWork, as_of: dt.date) -> FamilyGroupAssignment | None:
    return await family_group(work.access, work.family.id, as_of)


async def pinned(
    work: ProductWork, as_of: dt.date
) -> tuple[ProductConfigurationAdoption | None, tuple[uuid.UUID, ...]]:
    assert work.item is not None
    context = await work.access.context(ProductConfigurationAdoption)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("configuration adoption history is protected")
    adoption = await work.db.scalar(
        select(ProductConfigurationAdoption)
        .where(
            ProductConfigurationAdoption.company_id == work.company,
            ProductConfigurationAdoption.item_id == work.item.id,
            ProductConfigurationAdoption.effective_on <= as_of,
        )
        .order_by(
            ProductConfigurationAdoption.effective_on.desc(),
            ProductConfigurationAdoption.revision.desc(),
        )
        .limit(1)
    )
    if adoption is None:
        return None, ()
    sources = await bounded(
        work, ProductConfigurationAdoptionSource, "adoption_id", adoption.id, 16
    )
    return adoption, tuple(row.revision_id for row in sources)


async def configuration(
    work: ProductWork,
    as_of: dt.date,
    *,
    proposed: bool = False,
    query: EffectiveQuery | None = None,
) -> EffectiveConfiguration:
    assert work.item is not None
    group = await group_on(work, as_of)
    adoption, ids = await pinned(work, as_of)
    if not proposed and adoption is not None:
        if adoption.product_type_revision_id != work.family.product_type_revision_id:
            raise ConflictError("pinned type configuration differs from product structure")
        if adoption.group_assignment_id != (group.id if group else None):
            raise ConflictError("group reassignment requires explicit configuration adoption")
    query = query or EffectiveQuery(
        as_of=as_of,
        kind=cast(Literal["GOODS", "SERVICE"], work.family.kind),
        family_id=work.family.id,
        item_id=work.item.id,
        group_id=group.group_id if group else None,
    )
    return await resolve(
        work.db,
        work.actor,
        work.company,
        query,
        revisions=ids if adoption is not None and not proposed else None,
        resolution_version=adoption.resolution_version
        if adoption is not None and not proposed
        else 2,
    )


async def current_rows(
    work: ProductWork,
    model: type[Any],
    owner_field: str,
    owner_id: uuid.UUID,
    as_of: dt.date,
    *,
    limit: int,
) -> list[Any]:
    """Probe effective definitions without capping retained historical rows."""
    context = await work.access.context(model)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("product definition dependencies require readable fields")
    statement = select(model).where(
        model.company_id == work.company,
        getattr(model, owner_field) == owner_id,
    )
    if model is ItemBarcode:
        statement = statement.where(ItemBarcode.is_active.is_(True))
    else:
        statement = statement.where(
            model.valid_from <= as_of,
            or_(model.valid_to.is_(None), model.valid_to >= as_of),
        )
    rows = list(await work.db.scalars(statement.order_by(model.id).limit(limit)))
    for row in rows:
        await work.access.require(row)
    return rows


async def requirements(
    work: ProductWork, as_of: dt.date, *, proposed: bool = False
) -> tuple[ProductRequirements, EffectiveConfiguration]:
    assert work.item is not None
    effective = await configuration(work, as_of, proposed=proposed)
    missing = []
    if await group_on(work, as_of) is None:
        missing.append("primary_group")
    from catalog.tasks.category_membership import effective as category_memberships

    categories, _, category_missing = await category_memberships(work.access, work.family.id, as_of)
    missing.extend(category_missing)
    active_manufacturers = await current_rows(
        work, FamilyManufacturer, "family_id", work.family.id, as_of, limit=1
    )
    barcodes = await current_rows(work, ItemBarcode, "item_id", work.item.id, as_of, limit=1)
    bindings = await bounded(work, ItemUnitBinding, "item_id", work.item.id, 64)
    effective_bindings = []
    for binding in bindings:
        active = await current_rows(
            work, ItemUnitRevision, "binding_id", binding.id, as_of, limit=2
        )
        if len(active) > 1:
            raise ConflictError("unit binding has ambiguous effective revisions")
        if active:
            revision = active[0]
            if revision.conversion_mode == "FIXED":
                await validate_fixed_ratio(
                    work.access,
                    binding.unit_id,
                    work.item.base_unit_id,
                    Fraction(revision.numerator, revision.denominator),
                )
            else:
                await validate_measured_relation(
                    work.access, binding.unit_id, work.item.base_unit_id
                )
            effective_bindings.append(binding)
    available = {
        "variants": work.family.structure_mode == "VARIANT",
        "brand": work.family.brand_id is not None,
        "model": bool(work.family.model_code and work.family.model_code.strip()),
        "category": bool(categories),
        "manufacturer": bool(active_manufacturers),
        "barcode": any(row.is_active for row in barcodes),
        "alternate_units": any(
            row.unit_id != work.item.base_unit_id or row.usage_role == "PACK"
            for row in effective_bindings
        ),
        "compound_units": len(effective_bindings) > 1,
        "measured_units": any(row.usage_role == "MEASURED" for row in effective_bindings),
    }
    for field, present in available.items():
        mode = getattr(effective.options, field + "_mode")
        if mode == "REQUIRED" and not present:
            missing.append(field)
        # Having several unit choices is not itself a compound quantity entry.
        # DISABLED is enforced against submitted components by quantity preview.
        if mode == "DISABLED" and present and field != "compound_units":
            missing.append("forbidden_" + field)
    if not any(row.usage_role == "BASE" for row in effective_bindings):
        missing.append("base_unit_binding")
    from catalog.tasks.product_attributes import stored_requirements

    missing.extend(await stored_requirements(work))
    type_revision = await work.access.reference(
        ProductTypeRevision, work.family.product_type_revision_id
    )
    if work.family.kind == "GOODS" and (
        type_revision.require_expiry or type_revision.inventory_modes == ["STOCK"]
    ):
        if effective.profiles.inventory_template_revision_id is None:
            missing.append("inventory_profile")
    inventory_id = effective.profiles.inventory_template_revision_id
    if effective.profiles.identifier_profile_id is not None and inventory_id is None:
        missing.append("inventory_profile")
    if inventory_id is not None:
        inventory = await work.access.reference(InventoryProfileTemplateRevision, inventory_id)
        if effective.profiles.identifier_profile_id not in {None, inventory.identifier_profile_id}:
            raise ConflictError("identifier selection differs from the inventory profile")
        if inventory.serial_tracking and "base_unit_binding" not in missing:
            from catalog.tasks.product_unit_rules import unit_revisions

            base = await work.access.reference(UnitOfMeasure, work.item.base_unit_id)
            revisions = await unit_revisions(work.access, work.item.id, as_of, base=True)
            try:
                for revision in revisions:
                    validate_serial_rule(
                        base.dimension,
                        QuantityRule(revision.quantity_decimal_places, revision.quantity_increment),
                    )
            except ValidationFailedError:
                missing.append("integer_serial_base_quantity")
    return ProductRequirements(
        family_id=work.family.id,
        item_id=work.item.id,
        family_version=work.family.row_version,
        item_version=work.item.row_version,
        as_of=as_of,
        missing=sorted(set(missing)),
        product_definition_complete=not missing,
        policy_generation=effective.policy_generation,
    ), effective

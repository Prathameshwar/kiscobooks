"""Load a bounded form graph without a detail request for every selected value."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.field_policy import resolve_field_effect
from billing_platform.gateway import Actor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models import (
    AttributeDefinition,
    AttributeOption,
    FamilyAttribute,
    FamilyAttributeOption,
    Item,
    ItemAttributeValue,
    ProductFamily,
    UnitOfMeasure,
)
from catalog.schemas.attribute_forms import (
    AttributeFormField,
    AttributeFormOption,
    ProductAttributeForm,
)
from catalog.schemas.product_authoring import AttributeSelection
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.product_attributes import bounded
from catalog.tasks.product_commands import ProductWork


async def reference_rows(
    access: ConfigurationAccess, model: type[Any], ids: set[uuid.UUID]
) -> dict[uuid.UUID, Any]:
    if not ids:
        return {}
    context = await access.context(model)
    if not set(context.native.fields) <= context.readable():
        raise PermissionDeniedError("attribute form references require readable fields")
    rows = list(
        await access.db.scalars(
            select(model).where(model.company_id == access.company, model.id.in_(ids))
        )
    )
    if len(rows) != len(ids):
        raise ConflictError("attribute form references are unavailable")
    for row in rows:
        await access.require(row)
    return {row.id: row for row in rows}


async def form(
    db: AsyncSession, actor: Actor, company: uuid.UUID, item_id: uuid.UUID
) -> ProductAttributeForm:
    access = ConfigurationAccess(db, actor, company)
    item = await access.reference(Item, item_id)
    family = await access.reference(ProductFamily, item.family_id)
    work = ProductWork(db, actor, company, family, item, access)
    declarations = await bounded(work, FamilyAttribute, "family_id", family.id)
    selections = await bounded(work, FamilyAttributeOption, "family_id", family.id, 1024)
    values = await bounded(work, ItemAttributeValue, "item_id", item.id)
    by_definition = {row.definition_id: row for row in values}
    if not set(by_definition) <= {row.definition_id for row in declarations}:
        raise ConflictError("stored attributes must be reconciled with their family declarations")
    definitions = await reference_rows(
        access, AttributeDefinition, {row.definition_id for row in declarations}
    )
    options = await reference_rows(
        access,
        AttributeOption,
        {row.option_id for row in selections} | {row.option_id for row in values if row.option_id},
    )
    units = await reference_rows(
        access, UnitOfMeasure, {row.unit_id for row in values if row.unit_id} | {item.base_unit_id}
    )
    default = await db.scalar(
        select(Item).where(
            Item.company_id == company, Item.family_id == family.id, Item.default_slot == 1
        )
    )
    if default is None:
        raise ConflictError("family default SKU is unavailable")
    await access.require(default)
    context = await access.context(ItemAttributeValue)
    permission = actor.allows_scope("item.update", target=ScopePath(company_id=company))
    variant_writable = (
        permission
        and family.status in {"DRAFT", "ACTIVE"}
        and all(
            resolve_field_effect(
                context.rules(), field_key=key, access="write", target=ScopePath(company_id=company)
            )
            != "deny"
            for key in context.native.fields
        )
    )
    writable = variant_writable and item.status == "DRAFT"
    # Ordinary specifications remain writable independently of variant authoring.
    from catalog.tasks.product_mode import enabled

    variant_writable = variant_writable and await enabled(db, company)
    can_configure = permission and family.status in {"DRAFT", "ACTIVE"}
    for model in (FamilyAttribute, FamilyAttributeOption):
        declaration_context = await access.context(model)
        can_configure &= all(
            resolve_field_effect(
                declaration_context.rules(),
                field_key=key,
                access="write",
                target=ScopePath(company_id=company),
            )
            != "deny"
            for key in declaration_context.native.fields
        )
    fields = []
    for declaration in sorted(declarations, key=lambda row: (row.position, row.id)):
        definition = definitions[declaration.definition_id]
        stored = by_definition.get(declaration.definition_id)
        value = (
            AttributeSelection.model_validate(
                {key: getattr(stored, key) for key in AttributeSelection.model_fields}
            )
            if stored
            else None
        )
        fields.append(
            AttributeFormField(
                definition_id=definition.id,
                label=definition.name,
                value_type=definition.value_type,
                measurement_dimension=definition.measurement_dimension,
                is_variant_capable=definition.is_variant_capable,
                is_active=definition.is_active,
                is_axis=declaration.is_axis,
                is_required=declaration.is_required,
                position=declaration.position,
                allowed_options=[
                    AttributeFormOption(
                        id=selection.option_id,
                        label=options[selection.option_id].name,
                        is_active=options[selection.option_id].is_active,
                    )
                    for selection in selections
                    if selection.definition_id == definition.id
                ],
                value=value,
                option_label=options[value.option_id].name if value and value.option_id else None,
                unit_label=units[value.unit_id].name if value and value.unit_id else None,
                writable=writable,
                variant_writable=variant_writable,
            )
        )
    return ProductAttributeForm(
        item_id=item.id,
        item_version=item.row_version,
        item_name=item.name,
        item_status=item.status,
        family_id=family.id,
        family_version=family.row_version,
        family_name=family.name,
        family_status=family.status,
        default_item_id=default.id,
        structure_mode=family.structure_mode,
        base_unit_id=item.base_unit_id,
        base_unit_label=units[item.base_unit_id].name,
        can_configure=can_configure,
        can_create_variant=variant_writable
        and actor.allows_scope("item.create", target=ScopePath(company_id=company))
        and family.status in {"DRAFT", "ACTIVE"}
        and family.structure_mode == "VARIANT",
        fields=fields,
    )

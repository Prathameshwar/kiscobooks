"""Native family attributes, explicit SKU values and canonical variant identities."""

import uuid
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.money import MoneyError
from sqlalchemy import or_, select

from catalog.domain.attributes import AttributeValue, DefinitionRules
from catalog.domain.product_authoring import variant_identity
from catalog.domain.units import QuantityRule
from catalog.models.attributes import AttributeDefinition, AttributeOption, AttributeSetMember
from catalog.models.commercial import ProductTypeRevision
from catalog.models.product_definitions import (
    FamilyAttribute,
    FamilyAttributeOption,
    ItemAttributeValue,
    ItemVariantKey,
)
from catalog.models.products import Item
from catalog.models.units import UnitOfMeasure
from catalog.schemas.attributes import VALUE_FIELDS
from catalog.schemas.product_authoring import (
    AttributeAssignmentInput,
    AttributeSelection,
    FamilyAttributesInput,
    VariantInput,
)
from catalog.tasks.classification import validate_custom
from catalog.tasks.custom_fields import reserve_claims
from catalog.tasks.field_indexes import index_values
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.products import native, references


async def bounded(
    work: ProductWork, model: type[Any], field: str, value: uuid.UUID, limit: int = 128
) -> list[Any]:
    context = await work.access.context(model)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("product definition dependencies require readable fields")
    rows = list(
        await work.db.scalars(
            select(model)
            .where(model.company_id == work.company, getattr(model, field) == value)
            .order_by(model.id)
            .limit(limit + 1)
        )
    )
    if len(rows) > limit:
        raise ConflictError("product definition exceeds its bounded authoring contract")
    for row in rows:
        await work.access.require(row)
    return rows


async def validate_selection(
    work: ProductWork,
    entry: AttributeSelection,
    declarations: dict[uuid.UUID, FamilyAttribute],
    allowed: list[FamilyAttributeOption],
) -> uuid.UUID | None:
    declaration = declarations.get(entry.definition_id)
    if declaration is None:
        raise ValidationFailedError("SKU attribute is not declared by its family")
    definition = await work.access.reference(AttributeDefinition, entry.definition_id)
    if entry.value_type != definition.value_type:
        raise ValidationFailedError("SKU value type differs from its definition")
    present = [key for key in VALUE_FIELDS.values() if getattr(entry, key) is not None]
    permitted = {opt.option_id for opt in allowed if opt.definition_id == entry.definition_id}
    if entry.option_id is not None:
        if present or entry.unit_id is not None:
            raise ValidationFailedError(
                "option and scalar attribute representations cannot be mixed"
            )
        option = await work.access.reference(AttributeOption, entry.option_id)
        if option.definition_id != entry.definition_id:
            raise PermissionDeniedError("attribute option belongs to another definition")
        if option.value_type != definition.value_type:
            raise ValidationFailedError("attribute option type differs from its definition")
        if permitted and option.id not in permitted:
            raise ValidationFailedError("attribute option is not permitted by the family")
        return option.id if declaration.is_axis else None
    if permitted:
        raise ValidationFailedError("family allowed options require an option selection")
    if declaration.is_axis or present != [VALUE_FIELDS[entry.value_type]]:
        raise ValidationFailedError(
            "axis values need an option; scalar values need one typed field"
        )
    typed = AttributeValue(
        entry.value_type, getattr(entry, VALUE_FIELDS[entry.value_type]), entry.unit_id
    )
    typed.validate_definition(
        DefinitionRules(
            definition.value_type, definition.measurement_dimension, definition.is_variant_capable
        )
    )
    if entry.unit_id is not None:
        unit = await work.access.reference(UnitOfMeasure, entry.unit_id)
        if unit.dimension != definition.measurement_dimension:
            raise ValidationFailedError("attribute unit dimension differs from its definition")
        try:
            QuantityRule(unit.decimal_places, unit.quantity_increment).validate(typed.value)
        except MoneyError as exc:
            raise ValidationFailedError("attribute value violates its unit quantity grid") from exc
    return None


async def selections(
    work: ProductWork,
    item: Item,
    incoming: list[AttributeSelection],
    *,
    family_rows: list[FamilyAttribute] | None = None,
    family_options: list[FamilyAttributeOption] | None = None,
) -> None:
    if len({value.definition_id for value in incoming}) != len(incoming):
        raise ValidationFailedError("SKU attributes must have distinct definitions")
    declared = (
        family_rows
        if family_rows is not None
        else await bounded(work, FamilyAttribute, "family_id", work.family.id)
    )
    allowed = (
        family_options
        if family_options is not None
        else await bounded(work, FamilyAttributeOption, "family_id", work.family.id, 1024)
    )
    definitions = {row.definition_id: row for row in declared}
    axes = {
        row.definition_id: frozenset(
            opt.option_id for opt in allowed if opt.definition_id == row.definition_id
        )
        for row in declared
        if row.is_axis
    }
    selected = {}
    for entry in incoming:
        option = await validate_selection(work, entry, definitions, allowed)
        if option is not None:
            selected[entry.definition_id] = option
    old_values = await bounded(work, ItemAttributeValue, "item_id", item.id)
    old_keys = await bounded(work, ItemVariantKey, "item_id", item.id, 1)
    if axes:
        digest, canonical = variant_identity(axes, selected)
        existing = await work.db.scalar(
            select(ItemVariantKey).where(
                ItemVariantKey.company_id == work.company,
                ItemVariantKey.family_id == work.family.id,
                ItemVariantKey.combination_hash == digest,
                ItemVariantKey.item_id != item.id,
            )
        )
        if existing is not None:
            raise ConflictError(
                "variant combination already exists"
                if existing.canonical_combination == canonical
                else "variant identity hash collision"
            )
        if old_keys:
            key_row = old_keys[0]
            if key_row.combination_hash != digest or key_row.canonical_combination != canonical:
                before = await work.access.values(key_row)
                key_row.combination_hash, key_row.canonical_combination = digest, canonical
                await touch_value(work, key_row, before)
        else:
            work.db.add(
                await work.new(
                    ItemVariantKey,
                    family_id=work.family.id,
                    item_id=item.id,
                    combination_hash=digest,
                    canonical_combination=canonical,
                )
            )
    else:
        for row in old_keys:
            await work.retire_draft(row)
    previous = {row.definition_id: row for row in old_values}
    for entry in incoming:
        values = entry.model_dump()
        old = previous.pop(entry.definition_id, None)
        if old is None:
            work.db.add(await work.new(ItemAttributeValue, item_id=item.id, **values))
        elif any(getattr(old, key) != value for key, value in values.items()):
            before = await work.access.values(old)
            for key, value in values.items():
                setattr(old, key, value)
            await touch_value(work, old, before)
    for row in previous.values():
        await work.retire_draft(row)


async def touch_value(work: ProductWork, row: Any, before: dict[str, Any]) -> None:
    if row.row_version >= 2**31 - 1:
        raise ConflictError("attribute value version exhausted")
    row.row_version += 1
    row.updated_at, row.updated_by = utcnow(), work.actor.user_id
    await work.record(row, before, "update")


async def stored_requirements(work: ProductWork) -> list[str]:
    """Revalidate saved native values without writing or allocating any identities."""
    from billing_platform.errors import NotFoundError
    from pydantic import ValidationError

    assert work.item is not None
    declarations = await bounded(work, FamilyAttribute, "family_id", work.family.id)
    allowed = await bounded(work, FamilyAttributeOption, "family_id", work.family.id, 1024)
    saved = await bounded(work, ItemAttributeValue, "item_id", work.item.id)
    by_id = {row.definition_id: row for row in declarations}
    supplied = {row.definition_id for row in saved}
    missing = {
        row.definition_id
        for row in declarations
        if row.is_required and row.definition_id not in supplied
    }
    revision = await work.access.reference(
        ProductTypeRevision, work.family.product_type_revision_id
    )
    members = (
        await bounded(work, AttributeSetMember, "revision_id", revision.attribute_set_revision_id)
        if revision.attribute_set_revision_id
        else []
    )
    template = {row.definition_id: row for row in members}
    missing.update(
        row.definition_id
        for row in members
        if row.is_required and row.definition_id not in supplied
    )
    for declaration in declarations:
        if revision.attribute_set_revision_id and (
            declaration.definition_id not in template
            or (declaration.is_axis and not template[declaration.definition_id].allow_variant_axis)
        ):
            missing.add(declaration.definition_id)
    for row in saved:
        try:
            value = AttributeSelection.model_validate(
                {key: getattr(row, key) for key in AttributeSelection.model_fields}
            )
            await validate_selection(work, value, by_id, allowed)
        except (ValidationFailedError, ValidationError, ConflictError, NotFoundError):
            missing.add(row.definition_id)
    return ["attribute:" + str(key) for key in sorted(missing)]


async def configure_family(work: ProductWork, body: FamilyAttributesInput) -> None:
    entries = body.attributes
    if len({row.definition_id for row in entries}) != len(entries) or len(
        {row.position for row in entries}
    ) != len(entries):
        raise ValidationFailedError("family attribute definitions and positions must be unique")
    if sum(len(row.options) for row in entries) > 1024:
        raise ValidationFailedError("family attribute option bound is 1024 selections")
    revision = await work.access.reference(
        ProductTypeRevision, work.family.product_type_revision_id
    )
    axes = [row for row in entries if row.is_axis]
    if len(axes) > 8 or (axes and not revision.allow_variants):
        raise ValidationFailedError(
            "product type or family axis bound forbids this variant structure"
        )
    if axes:
        from catalog.tasks.product_choices import require_choice

        await require_choice(work, "variants")
    current = await bounded(work, FamilyAttribute, "family_id", work.family.id)
    value_context = await work.access.context(ItemAttributeValue)
    if set(value_context.native.fields) - value_context.readable():
        raise PermissionDeniedError("existing SKU attribute values are protected")
    used = (
        select(ItemAttributeValue.id)
        .join(
            Item,
            (Item.tenant_id == ItemAttributeValue.tenant_id)
            & (Item.company_id == ItemAttributeValue.company_id)
            & (Item.id == ItemAttributeValue.item_id),
        )
        .where(ItemAttributeValue.company_id == work.company, Item.family_id == work.family.id)
    )
    removed = {row.definition_id for row in current} - {row.definition_id for row in entries}
    if (
        removed
        and await work.db.scalar(used.where(ItemAttributeValue.definition_id.in_(removed)).limit(1))
        is not None
    ):
        raise ConflictError("clear SKU values explicitly before removing their family declarations")
    for entry in entries:
        # An allowlist must keep permitting what SKUs already selected. Declaring no options is
        # "no option restriction" only while no SKU holds one: an empty list under an existing
        # selection strands it, so that is the same conflict and not a shape complaint later.
        stranded = (
            or_(
                ItemAttributeValue.option_id.is_(None),
                ItemAttributeValue.option_id.not_in(entry.options),
            )
            if entry.options
            else ItemAttributeValue.option_id.is_not(None)
        )
        conflict = used.where(ItemAttributeValue.definition_id == entry.definition_id, stranded)
        if await work.db.scalar(conflict.limit(1)) is not None:
            raise ConflictError("existing SKU selections must remain permitted by the family")
    old_options = await bounded(work, FamilyAttributeOption, "family_id", work.family.id, 1024)
    variant = await work.db.scalar(
        select(ItemVariantKey.id)
        .where(
            ItemVariantKey.company_id == work.company, ItemVariantKey.family_id == work.family.id
        )
        .limit(1)
    )
    if variant is not None:
        existing_axes = {
            row.definition_id: frozenset(
                opt.option_id for opt in old_options if opt.definition_id == row.definition_id
            )
            for row in current
            if row.is_axis
        }
        requested_axes = {row.definition_id: frozenset(row.options) for row in axes}
        if existing_axes.keys() != requested_axes.keys():
            raise ConflictError("existing SKU combinations require stable family axes")
    members = []
    if revision.attribute_set_revision_id is not None:
        members = await bounded(
            work, AttributeSetMember, "revision_id", revision.attribute_set_revision_id
        )
        required = {row.definition_id for row in members if row.is_required}
        if not required <= {row.definition_id for row in entries if row.is_required}:
            raise ValidationFailedError("family cannot omit required product-type attributes")
    member_by_id = {row.definition_id: row for row in members}
    if work.family.status == "ACTIVE":
        previous = {row.definition_id: row for row in current}
        old_pairs = {(row.definition_id, row.option_id) for row in old_options}
        new_pairs = {(entry.definition_id, option) for entry in entries for option in entry.options}
        if (
            set(previous) != {entry.definition_id for entry in entries}
            or not old_pairs <= new_pairs
            or "default_item_attributes" in body.model_fields_set
        ):
            raise ConflictError("active family attributes allow only additional options")
        for entry in entries:
            old = previous[entry.definition_id]
            if any(
                getattr(old, key) != getattr(entry, key)
                for key in ("is_axis", "is_required", "position")
            ):
                raise ConflictError("active family attribute declarations are immutable")
            await work.access.reference(AttributeDefinition, entry.definition_id)
            if len(set(entry.options)) != len(entry.options):
                raise ValidationFailedError("family attribute options must be distinct")
            for option_id in entry.options:
                if (entry.definition_id, option_id) in old_pairs:
                    continue
                option = await work.access.reference(AttributeOption, option_id)
                if option.definition_id != entry.definition_id:
                    raise PermissionDeniedError("family option belongs to another attribute")
                work.db.add(
                    await work.new(
                        FamilyAttributeOption,
                        family_id=work.family.id,
                        definition_id=entry.definition_id,
                        option_id=option_id,
                    )
                )
        return
    new_attributes = []
    new_options = []
    for entry in entries:
        row = await work.new(
            FamilyAttribute, family_id=work.family.id, **entry.model_dump(exclude={"options"})
        )
        definition = await work.access.reference(AttributeDefinition, entry.definition_id)
        member = member_by_id.get(entry.definition_id)
        if revision.attribute_set_revision_id is not None and (
            member is None or (entry.is_axis and not member.allow_variant_axis)
        ):
            raise ValidationFailedError("family attributes exceed the pinned product-type template")
        if entry.is_axis and (
            not entry.is_required or not definition.is_variant_capable or not entry.options
        ):
            raise ValidationFailedError(
                "variant axes require eligible required definitions and options"
            )
        if len(set(entry.options)) != len(entry.options):
            raise ValidationFailedError("family attribute options must be distinct")
        new_attributes.append(row)
        for option_id in entry.options:
            selected = await work.new(
                FamilyAttributeOption,
                family_id=work.family.id,
                definition_id=entry.definition_id,
                option_id=option_id,
            )
            option = await work.access.reference(AttributeOption, option_id)
            if option.definition_id != entry.definition_id:
                raise PermissionDeniedError("family option belongs to another attribute")
            new_options.append(selected)
    default = await work.db.scalar(
        select(Item).where(
            Item.company_id == work.company,
            Item.family_id == work.family.id,
            Item.default_slot == 1,
        )
    )
    if default is None:
        raise ConflictError("family has no default SKU")
    await work.access.require(default)
    replace_default = "default_item_attributes" in body.model_fields_set
    if axes and variant is None and not replace_default:
        raise ValidationFailedError("declare the default SKU combination with its expected version")
    if replace_default:
        if default.status != "DRAFT":
            raise ConflictError("active default SKU attribute values are immutable")
        if body.expected_default_item_version is None:
            raise ValidationFailedError(
                "default SKU attribute replacement requires its expected version"
            )
        if default.row_version != body.expected_default_item_version:
            raise ConflictError("default SKU version changed; reload before editing")
        before = await work.access.values(default)
        if default.row_version >= 2**31 - 1:
            raise ConflictError("default SKU version exhausted")
        default.row_version += 1
        default.updated_at, default.updated_by = utcnow(), work.actor.user_id
        await work.record(default, before, "update")
        await selections(
            work,
            default,
            body.default_item_attributes,
            family_rows=new_attributes,
            family_options=new_options,
        )
    before = await work.access.values(work.family)
    work.family.structure_mode = "VARIANT" if axes else "SIMPLE"
    await work.record(work.family, before, "update")
    for row in old_options:
        await work.retire_draft(row)
    await work.db.flush()
    for row in current:
        await work.retire_draft(row)
    await work.db.flush()
    work.db.add_all(new_attributes)
    await work.db.flush()
    work.db.add_all(new_options)
    work.item = default


async def assign_values(work: ProductWork, body: AttributeAssignmentInput) -> None:
    assert work.item is not None
    await selections(work, work.item, body.attributes)


async def create_variant(work: ProductWork, body: VariantInput) -> None:
    work.actor.require_scope("item.create", target=ScopePath(company_id=work.company))
    if work.family.structure_mode != "VARIANT":
        raise ConflictError("declare family axes and the default SKU combination first")
    from catalog.tasks.product_choices import require_choice

    await require_choice(work, "variants")
    from billing_platform.ids import uuid7

    sku = Item(
        id=uuid7(),
        tenant_id=work.actor.tenant_id,
        company_id=work.company,
        created_by=work.actor.user_id,
        updated_by=work.actor.user_id,
        row_version=1,
        family_id=work.family.id,
        default_slot=None,
        status="DRAFT",
        **body.item.model_dump(exclude={"custom_fields"}),
    )
    context = await work.access.context(Item)
    values = native(sku, context)
    sku.custom_fields = await validate_custom(
        work.db,
        work.actor,
        work.company,
        context,
        body.item.custom_fields,
        {},
        values,
        {},
        creating=True,
    )
    values = native(sku, context)
    from catalog.tasks.field_context import FieldWriteChecks

    context.assert_writable(
        frozenset(values),
        before={},
        after=values,
        checked=work.access.checks.setdefault("catalog.item", FieldWriteChecks()),
    )
    work.changed.setdefault("catalog.item", set()).update(values)
    await references(work.db, work.actor, work.company, work.family, sku)
    await work.record(sku, {})
    await reserve_claims(
        work.db,
        company_id=work.company,
        entity_type="catalog.item",
        entity_id=sku.id,
        definitions=context.definitions,
        values=sku.custom_fields or {},
    )
    await index_values(work.db, context, sku.id, sku.custom_fields or {})
    work.db.add(sku)
    await work.db.flush([sku])
    await selections(work, sku, body.attributes)
    work.item = sku

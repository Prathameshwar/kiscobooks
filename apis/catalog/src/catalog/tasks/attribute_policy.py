"""Native attribute reference, equality and lifecycle checks under the company lock."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from billing_platform.db.access import company_object
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.exact import RationalConversion
from billing_platform.money import MoneyError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.attributes import AttributeValue, DefinitionRules
from catalog.domain.units import QuantityRule
from catalog.models.attributes import (
    AttributeDefinition,
    AttributeOption,
    AttributeSet,
    AttributeSetMember,
    AttributeSetRevision,
)
from catalog.models.classification import ClassificationMaster
from catalog.models.commercial import ProductType, ProductTypeRevision
from catalog.models.units import UnitConversion, UnitOfMeasure
from catalog.schemas.attributes import VALUE_FIELDS


def definition_rules(row: AttributeDefinition) -> DefinitionRules:
    return DefinitionRules(
        row.value_type, row.measurement_dimension, row.is_variant_capable, row.is_active
    )


async def validate_attributes(
    db: AsyncSession, row: ClassificationMaster, before: Mapping[str, Any]
) -> None:
    creating = not before
    activating = row.is_active and not before.get("is_active", False)
    if isinstance(row, AttributeDefinition):
        definition_rules(row)
        identity_changed = not creating and any(
            getattr(row, field) != before[field]
            for field in ("code", "value_type", "measurement_dimension")
        )
        if identity_changed:
            for model in (AttributeOption, AttributeSetMember):
                if (
                    await db.scalar(
                        select(model.id)
                        .where(model.company_id == row.company_id, model.definition_id == row.id)
                        .limit(1)
                    )
                    is not None
                ):
                    raise ConflictError("referenced attribute definition identity is immutable")
        if not creating and before["is_variant_capable"] and not row.is_variant_capable:
            if (
                await db.scalar(
                    select(AttributeSetMember.id)
                    .where(
                        AttributeSetMember.company_id == row.company_id,
                        AttributeSetMember.definition_id == row.id,
                        AttributeSetMember.allow_variant_axis.is_(True),
                    )
                    .limit(1)
                )
                is not None
            ):
                raise ConflictError("attribute is used by a variant-capable template member")
        if not row.is_active and before.get("is_active", False):
            if (
                await db.scalar(
                    select(AttributeOption.id)
                    .where(
                        AttributeOption.company_id == row.company_id,
                        AttributeOption.definition_id == row.id,
                        AttributeOption.is_active.is_(True),
                    )
                    .limit(1)
                )
                is not None
            ):
                raise ConflictError("attribute definition has active options")
            used = (
                select(AttributeSetMember.id)
                .join(
                    AttributeSetRevision,
                    (AttributeSetRevision.company_id == AttributeSetMember.company_id)
                    & (AttributeSetRevision.id == AttributeSetMember.revision_id),
                )
                .join(
                    AttributeSet,
                    (AttributeSet.company_id == AttributeSetRevision.company_id)
                    & (AttributeSet.id == AttributeSetRevision.attribute_set_id),
                )
                .where(
                    AttributeSetMember.company_id == row.company_id,
                    AttributeSetMember.definition_id == row.id,
                    AttributeSetRevision.published_at.is_not(None),
                    AttributeSet.is_active.is_(True),
                )
                .limit(1)
            )
            if await db.scalar(used) is not None:
                raise ConflictError("attribute definition belongs to an active published template")
    elif isinstance(row, AttributeOption):
        definition = await company_object(
            db, AttributeDefinition, row.definition_id, company_id=row.company_id
        )
        semantic_fields = {"definition_id", "value_type", "unit_id", *VALUE_FIELDS.values()}
        changing = creating or any(
            getattr(row, field) != before.get(field) for field in semantic_fields
        )
        if (changing or activating) and not definition.is_active:
            raise ConflictError("attribute definition is inactive")
        value = AttributeValue(
            row.value_type, getattr(row, VALUE_FIELDS[row.value_type]), row.unit_id
        )
        value.validate_definition(definition_rules(definition))
        canonical_unit_id = None
        conversion = None
        if row.unit_id is not None:
            unit = await company_object(db, UnitOfMeasure, row.unit_id, company_id=row.company_id)
            if unit.dimension != definition.measurement_dimension or (
                (changing or activating) and not unit.is_active
            ):
                raise ValidationFailedError(
                    "attribute unit must be active and match the definition dimension"
                )
            try:
                QuantityRule(unit.decimal_places, unit.quantity_increment).validate(value.value)
            except MoneyError as exc:
                raise ValidationFailedError(
                    "attribute value violates its unit precision or increment"
                ) from exc
            relation = await db.scalar(
                select(UnitConversion).where(
                    UnitConversion.company_id == row.company_id,
                    UnitConversion.from_unit_id == unit.id,
                )
            )
            if relation is None:
                raise ConflictError(
                    "measured attributes require a declared canonical unit conversion"
                )
            canonical_unit_id = relation.canonical_unit_id
            conversion = RationalConversion(relation.numerator, relation.denominator)
        digest, canonical = value.canonical(
            canonical_unit_id=canonical_unit_id, conversion=conversion
        )
        existing = (
            await db.execute(
                select(AttributeOption.id, AttributeOption.canonical_value)
                .where(
                    AttributeOption.company_id == row.company_id,
                    AttributeOption.definition_id == row.definition_id,
                    AttributeOption.value_hash == digest,
                    AttributeOption.id != row.id,
                )
                .limit(1)
            )
        ).first()
        if existing is not None:
            if existing.canonical_value != canonical:
                raise ConflictError("attribute value hash collision requires review")
            raise ConflictError("attribute option value already exists")
        row.value_hash, row.canonical_value = digest, canonical
    elif isinstance(row, AttributeSet):
        if not creating and row.code != before["code"]:
            if (
                await db.scalar(
                    select(AttributeSetRevision.id)
                    .where(
                        AttributeSetRevision.company_id == row.company_id,
                        AttributeSetRevision.attribute_set_id == row.id,
                    )
                    .limit(1)
                )
                is not None
            ):
                raise ConflictError("attribute set identity is immutable after its first revision")

        if activating:
            invalid = (
                select(AttributeSetMember.id)
                .join(
                    AttributeSetRevision,
                    (AttributeSetRevision.company_id == AttributeSetMember.company_id)
                    & (AttributeSetRevision.id == AttributeSetMember.revision_id),
                )
                .join(
                    AttributeDefinition,
                    (AttributeDefinition.company_id == AttributeSetMember.company_id)
                    & (AttributeDefinition.id == AttributeSetMember.definition_id),
                )
                .where(
                    AttributeSetMember.company_id == row.company_id,
                    AttributeSetRevision.attribute_set_id == row.id,
                    AttributeSetRevision.published_at.is_not(None),
                    AttributeDefinition.is_active.is_(False),
                )
                .limit(1)
            )
            if await db.scalar(invalid) is not None:
                raise ConflictError("published attribute templates require active definitions")
        if not row.is_active and before.get("is_active", False):
            used = (
                select(ProductTypeRevision.id)
                .join(
                    AttributeSetRevision,
                    (AttributeSetRevision.company_id == ProductTypeRevision.company_id)
                    & (AttributeSetRevision.id == ProductTypeRevision.attribute_set_revision_id),
                )
                .join(
                    ProductType,
                    (ProductType.company_id == ProductTypeRevision.company_id)
                    & (ProductType.id == ProductTypeRevision.product_type_id),
                )
                .where(
                    ProductTypeRevision.company_id == row.company_id,
                    AttributeSetRevision.attribute_set_id == row.id,
                    ProductType.is_active.is_(True),
                )
                .limit(1)
            )
            if await db.scalar(used) is not None:
                raise ConflictError("attribute template is referenced by an active product type")

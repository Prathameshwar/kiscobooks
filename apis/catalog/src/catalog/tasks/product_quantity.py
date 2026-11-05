"""Validate entered compound/measured quantities against definitions, without stock writes."""

from decimal import Context, Decimal, localcontext
from fractions import Fraction

from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.exact import RationalConversion, convert_quantity, exact_decimal
from billing_platform.money import MoneyError

from catalog.domain.units import QuantityRule
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.units import UnitOfMeasure
from catalog.schemas.product_authoring import QuantityPreviewInput, QuantityPreviewResult
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_requirements import configuration
from catalog.tasks.product_unit_rules import base_quantity_rule, require_serial_base
from catalog.tasks.unit_consistency import validate_fixed_ratio, validate_measured_relation


async def preview(work: ProductWork, body: QuantityPreviewInput) -> QuantityPreviewResult:
    assert work.item is not None
    effective = await configuration(work, body.as_of)
    if len(body.components) > 1 and effective.options.compound_units_mode == "DISABLED":
        raise ValidationFailedError("compound quantity entry is disabled")
    base = await work.access.reference(UnitOfMeasure, work.item.base_unit_id)
    base_rule = await base_quantity_rule(work, body.as_of)
    await require_serial_base(work, effective, body.as_of, base_rule)
    total = Decimal(0)
    try:
        for component in body.components:
            revision = await work.access.reference(ItemUnitRevision, component.unit_revision_id)
            binding = await work.access.reference(ItemUnitBinding, revision.binding_id)
            if binding.item_id != work.item.id:
                raise PermissionDeniedError("quantity unit belongs to another SKU")
            if revision.valid_from > body.as_of or (
                revision.valid_to is not None and revision.valid_to < body.as_of
            ):
                raise ConflictError("quantity unit revision is not effective on this date")
            if component.quantity <= 0:
                raise ValidationFailedError("entered component quantity must be positive")
            QuantityRule(revision.quantity_decimal_places, revision.quantity_increment).validate(
                component.quantity
            )
            if revision.conversion_mode == "FIXED":
                await validate_fixed_ratio(
                    work.access,
                    binding.unit_id,
                    base.id,
                    Fraction(revision.numerator, revision.denominator),
                )
                if component.measured_base_quantity is not None:
                    raise ValidationFailedError(
                        "fixed conversion cannot accept a measured override"
                    )
                converted = convert_quantity(
                    component.quantity,
                    RationalConversion(revision.numerator, revision.denominator),
                    decimal_places=base_rule.decimal_places,
                    increment=base_rule.increment,
                )
            else:
                await validate_measured_relation(work.access, binding.unit_id, base.id)
                if (
                    effective.options.measured_units_mode == "DISABLED"
                    or component.measured_base_quantity is None
                ):
                    raise ValidationFailedError(
                        "measured entry requires an allowed explicit base measurement"
                    )
                converted = component.measured_base_quantity
                if converted <= 0:
                    raise ValidationFailedError("measured base quantity must be positive")
                base_rule.validate(converted)
            with localcontext(Context(prec=50)):
                total += converted
        total = exact_decimal(
            total, decimal_places=base_rule.decimal_places, increment=base_rule.increment
        )
    except MoneyError as exc:
        raise ValidationFailedError(
            "quantity is not exactly representable under its unit rules"
        ) from exc
    if work.item.min_sale_quantity is not None and total < work.item.min_sale_quantity:
        raise ValidationFailedError("quantity is below the SKU minimum sale quantity")
    return QuantityPreviewResult(
        item_id=work.item.id, base_unit_id=base.id, base_quantity=total, components=body.components
    )

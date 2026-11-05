"""Protected dated quantity evidence for the existing signed stock fence."""

from fractions import Fraction
from typing import Any

from billing_platform.errors import ConflictError
from billing_platform.gateway import Actor
from sqlalchemy.ext.asyncio import AsyncSession
from voucher_execution.stock_facts import StockFenceRequest

from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.units import UnitOfMeasure
from catalog.tasks.product_requirements import configuration, product_work
from catalog.tasks.unit_consistency import validate_fixed_ratio, validate_measured_relation


async def quantity_facts(
    db: AsyncSession,
    actor: Actor,
    request: StockFenceRequest,
    items: dict[Any, Any],
    contexts: dict[str, Any],
) -> dict[Any, list[dict[str, Any]]]:
    # Local imports avoid a dependency cycle with the common source scope helpers.
    from catalog.tasks.stock_sources import rows, visible

    if not request.quantity_unit_revision_ids:
        return {}
    company = request.company_id
    revisions = await rows(db, ItemUnitRevision, company, request.quantity_unit_revision_ids)
    bindings = await rows(
        db, ItemUnitBinding, company, tuple({row.binding_id for row in revisions.values()})
    )
    units = await rows(
        db, UnitOfMeasure, company, tuple({row.unit_id for row in bindings.values()})
    )
    works, configurations = {}, {}
    result: dict[Any, list[dict[str, Any]]] = {}
    for revision in revisions.values():
        binding = bindings[revision.binding_id]
        unit = units[binding.unit_id]
        if binding.item_id not in items or not unit.is_active:
            raise ConflictError("quantity unit is unavailable for this stock item")
        if revision.valid_from > request.stock_date or (
            revision.valid_to and revision.valid_to < request.stock_date
        ):
            raise ConflictError("quantity unit revision is not effective on the stock date")
        visible(contexts["item_unit_binding"], binding, {"item_id", "unit_id", "usage_role"})
        visible(
            contexts["item_unit_revision"],
            revision,
            {
                "valid_from",
                "valid_to",
                "conversion_mode",
                "numerator",
                "denominator",
                "quantity_increment",
                "quantity_decimal_places",
                "fractional_entry",
                "secondary_unit_id",
            },
        )
        visible(
            contexts["unit_of_measure"],
            unit,
            {"is_active", "quantity_increment", "decimal_places", "dimension"},
        )
        if revision.quantity_increment % unit.quantity_increment:
            raise ConflictError("quantity unit rule widens its master increment")
        if binding.item_id not in works:
            works[binding.item_id] = await product_work(db, actor, company, binding.item_id)
            configurations[binding.item_id] = await configuration(
                works[binding.item_id], request.stock_date
            )
        work, config = works[binding.item_id], configurations[binding.item_id]
        base = items[binding.item_id].base_unit_id
        if revision.conversion_mode == "FIXED":
            if binding.usage_role != "BASE" and config.options.alternate_units_mode == "DISABLED":
                raise ConflictError("alternate stock quantities are disabled for this product")
            await validate_fixed_ratio(
                work.access, unit.id, base, Fraction(revision.numerator, revision.denominator)
            )
        else:
            if (
                config.options.measured_units_mode == "DISABLED"
                or revision.secondary_unit_id != base
            ):
                raise ConflictError(
                    "measured stock quantities are disabled or have a different base unit"
                )
            await validate_measured_relation(work.access, unit.id, base)
        result.setdefault(binding.item_id, []).append(
            {
                "item_id": binding.item_id,
                "unit_id": unit.id,
                "revision_id": revision.id,
                "usage_role": binding.usage_role,
                "conversion_mode": revision.conversion_mode,
                "numerator": str(revision.numerator) if revision.numerator is not None else None,
                "denominator": str(revision.denominator)
                if revision.denominator is not None
                else None,
                "quantity_increment": str(revision.quantity_increment),
                "quantity_decimal_places": min(
                    unit.decimal_places, revision.quantity_decimal_places
                ),
                "fractional_entry": revision.fractional_entry,
            }
        )
    return result

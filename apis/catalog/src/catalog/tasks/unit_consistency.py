"""Keep declared physical conversions consistent with retained SKU definitions."""

import uuid
from fractions import Fraction

from billing_platform.errors import ConflictError, PermissionDeniedError
from sqlalchemy import or_, select

from catalog.domain.units import validate_measured_units
from catalog.models import Item, ItemUnitBinding, ItemUnitRevision, UnitConversion
from catalog.tasks.configuration_access import ConfigurationAccess


async def canonical_relations(
    access: ConfigurationAccess,
    units: set[uuid.UUID],
    *,
    permission: str | None = None,
) -> dict[uuid.UUID, UnitConversion]:
    context = await access.context(UnitConversion, permission=permission)
    if not set(context.native.fields) <= context.readable():
        raise PermissionDeniedError("unit consistency requires readable canonical relations")
    rows = list(
        await access.db.scalars(
            select(UnitConversion).where(
                UnitConversion.company_id == access.company,
                UnitConversion.from_unit_id.in_(units),
            )
        )
    )
    for row in rows:
        values = {key: getattr(row, key) for key in context.native.fields}
        if not set(values) <= context.readable(values):
            raise PermissionDeniedError("unit consistency requires readable canonical relations")
    return {row.from_unit_id: row for row in rows}


def check_ratio(
    relations: dict[uuid.UUID, UnitConversion],
    unit_id: uuid.UUID,
    base_id: uuid.UUID,
    ratio: Fraction,
) -> None:
    source, target = relations.get(unit_id), relations.get(base_id)
    if source is None or target is None or source.canonical_unit_id != target.canonical_unit_id:
        # Undeclared containers retain product-specific sizes.
        return
    canonical = Fraction(
        source.numerator * target.denominator, source.denominator * target.numerator
    )
    if canonical != ratio:
        raise ConflictError("product conversion conflicts with declared canonical unit relations")


async def validate_fixed_ratio(
    access: ConfigurationAccess,
    unit_id: uuid.UUID,
    base_id: uuid.UUID,
    ratio: Fraction,
) -> None:
    if unit_id == base_id:
        if ratio != 1:
            raise ConflictError("base-unit conversion must be identity")
        return
    check_ratio(await canonical_relations(access, {unit_id, base_id}), unit_id, base_id, ratio)


def check_measured(
    relations: dict[uuid.UUID, UnitConversion], unit_id: uuid.UUID, base_id: uuid.UUID
) -> None:
    source, target = relations.get(unit_id), relations.get(base_id)
    if (
        source is not None
        and target is not None
        and source.canonical_unit_id == target.canonical_unit_id
    ):
        raise ConflictError("measured conversion conflicts with declared canonical unit relations")


async def validate_measured_relation(
    access: ConfigurationAccess, unit_id: uuid.UUID, base_id: uuid.UUID
) -> None:
    validate_measured_units(unit_id, base_id)
    check_measured(await canonical_relations(access, {unit_id, base_id}), unit_id, base_id)


async def guard_relation(access: ConfigurationAccess, candidate: UnitConversion) -> None:
    """Both writers hold the company lock; include closed revisions without truncation."""
    # Unit administrators can check dependencies; field denies still apply.
    # Conflict messages expose no dependent product identifiers.
    for model, fields in (
        (Item, {"base_unit_id"}),
        (ItemUnitBinding, {"unit_id", "item_id"}),
        (ItemUnitRevision, {"binding_id", "conversion_mode", "numerator", "denominator"}),
    ):
        context = await access.context(model, permission="unit.manage")
        if not fields <= context.readable():
            raise PermissionDeniedError("unit consistency requires readable product dependencies")
    rows = (
        await access.db.execute(
            select(
                ItemUnitBinding.unit_id,
                Item.base_unit_id,
                ItemUnitRevision.numerator,
                ItemUnitRevision.denominator,
                ItemUnitRevision.conversion_mode,
            )
            .select_from(ItemUnitBinding)
            .join(
                Item,
                (Item.id == ItemUnitBinding.item_id)
                & (Item.tenant_id == ItemUnitBinding.tenant_id)
                & (Item.company_id == ItemUnitBinding.company_id),
            )
            .join(
                ItemUnitRevision,
                (ItemUnitRevision.binding_id == ItemUnitBinding.id)
                & (ItemUnitRevision.tenant_id == ItemUnitBinding.tenant_id)
                & (ItemUnitRevision.company_id == ItemUnitBinding.company_id),
            )
            .where(
                ItemUnitBinding.company_id == access.company,
                ItemUnitRevision.conversion_mode.in_(("FIXED", "MEASURED")),
                ItemUnitBinding.unit_id != Item.base_unit_id,
                or_(
                    ItemUnitBinding.unit_id == candidate.from_unit_id,
                    Item.base_unit_id == candidate.from_unit_id,
                ),
            )
            .limit(1025)
        )
    ).all()
    if not rows:
        return
    if len(rows) > 1024:
        raise ConflictError(
            "canonical relation exceeds the product-history validation bound of 1024"
        )
    units = {unit for row in rows for unit in (row.unit_id, row.base_unit_id)}
    relations = await canonical_relations(access, units, permission="unit.manage")
    relations[candidate.from_unit_id] = candidate
    for row in rows:
        if row.conversion_mode == "MEASURED":
            check_measured(relations, row.unit_id, row.base_unit_id)
        else:
            check_ratio(
                relations, row.unit_id, row.base_unit_id, Fraction(row.numerator, row.denominator)
            )

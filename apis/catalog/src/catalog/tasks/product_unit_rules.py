"""Validate quantity grids over every affected current and scheduled unit interval."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.exact import RationalConversion, convert_quantity
from billing_platform.money import MoneyError
from sqlalchemy import or_, select

from catalog.domain.units import QuantityRule, validate_serial_rule
from catalog.models.inventory_templates import InventoryProfileTemplateRevision
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.units import UnitOfMeasure
from catalog.schemas.configuration import EffectiveConfiguration
from catalog.tasks.configuration_access import ConfigurationAccess

if TYPE_CHECKING:
    from catalog.tasks.product_commands import ProductWork


async def unit_revisions(
    access: ConfigurationAccess,
    item_id: uuid.UUID,
    as_of: dt.date,
    *,
    base: bool,
    effective_only: bool = False,
) -> list[ItemUnitRevision]:
    for model in (ItemUnitBinding, ItemUnitRevision):
        context = await access.context(model)
        if set(context.native.fields) - context.readable():
            raise PermissionDeniedError("SKU quantity definitions are protected")
    statement = (
        select(ItemUnitRevision)
        .join(
            ItemUnitBinding,
            (ItemUnitBinding.tenant_id == ItemUnitRevision.tenant_id)
            & (ItemUnitBinding.company_id == ItemUnitRevision.company_id)
            & (ItemUnitBinding.id == ItemUnitRevision.binding_id),
        )
        .where(
            ItemUnitRevision.company_id == access.company,
            ItemUnitBinding.item_id == item_id,
            ItemUnitBinding.usage_role == "BASE" if base else ItemUnitBinding.usage_role != "BASE",
            or_(ItemUnitRevision.valid_to.is_(None), ItemUnitRevision.valid_to >= as_of),
        )
    )
    if effective_only:
        statement = statement.where(ItemUnitRevision.valid_from <= as_of)
    rows = list(
        await access.db.scalars(
            statement.order_by(ItemUnitRevision.id).limit(2 if effective_only else 1025)
        )
    )
    if len(rows) > 1024:
        raise ConflictError("scheduled SKU unit revisions exceed the validation bound of 1024")
    if len({row.binding_id for row in rows}) > 64:
        raise ConflictError("SKU unit definitions exceed the authoring bound")
    for row in rows:
        await access.require(row)
    return rows


async def validate_alternate_grids(work: "ProductWork", rule: QuantityRule, as_of: dt.date) -> None:
    assert work.item is not None
    # A newly appended base revision runs indefinitely, overlapping later alternates too.
    for row in await unit_revisions(work.access, work.item.id, as_of, base=False):
        if row.conversion_mode == "FIXED":
            assert row.numerator is not None and row.denominator is not None
            convert_quantity(
                row.quantity_increment,
                RationalConversion(row.numerator, row.denominator),
                decimal_places=rule.decimal_places,
                increment=rule.increment,
            )


async def validate_base_grids(
    work: "ProductWork", increment: Decimal, ratio: RationalConversion, as_of: dt.date
) -> None:
    assert work.item is not None
    # The alternate may begin before an already scheduled stricter base revision.
    for row in await unit_revisions(work.access, work.item.id, as_of, base=True):
        convert_quantity(
            increment,
            ratio,
            decimal_places=row.quantity_decimal_places,
            increment=row.quantity_increment,
        )


async def base_quantity_rule(work: "ProductWork", as_of: dt.date) -> QuantityRule:
    assert work.item is not None
    rows = await unit_revisions(work.access, work.item.id, as_of, base=True, effective_only=True)
    if len(rows) != 1:
        raise ConflictError("quantity entry requires one effective base-unit revision")
    row = rows[0]
    return QuantityRule(row.quantity_decimal_places, row.quantity_increment)


async def require_serial_base(
    work: "ProductWork",
    config: EffectiveConfiguration,
    as_of: dt.date,
    rule: QuantityRule | None = None,
) -> None:
    assert work.item is not None
    profile_id = config.profiles.inventory_template_revision_id
    if profile_id is None:
        return
    profile = await work.access.reference(InventoryProfileTemplateRevision, profile_id)
    if profile.serial_tracking:
        base = await work.access.reference(UnitOfMeasure, work.item.base_unit_id)
        validate_serial_rule(base.dimension, rule or await base_quantity_rule(work, as_of))


async def validate_minimum_quantity(
    access: ConfigurationAccess, item_id: uuid.UUID, minimum: Decimal
) -> None:
    context = await access.context(ItemUnitRevision)
    today = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
    for row in await unit_revisions(access, item_id, today, base=True):
        try:
            QuantityRule(row.quantity_decimal_places, row.quantity_increment).validate(minimum)
        except MoneyError as exc:
            raise ValidationFailedError(
                "minimum sale quantity does not fit a current or scheduled SKU base unit"
            ) from exc

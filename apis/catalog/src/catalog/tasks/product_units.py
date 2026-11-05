"""SKU-specific exact unit revisions and globally scoped product barcode identities."""

import datetime as dt
from fractions import Fraction
from typing import Literal, cast
from zoneinfo import ZoneInfo

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.exact import RationalConversion, convert_quantity, exact_decimal
from billing_platform.ids import uuid7
from billing_platform.money import MoneyError
from sqlalchemy import select

from catalog.domain.barcodes import generate_internal_value, gtin_aliases
from catalog.domain.product_authoring import validate_barcode
from catalog.domain.units import QuantityRule
from catalog.models.product_definitions import ItemBarcode, ItemUnitBinding, ItemUnitRevision
from catalog.models.units import PackType, UnitOfMeasure
from catalog.schemas.product_authoring import (
    BarcodeGenerateInput,
    BarcodeInput,
    BarcodeStateInput,
    UnitBindingInput,
    UnitRevisionInput,
)
from catalog.tasks.product_commands import ProductWork
from catalog.tasks.product_unit_rules import (
    base_quantity_rule,
    require_serial_base,
    validate_alternate_grids,
    validate_base_grids,
)
from catalog.tasks.unit_consistency import validate_fixed_ratio, validate_measured_relation


async def bind_unit(work: ProductWork, body: UnitBindingInput) -> None:
    assert work.item is not None
    if isinstance(body, UnitRevisionInput):
        binding = await work.access.reference(ItemUnitBinding, body.binding_id)
        if binding.item_id != work.item.id:
            raise PermissionDeniedError("unit binding belongs to another SKU")
        if (binding.code, binding.unit_id, binding.usage_role) != (
            body.code,
            body.unit_id,
            body.role,
        ):
            raise ConflictError("unit binding identity cannot change through a numeric revision")
    else:
        from catalog.tasks.product_attributes import bounded

        if len(await bounded(work, ItemUnitBinding, "item_id", work.item.id, 64)) >= 64:
            raise ConflictError("SKU unit definitions exceed the authoring bound")
        binding = await work.new(
            ItemUnitBinding,
            item_id=work.item.id,
            code=body.code,
            unit_id=body.unit_id,
            usage_role=body.role,
        )
    context = await work.access.context(ItemUnitRevision)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("unit revision history is protected")
    previous = await work.db.scalar(
        select(ItemUnitRevision)
        .where(
            ItemUnitRevision.company_id == work.company, ItemUnitRevision.binding_id == binding.id
        )
        .order_by(ItemUnitRevision.revision.desc())
        .limit(1)
    )
    if previous is not None and (
        previous.revision >= 2**31 - 1 or body.valid_from <= previous.valid_from
    ):
        raise ConflictError("unit revision must advance its effective date and revision")
    today = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
    if previous is not None and body.valid_from < today:
        raise ConflictError("unit revision cannot rewrite effective history")
    if previous is not None and (
        previous.conversion_mode != body.conversion_mode
        or previous.numerator != body.numerator
        or previous.denominator != body.denominator
        or previous.nominal_ratio != body.nominal_ratio
        or previous.quantity_decimal_places != body.quantity_decimal_places
        or previous.quantity_increment != body.quantity_increment
        or previous.fractional_entry != body.fractional_entry
    ):
        owned_code = await work.db.scalar(
            select(ItemBarcode.id)
            .where(
                ItemBarcode.company_id == work.company,
                ItemBarcode.binding_id == binding.id,
            )
            .limit(1)
        )
        if owned_code is not None:
            raise ConflictError("barcoded unit meaning is immutable; create a new binding")
    values = body.model_dump(
        exclude={"expected_version", "code", "unit_id", "role", "binding_id", "accept_defaults"}
    )
    row = await work.new(
        ItemUnitRevision,
        binding_id=binding.id,
        revision=previous.revision + 1 if previous else 1,
        valid_to=None,
        **values,
    )
    if body.accept_defaults is not None:
        from catalog.schemas.configuration import AuthoringDefaultsQuery
        from catalog.tasks.configuration_authoring import accepted

        suggestion = await accepted(
            work.access,
            body.accept_defaults,
            AuthoringDefaultsQuery(
                as_of=body.valid_from,
                kind=cast(Literal["GOODS", "SERVICE"], work.family.kind),
                item_id=work.item.id,
                unit_id=body.unit_id,
                include_price=False,
            ),
        )
        selected = suggestion.quantity
        if selected is None or (
            body.quantity_decimal_places,
            body.quantity_increment,
            body.fractional_entry,
        ) != (
            selected.quantity_decimal_places,
            selected.quantity_increment,
            selected.fractional_entry,
        ):
            raise ConflictError("quantity settings differ from accepted defaults")
    from catalog.tasks.product_choices import require_choice

    if body.unit_id != work.item.base_unit_id or body.role == "PACK":
        await require_choice(work, "alternate_units", as_of=body.valid_from)
    if body.conversion_mode == "MEASURED":
        await require_choice(work, "measured_units", as_of=body.valid_from)
    unit = await work.access.reference(UnitOfMeasure, body.unit_id)
    base = await work.access.reference(UnitOfMeasure, work.item.base_unit_id)
    if body.pack_type_id is not None:
        await work.access.reference(PackType, body.pack_type_id)
    try:
        quantity = QuantityRule(body.quantity_decimal_places, body.quantity_increment)
        if body.role == "BASE":
            from catalog.tasks.product_requirements import configuration

            await require_serial_base(
                work, await configuration(work, body.valid_from), body.valid_from, quantity
            )
            if work.item.min_sale_quantity is not None:
                quantity.validate(work.item.min_sale_quantity)
            await validate_alternate_grids(work, quantity, body.valid_from)
        base_rule = (
            quantity if body.role == "BASE" else await base_quantity_rule(work, body.valid_from)
        )
        QuantityRule(unit.decimal_places, unit.quantity_increment).validate(body.quantity_increment)
        if body.quantity_decimal_places > unit.decimal_places:
            raise ValidationFailedError("SKU quantity precision cannot exceed its unit")
        if not body.fractional_entry and (
            body.quantity_decimal_places != 0 or Fraction(body.quantity_increment).denominator != 1
        ):
            raise ValidationFailedError("fractional quantities require explicit fractional entry")
        if body.conversion_mode == "FIXED":
            if (
                body.numerator is None
                or body.denominator is None
                or body.secondary_unit_id is not None
                or body.nominal_ratio is not None
            ):
                raise ValidationFailedError(
                    "fixed unit revisions require only an exact numerator/denominator"
                )
            ratio = RationalConversion(body.numerator, body.denominator)
            if unit.dimension != base.dimension:
                raise ValidationFailedError("fixed conversions require compatible unit dimensions")
            if body.unit_id == base.id and ratio.numerator != ratio.denominator:
                raise ValidationFailedError("base-unit conversion must be identity")
            if body.role == "BASE" and (body.unit_id != base.id or body.pack_type_id is not None):
                raise ValidationFailedError("base binding must use the SKU base unit")
            if body.role == "MEASURED":
                raise ValidationFailedError("measured binding requires measured conversion")
            await validate_fixed_ratio(
                work.access, unit.id, base.id, Fraction(ratio.numerator, ratio.denominator)
            )
            convert_quantity(
                quantity.increment,
                ratio,
                decimal_places=base_rule.decimal_places,
                increment=base_rule.increment,
            )
            if body.role != "BASE":
                await validate_base_grids(work, quantity.increment, ratio, body.valid_from)
            row.numerator, row.denominator = ratio.numerator, ratio.denominator
        else:
            if (
                work.family.kind != "GOODS"
                or body.role != "MEASURED"
                or body.numerator is not None
                or body.denominator is not None
            ):
                raise ValidationFailedError(
                    "measured dual quantities require a goods measured binding"
                )
            if (
                body.secondary_unit_id != base.id
                or body.nominal_ratio is None
                or body.nominal_ratio <= 0
            ):
                raise ValidationFailedError(
                    "measured unit needs its actual base-unit measure and positive nominal ratio"
                )
            await work.access.reference(UnitOfMeasure, body.secondary_unit_id)
            await validate_measured_relation(work.access, unit.id, base.id)
            exact_decimal(body.nominal_ratio)
        # Canonicalized ratios are part of the checked resulting field set.
        await work.access.write(row, {})
    except MoneyError as exc:
        raise ValidationFailedError(
            "unit conversion or quantity is not exactly representable"
        ) from exc
    if body.role == "BASE" and not isinstance(body, UnitRevisionInput):
        if (
            await work.db.scalar(
                select(ItemUnitBinding.id)
                .where(
                    ItemUnitBinding.company_id == work.company,
                    ItemUnitBinding.item_id == work.item.id,
                    ItemUnitBinding.usage_role == "BASE",
                )
                .limit(1)
            )
            is not None
        ):
            raise ConflictError("SKU already has a base binding")
    if previous is not None:
        before = await work.access.values(previous)
        previous.valid_to = body.valid_from - dt.timedelta(days=1)
        previous.row_version += 1
        await work.record(previous, before, "close")
    else:
        work.db.add(binding)
        await work.db.flush([binding])
    work.db.add(row)


async def add_barcode(work: ProductWork, body: BarcodeInput) -> None:
    assert work.item is not None
    row = await work.new(
        ItemBarcode,
        item_id=work.item.id,
        is_active=True,
        **body.model_dump(exclude={"expected_version"}),
    )
    from catalog.tasks.product_choices import require_choice

    await require_choice(work, "barcode")
    validate_barcode(body.value, body.symbology)
    await require_barcode_unique(work, body.value, body.symbology)
    if body.binding_id is not None:
        binding = await work.access.reference(ItemUnitBinding, body.binding_id)
        if binding.item_id != work.item.id:
            raise PermissionDeniedError("barcode unit binding belongs to another SKU")
        if binding.usage_role == "MEASURED":
            raise ValidationFailedError("barcodes require a fixed-quantity unit binding")
        context = await work.access.context(ItemUnitRevision)
        as_of = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
        revision_query = select(ItemUnitRevision).where(
            ItemUnitRevision.company_id == work.company,
            ItemUnitRevision.binding_id == binding.id,
        )
        if work.item.status == "ACTIVE":
            revision_query = revision_query.where(
                ItemUnitRevision.valid_from <= as_of,
                (ItemUnitRevision.valid_to.is_(None) | (ItemUnitRevision.valid_to >= as_of)),
            )
        revisions = list(
            await work.db.scalars(revision_query.order_by(ItemUnitRevision.valid_from).limit(2))
        )
        if not revisions or (work.item.status == "ACTIVE" and len(revisions) != 1):
            raise ConflictError("barcode unit binding has no unambiguous current fixed revision")
        if any(revision.conversion_mode != "FIXED" for revision in revisions):
            raise ConflictError("barcode unit binding requires fixed revisions")
        await work.access.require(revisions[0])
    work.db.add(row)


async def require_barcode_unique(work: ProductWork, value: str, symbology: str) -> None:
    """The company policy lock serializes equivalent-GTIN claims across API writers."""
    if symbology != "GTIN" and not (value.isascii() and value.isdigit()):
        return
    try:
        aliases = gtin_aliases(value)
    except ValidationFailedError:
        # A plain numeric Code 128/QR payload need not itself be a GTIN.
        return
    existing = await work.db.scalar(
        select(ItemBarcode.id)
        .where(
            ItemBarcode.company_id == work.company,
            ItemBarcode.value.in_(aliases),
        )
        .limit(1)
    )
    if existing is not None:
        raise ConflictError("equivalent GTIN is already owned by this company")


async def generate_barcode(work: ProductWork, body: BarcodeGenerateInput) -> None:
    await add_barcode(
        work,
        BarcodeInput(
            expected_version=body.expected_version,
            binding_id=body.binding_id,
            value=generate_internal_value(uuid7()),
            symbology="CODE128",
        ),
    )


async def barcode_state(work: ProductWork, body: BarcodeStateInput) -> None:
    assert work.item is not None
    # An inactive barcode must still be addressable for explicit reactivation.
    from billing_platform.db.access import company_object

    context = await work.access.context(ItemBarcode)
    if set(context.native.fields) - context.readable():
        raise PermissionDeniedError("barcode lifecycle fields are protected")
    row = await company_object(work.db, ItemBarcode, body.barcode_id, company_id=work.company)
    await work.access.require(row)
    if row.item_id != work.item.id:
        raise PermissionDeniedError("barcode belongs to another SKU")
    before = await work.access.values(row)
    if row.is_active != body.is_active:
        if not body.is_active and work.item.status == "ACTIVE":
            from catalog.tasks.product_requirements import configuration

            context = await work.access.context(ItemBarcode)
            as_of = utcnow().astimezone(ZoneInfo(context.company.timezone)).date()
            effective = await configuration(work, as_of)
            if effective.options.barcode_mode == "REQUIRED":
                other = await work.db.scalar(
                    select(ItemBarcode.id)
                    .where(
                        ItemBarcode.company_id == work.company,
                        ItemBarcode.item_id == work.item.id,
                        ItemBarcode.id != row.id,
                        ItemBarcode.is_active.is_(True),
                    )
                    .limit(1)
                )
                if other is None:
                    raise ConflictError("active item requires at least one barcode")
        if row.row_version >= 2**31 - 1:
            raise ConflictError("barcode version exhausted")
        row.is_active = body.is_active
        row.row_version += 1
        await work.record(row, before, "update")
    if body.is_active:
        from catalog.tasks.product_choices import require_choice

        await require_choice(work, "barcode")

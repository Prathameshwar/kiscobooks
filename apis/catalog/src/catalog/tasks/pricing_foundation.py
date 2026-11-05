"""Price levels/books and exact dated SKU-unit policies."""

import datetime as dt
import uuid
from fractions import Fraction
from typing import Any, Literal, cast

from billing_platform.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from billing_platform.exact import exact_decimal
from billing_platform.reference import load
from pydantic import BaseModel
from sqlalchemy import select

from catalog.domain.pricing import RateGrid
from catalog.domain.units import QuantityRule
from catalog.models.pricing import (
    CompanyPricingPolicy,
    ItemPriceNumericRevision,
    ItemPriceScope,
    ItemPriceSeries,
    PriceLevel,
    PricePlan,
    PricingRow,
)
from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
from catalog.models.projections import CompanyCurrencyAllowanceProjection
from catalog.models.sales_channel import SalesChannel
from catalog.models.units import PackType, UnitOfMeasure
from catalog.schemas.pricing import (
    BootstrapInput,
    LevelCreate,
    LevelPatch,
    NumericInput,
    PlanCreate,
    PlanPatch,
    PolicyInput,
    ScopeInput,
    SeriesInput,
)
from catalog.tasks.classification import validate_custom
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.custom_fields import reserve_claims
from catalog.tasks.field_indexes import index_values
from catalog.tasks.pricing_commands import PricingWork, product, protected, purpose_access, row
from catalog.tasks.unit_consistency import validate_fixed_ratio, validate_measured_relation

CONTROL_FIELDS = {
    "expected_generation",
    "expected_source_version",
    "supersedes_id",
    "expected_previous_version",
    "expected_version",
    "accept_defaults",
}


def values(body: BaseModel) -> dict[str, Any]:
    return body.model_dump(exclude=CONTROL_FIELDS)


async def currency(access: ConfigurationAccess, code: str, *, owner: type[Any] = PricePlan) -> None:
    context = await access.context(owner)
    if code not in {entry["code"] for entry in load("currency")}:
        raise ValidationFailedError("unknown ISO currency")
    if code != context.company.base_currency and "multi_currency" not in context.features:
        raise ConflictError("foreign currency pricing requires enabled multi_currency")
    if code != context.company.base_currency:
        allowed = await access.db.scalar(
            select(CompanyCurrencyAllowanceProjection.id).where(
                CompanyCurrencyAllowanceProjection.company_id == context.company.company_id,
                CompanyCurrencyAllowanceProjection.currency_code == code,
                CompanyCurrencyAllowanceProjection.is_active.is_(True),
            )
        )
        if allowed is None:
            raise ConflictError("foreign currency pricing is not enabled for this company")


async def level(access: ConfigurationAccess, level_id: uuid.UUID) -> PriceLevel:
    value = await row(access, PriceLevel, level_id)
    context = await access.context(PriceLevel)
    if not value.is_active:
        raise ConflictError("price level is inactive")
    if value.ordinal != 1 and "multi_price_levels" not in context.features:
        raise ConflictError("additional price levels require enabled multi_price_levels")
    return value


async def unit(
    access: ConfigurationAccess,
    item_id: uuid.UUID,
    revision_id: uuid.UUID,
    as_of: dt.date | None = None,
    *,
    purpose: str | None = None,
) -> tuple[ItemUnitRevision, ItemUnitBinding]:
    item, _ = await product(access, item_id)
    revision = await row(access, ItemUnitRevision, revision_id)
    binding = await row(access, ItemUnitBinding, revision.binding_id)
    if binding.item_id != item_id:
        raise PermissionDeniedError("pricing unit belongs to another SKU")
    master = await access.reference(UnitOfMeasure, binding.unit_id)
    if revision.pack_type_id is not None:
        await access.reference(PackType, revision.pack_type_id)
    if as_of is not None and (
        revision.valid_from > as_of or (revision.valid_to is not None and revision.valid_to < as_of)
    ):
        raise ConflictError("pricing unit revision is not effective on this date")
    if (purpose in {"SALE", "REFERENCE_RETAIL"} and binding.usage_role == "PURCHASE") or (
        purpose == "PURCHASE" and binding.usage_role == "SALE"
    ):
        raise ConflictError("unit binding does not support this price purpose")
    if revision.quantity_decimal_places > master.decimal_places:
        raise ConflictError("pricing unit exceeds its master precision")
    if revision.conversion_mode == "FIXED":
        assert revision.numerator is not None and revision.denominator is not None
        await validate_fixed_ratio(
            access,
            binding.unit_id,
            item.base_unit_id,
            Fraction(revision.numerator, revision.denominator),
        )
    else:
        await validate_measured_relation(access, binding.unit_id, item.base_unit_id)
    return revision, binding


async def numeric(
    access: ConfigurationAccess,
    numeric_id: uuid.UUID,
    item_id: uuid.UUID,
    revision_id: uuid.UUID,
    code: str,
    as_of: dt.date,
    *,
    entering: bool = True,
) -> ItemPriceNumericRevision:
    value = await row(access, ItemPriceNumericRevision, numeric_id)
    if (value.item_id, value.unit_revision_id, value.currency) != (item_id, revision_id, code):
        raise PermissionDeniedError("price precision belongs to another SKU/unit/currency")
    if entering and (
        value.valid_from > as_of or (value.valid_to is not None and value.valid_to < as_of)
    ):
        raise ConflictError("rate precision is not effective at publication start")
    return value


async def bootstrap(
    work: PricingWork, body: BootstrapInput, object_id: uuid.UUID | None
) -> PricingRow:
    await protected(work.access, PriceLevel)
    context = await work.access.context(PriceLevel)
    count = 3 if "multi_price_levels" in context.features else 1
    result = None
    for ordinal in range(1, count + 1):
        existing = await work.db.scalar(
            select(PriceLevel).where(
                PriceLevel.company_id == work.company, PriceLevel.ordinal == ordinal
            )
        )
        if existing is None:
            existing = await work.new(
                PriceLevel,
                code=f"PRICE{ordinal}",
                name=f"Price {ordinal}",
                ordinal=ordinal,
                is_active=True,
            )
        await work.access.require(existing)
        if ordinal == 1:
            result = existing
    assert result is not None
    return result


async def create_level(
    work: PricingWork, body: LevelCreate, object_id: uuid.UUID | None
) -> PricingRow:
    await bootstrap(work, BootstrapInput(), None)
    if "multi_price_levels" not in (await work.access.context(PriceLevel)).features:
        raise ConflictError("additional price levels require enabled multi_price_levels")
    if body.ordinal <= 3 or body.code in {"PRICE1", "PRICE2", "PRICE3"}:
        raise ValidationFailedError("baseline levels are seeded; edit their names instead")
    return await work.new(PriceLevel, **body.model_dump(), is_active=True)


async def update_level(
    work: PricingWork, body: LevelPatch, object_id: uuid.UUID | None
) -> PricingRow:
    assert object_id is not None
    value = await row(work.access, PriceLevel, object_id)
    if not body.name.strip() or any(ord(c) < 32 for c in body.name):
        raise ValidationFailedError("level name must contain printable text")
    if value.ordinal == 1 and not body.is_active:
        raise ConflictError("the baseline price level cannot be retired")
    await work.update(
        value, body.expected_version, name=body.name.strip(), is_active=body.is_active
    )
    if not body.is_active:
        # Keep historical policies/books resolvable; retirement has no effective date.
        for model, field in (
            (PricePlan, PricePlan.price_level_id),
            (CompanyPricingPolicy, CompanyPricingPolicy.default_level_id),
            (CompanyPricingPolicy, CompanyPricingPolicy.fallback_level_id),
        ):
            await protected(work.access, model)
            if (
                await work.db.scalar(
                    select(model.id)
                    .where(model.company_id == work.company, field == value.id)
                    .limit(1)
                )
                is not None
            ):
                raise ConflictError("referenced price levels cannot be retired")
    return value


async def create_plan(
    work: PricingWork, body: PlanCreate, object_id: uuid.UUID | None
) -> PricingRow:
    await currency(work.access, body.currency)
    if body.price_level_id is not None:
        await level(work.access, body.price_level_id)
    incoming = body.model_dump(exclude={"custom_fields"})
    value = PricePlan(**incoming)
    await purpose_access(work.access, value, write=True)
    context = await work.access.context(PricePlan)
    custom = await validate_custom(
        work.db,
        work.actor,
        work.company,
        context,
        body.custom_fields,
        {},
        {**incoming, "row_version": 1},
        {},
        creating=True,
    )
    value = await work.new(PricePlan, **incoming, custom_fields=custom)
    await reserve_claims(
        work.db,
        company_id=work.company,
        entity_type=context.native.entity_type,
        entity_id=value.id,
        definitions=context.definitions,
        values=custom,
    )
    await index_values(work.db, context, value.id, custom)
    return value


async def create_policy(
    work: PricingWork, body: PolicyInput, object_id: uuid.UUID | None
) -> PricingRow:
    await level(work.access, body.default_level_id)
    if body.fallback_level_id is not None:
        await level(work.access, body.fallback_level_id)
    if body.purchase_plan_id is not None:
        plan = await row(work.access, PricePlan, body.purchase_plan_id)
        await purpose_access(work.access, plan, write=True)
        if plan.purpose != "PURCHASE":
            raise ValidationFailedError("purchase default requires a PURCHASE book")
    await work.history(CompanyPricingPolicy, body, {})
    return await work.new(CompanyPricingPolicy, **values(body))


async def create_scope(
    work: PricingWork, body: ScopeInput, object_id: uuid.UUID | None
) -> PricingRow:
    await product(work.access, body.item_id)
    return await work.new(ItemPriceScope, item_id=body.item_id, subject_kind="SKU")


async def create_numeric(
    work: PricingWork, body: NumericInput, object_id: uuid.UUID | None
) -> PricingRow:
    if body.accept_defaults is not None:
        context = await work.access.context(ItemPriceNumericRevision)
        incoming = values(body)
        context.assert_writable(
            frozenset(key for key, value in incoming.items() if value is not None),
            before={},
            after=incoming,
        )
        from catalog.schemas.configuration import AuthoringDefaultsQuery
        from catalog.tasks.configuration_authoring import accepted

        _, family = await product(work.access, body.item_id)
        suggestion = await accepted(
            work.access,
            body.accept_defaults,
            AuthoringDefaultsQuery(
                as_of=body.valid_from,
                kind=cast(Literal["GOODS", "SERVICE"], family.kind),
                item_id=body.item_id,
                unit_revision_id=body.unit_revision_id,
                currency=body.currency,
            ),
        )
        selected = suggestion.price
        if selected is None or (body.price_decimal_places, body.price_increment) != (
            selected.price_decimal_places,
            selected.price_increment,
        ):
            raise ConflictError("price settings differ from accepted defaults")
    await currency(work.access, body.currency)
    await unit(work.access, body.item_id, body.unit_revision_id, body.valid_from)
    RateGrid(body.price_decimal_places, body.price_increment)
    await work.history(
        ItemPriceNumericRevision,
        body,
        {
            "item_id": body.item_id,
            "unit_revision_id": body.unit_revision_id,
            "currency": body.currency,
        },
    )
    return await work.new(ItemPriceNumericRevision, **values(body))


async def create_series(
    work: PricingWork, body: SeriesInput, object_id: uuid.UUID | None
) -> PricingRow:
    plan = await row(work.access, PricePlan, body.plan_id)
    await purpose_access(work.access, plan, write=True)
    if plan.price_level_id is not None:
        await level(work.access, plan.price_level_id)
    if body.channel_code is not None:
        if plan.purpose != "SALE":
            raise ValidationFailedError("only sale prices may name a sales channel")
        await protected(work.access, SalesChannel)
        channel = await work.access.db.scalar(
            select(SalesChannel).where(
                SalesChannel.company_id == work.access.company,
                SalesChannel.code == body.channel_code,
            )
        )
        if channel is None or not channel.is_active:
            raise ValidationFailedError("sales channel is unavailable")
        await work.access.require(channel)
    scope = await row(work.access, ItemPriceScope, body.price_scope_id)
    await unit(work.access, scope.item_id, body.unit_revision_id, purpose=plan.purpose)
    return await work.new(
        ItemPriceSeries,
        **body.model_dump(),
        item_id=scope.item_id,
        currency=plan.currency,
        audience_kind="STANDARD",
    )


def basis(revision: ItemUnitRevision, quantity: Any) -> None:
    exact_decimal(quantity)
    QuantityRule(revision.quantity_decimal_places, revision.quantity_increment).validate(quantity)
    if not revision.fractional_entry and quantity != quantity.to_integral_value():
        raise ValidationFailedError("fractional pricing-unit quantities are disabled")


async def update_plan(
    work: PricingWork, body: PlanPatch, object_id: uuid.UUID | None
) -> PricingRow:
    assert object_id is not None
    value = await row(work.access, PricePlan, object_id)
    await purpose_access(work.access, value, write=True)
    if not body.name.strip() or any(ord(c) < 32 for c in body.name):
        raise ValidationFailedError("plan name must contain printable text")
    context = await work.access.context(PricePlan)
    before = await work.access.values(value)
    after = {**before, "name": body.name.strip()}
    custom = await validate_custom(
        work.db,
        work.actor,
        work.company,
        context,
        body.custom_fields,
        before,
        after,
        value.custom_fields or {},
        creating=False,
    )
    await work.update(value, body.expected_version, name=body.name.strip(), custom_fields=custom)
    await reserve_claims(
        work.db,
        company_id=work.company,
        entity_type=context.native.entity_type,
        entity_id=value.id,
        definitions=context.definitions,
        values=custom,
    )
    await index_values(work.db, context, value.id, custom)
    return value

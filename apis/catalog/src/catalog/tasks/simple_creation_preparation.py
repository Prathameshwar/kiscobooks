"""Resolve simple form choices through the existing native configuration owners."""

import uuid
from decimal import Decimal
from typing import Any

from billing_platform.authz import ScopePath
from billing_platform.company_context import CompanyContext
from billing_platform.errors import ConflictError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.money import MoneyError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.models.classification import ItemGroup
from catalog.models.pricing import CompanyPricingPolicy, PricePlan
from catalog.models.projections import CompanyProjection
from catalog.schemas.configuration import AuthoringDefaultsQuery
from catalog.schemas.product_initial import InitialProductSetup
from catalog.schemas.simple_product_creation import SimpleCreationInput
from catalog.schemas.simple_products import SimpleProductCreate
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.configuration_authoring import suggestions
from catalog.tasks.pricing_commands import business_date, effective
from catalog.tasks.product_mode import enabled, version
from catalog.tasks.simple_classification_details import validate_details
from catalog.tasks.simple_sale_prices import sale_amounts
from catalog.tasks.simple_serial_preparation import prepare_serials

UNSUPPORTED_SIMPLE_OPTIONS = (
    "variants",
    "alternate_units",
    "compound_units",
    "measured_units",
)


async def default_group(access: ConfigurationAccess) -> uuid.UUID | None:
    identity = await access.db.scalar(
        select(ItemGroup.id).where(
            ItemGroup.company_id == access.company,
            ItemGroup.code == "DEFAULT",
            ItemGroup.is_active.is_(True),
        )
    )
    if identity is not None:
        await access.reference(ItemGroup, identity)
    return identity


def creation_permissions(body: SimpleCreationInput) -> frozenset[str]:
    permissions = {"item.create", "item.read", "item.update", "item.activate"}
    if (
        body.sale_prices
        or body.sale_price is not None
        or body.purchase_price is not None
        or body.mrp is not None
        or body.batches
    ):
        permissions.update(("price_plan.read", "price_plan.manage", "price_plan.publish"))
    if body.purchase_price is not None or any(
        entry.purchase_price is not None for entry in body.batches
    ):
        permissions.add("purchase_price.manage")
    if body.tax is not None:
        permissions.add("tax_rule.publish")
    if body.batches:
        permissions.update(("accounting.batch.read", "accounting.batch.manage"))
    if body.serials or any(entry.serials for entry in body.batches):
        permissions.update(("accounting.serial.read", "accounting.serial.manage"))
    if body.has_opening:
        permissions.update((
            "accounting.finance.manage",
            "accounting.stock.configure",
            "accounting.stock.read",
            "accounting.stock.post",
            "period.post",
            "vouchers.read",
            "vouchers.create",
            "vouchers.submit",
            "vouchers.issue",
            "vouchers.post",
        ))
    return frozenset(permissions)


def authority(actor: Actor, company: uuid.UUID, body: SimpleCreationInput) -> None:
    target = ScopePath(company_id=company)
    for permission in creation_permissions(body):
        actor.require_scope(permission, target=target)


async def prepare(
    db: AsyncSession,
    actor: Actor,
    context: CompanyContext,
    body: SimpleCreationInput,
    code: str,
) -> tuple[SimpleProductCreate, dict[str, Any]]:
    company = context.company_id
    authority(actor, company, body)
    if await enabled(db, company):
        raise ConflictError("Use the product profile and SKU workflow for this company")
    access = ConfigurationAccess(db, actor, company)
    profile = await db.scalar(
        select(CompanyProjection).where(CompanyProjection.company_id == company)
    )
    if profile is None or context.finance is None or not context.finance.company_active:
        raise ConflictError("Complete company setup before creating products")
    today = business_date(profile.timezone)
    opening_date = context.finance.books_begin_date
    if body.opening_date is not None and body.opening_date != opening_date:
        raise ValidationFailedError("Opening date must be the company books begin date")
    if body.has_opening and ("inventory" not in context.features or opening_date > today):
        raise ConflictError("Opening stock requires enabled inventory and an open books date")
    group = body.group_id or await default_group(access)
    if group is None:
        raise ValidationFailedError(
            "Choose a product group", fields={"group_id": "A product group is required"}
        )
    defaults = await suggestions(
        access,
        AuthoringDefaultsQuery(
            as_of=today,
            kind=body.kind,
            group_id=group,
            unit_id=body.base_unit_id,
            currency=context.base_currency,
        ),
    )
    if defaults.missing or defaults.product_type_revision_id is None or defaults.quantity is None:
        raise ConflictError("Complete the default product type and base unit configuration")
    configuration = defaults.configuration
    from catalog.tasks.simple_batch_preparation import prepare_batches

    await prepare_serials(access, defaults, body)
    batch_plan = await prepare_batches(access, defaults, body, today, opening_date)
    for option, field in (
        ("brand", "brand_id"),
        ("model", "model_code"),
        ("barcode", "barcode"),
        ("manufacturer", "manufacturer_id"),
    ):
        mode = getattr(configuration.options, option + "_mode")
        value = getattr(body, field)
        error_field = "barcode.value" if option == "barcode" else field
        if mode == "REQUIRED" and not value:
            raise ValidationFailedError(
                "Complete the required product details",
                fields={error_field: "Required by product configuration"},
            )
        if mode == "DISABLED" and value is not None:
            raise ValidationFailedError(
                "This product detail is disabled",
                fields={error_field: "Disabled by product configuration"},
            )
    await validate_details(access, configuration, body)
    if body.barcode is not None:
        from catalog.domain.product_authoring import validate_barcode

        try:
            validate_barcode(body.barcode.value, body.barcode.symbology)
        except ValidationFailedError as exc:
            raise ValidationFailedError(exc.message, fields={"barcode.value": exc.message}) from exc
    unsupported = [
        option.replace("_", " ")
        for option in UNSUPPORTED_SIMPLE_OPTIONS
        if getattr(configuration.options, option + "_mode") == "REQUIRED"
    ]
    if unsupported:
        raise ConflictError(
            "Simple creation cannot capture required "
            + ", ".join(unsupported)
            + ". Review Product Configuration before saving."
        )
    for field, mode in (
        ("purchase_price", configuration.pricing.purchase_reference_mode),
        ("mrp", configuration.pricing.mrp_mode),
    ):
        value = getattr(body, field)
        if (
            mode == "DISABLED" or (field == "mrp" and body.kind == "SERVICE")
        ) and value is not None:
            raise ValidationFailedError(
                "This price is disabled", fields={field: "Disabled by product configuration"}
            )
        if (
            mode == "REQUIRED"
            and value is None
            and not body.batch_enabled
            and not (field == "mrp" and body.kind == "SERVICE")
        ):
            raise ValidationFailedError(
                "Enter the required price", fields={field: "Required by product configuration"}
            )
    if body.opening_quantity:
        from catalog.domain.units import QuantityRule
        from catalog.models.inventory_templates import InventoryProfileTemplateRevision

        try:
            QuantityRule(
                defaults.quantity.quantity_decimal_places, defaults.quantity.quantity_increment
            ).validate(body.opening_quantity)
        except MoneyError as exc:
            raise ValidationFailedError(
                "Opening quantity does not fit the selected base unit",
                fields={"opening_quantity": "Use the base unit's quantity precision and increment"},
            ) from exc
        template_id = configuration.profiles.inventory_template_revision_id
        if template_id is None:
            raise ConflictError("Configure a stock inventory profile before entering opening stock")
        template = await access.reference(InventoryProfileTemplateRevision, template_id)
        if (template.lot_tracking and body.batch_enabled is not False) or (
            template.serial_tracking and not body.serials
        ):
            raise ConflictError(
                "Simple opening requires an inventory profile without batches or serials"
            )
    if body.tax is not None and profile.default_tax_system != "gst_in":
        raise ValidationFailedError("GST fields are unavailable for this company's tax system")
    if profile.default_tax_system == "gst_in" and (
        body.tax is None or body.tax.classification_id is None or body.tax.rule_id is None
    ):
        raise ValidationFailedError(
            "Select HSN/SAC and GST treatment",
            fields={"tax": "Select a published classification and GST rule"},
        )
    if body.tax is not None:
        from catalog.domain.tax import classification_matches
        from catalog.models.tax import TaxClassification, TaxRule
        from catalog.models.tax_governance import TaxRuleApplicability
        from catalog.tasks.tax_commands import active
        from catalog.tasks.tax_history import require_live, rows
        from catalog.tasks.tax_validation import stored_match

        assert body.tax.classification_id is not None and body.tax.rule_id is not None
        classification = await access.reference(TaxClassification, body.tax.classification_id)
        await require_live(access, classification)
        rule = await active(access, TaxRule, body.tax.rule_id)
        if classification.item_kind != body.kind or rule.item_kind != body.kind:
            raise ValidationFailedError(
                "Choose HSN for Goods or SAC for Services and a matching GST rule"
            )
        if classification.valid_from > today or classification.valid_to is not None:
            raise ValidationFailedError(
                "Choose a current HSN/SAC classification covering future product use"
            )
        matches = await rows(access, TaxRuleApplicability, rule_id=rule.id)
        if rule.classification_scope == "SPECIFIC" and not any(
            classification_matches(
                classification.code_system, classification.code, stored_match(match)
            )
            for match in matches
        ):
            raise ValidationFailedError(
                "The selected GST rule does not apply to this HSN/SAC",
                fields={"tax": "Choose a compatible GST rule"},
            )
    price = defaults.price
    assert price is not None
    if price.price_basis_quantity != Decimal("1"):
        raise ConflictError("Simple prices require a price basis of one base unit")
    policy = await effective(access, CompanyPricingPolicy, today)
    prices = [] if body.batch_enabled else await sale_amounts(access, configuration, today, body)
    if body.purchase_price is not None:
        if policy is None:
            raise ConflictError("Complete company pricing defaults")
        query = select(PricePlan).where(
            PricePlan.company_id == company,
            PricePlan.currency == context.base_currency,
            PricePlan.purpose == "PURCHASE",
            PricePlan.id == policy.purchase_plan_id,
        )
        plan = await db.scalar(query)
        if plan is None:
            raise ConflictError("The default price book is unavailable")
        await access.require(plan)
        prices.append(
            {
                "plan_id": plan.id,
                "amount": body.purchase_price,
            }
        )
    for entry in prices:
        entry.update(
            price_basis_quantity=Decimal("1"), price_decimal_places=price.price_decimal_places
        )
    setup = InitialProductSetup.model_validate(
        {
            "effective_from": today,
            "group_id": group,
            "tax": body.tax,
            "prices": prices,
            **({"batch_enabled": body.batch_enabled} if body.batch_enabled is not None else {}),
            **({"categories": body.categories} if body.categories else {}),
            **(
                {
                    "manufacturer": {
                        "expected_version": 1,
                        "manufacturer_id": body.manufacturer_id,
                        "site_id": body.manufacturer_site_id,
                        "valid_from": today,
                    }
                }
                if body.manufacturer_id is not None
                else {}
            ),
            "barcodes": [{"expected_version": 1, **body.barcode.model_dump()}]
            if body.barcode is not None
            else [],
            "expected_generation": configuration.policy_generation,
            "expected_source_version": configuration.source_version,
            "units": [
                {
                    "expected_version": 1,
                    "code": "BASE",
                    "unit_id": body.base_unit_id,
                    "role": "BASE",
                    "numerator": 1,
                    "denominator": 1,
                    "quantity_decimal_places": defaults.quantity.quantity_decimal_places,
                    "quantity_increment": defaults.quantity.quantity_increment,
                    "fractional_entry": defaults.quantity.fractional_entry,
                    "valid_from": opening_date if body.has_opening else today,
                }
            ],
        }
    )
    create = SimpleProductCreate(
        authoring_version=await version(db, company),
        code=code,
        name=body.name,
        kind=body.kind,
        product_type_revision_id=defaults.product_type_revision_id,
        base_unit_id=body.base_unit_id,
        brand_id=body.brand_id,
        series_id=body.series_id,
        model_code=body.model_code,
        custom_fields=body.custom_fields,
        shared_custom_fields=body.shared_custom_fields,
        initial_setup=setup,
    )
    return create, {
        "today": today.isoformat(),
        "opening_date": opening_date.isoformat(),
        "currency": context.base_currency,
        "jurisdiction": profile.country_code,
        "price_places": price.price_decimal_places,
        **({"batch_plan": batch_plan} if body.batch_enabled else {}),
    }

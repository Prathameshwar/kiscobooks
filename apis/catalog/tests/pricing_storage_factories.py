"""Native pricing fixtures with every new table and valid company-owned references."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import pricing as m
from tests.product_definition_factories import seed_definitions


async def seed_pricing(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    company, ids = await seed_definitions(factory, tenant)
    common = {"tenant_id": tenant, "company_id": company, "row_version": 1}
    dates = {"valid_from": dt.date(2090, 1, 1), "valid_to": None}
    scope = {
        "item_id": ids["item"],
        "unit_revision_id": ids["item_unit_revision"],
        "currency": "INR",
    }
    with tenant_scope(tenant):
        async with factory.begin() as db:

            async def save(model: type[Any], **values: Any) -> Any:
                value = model(**common, **values)
                db.add(value)
                await db.flush()
                ids.setdefault(model.__tablename__, value.id)
                return value

            level = await save(
                m.PriceLevel, code="PRICE1", name="Retail", ordinal=1, is_active=True
            )
            plan = await save(
                m.PricePlan,
                code="SALE",
                name="Sale",
                purpose="SALE",
                price_level_id=level.id,
                currency="INR",
                tax_basis="EXCLUSIVE",
            )
            await save(
                m.CompanyPricingPolicy,
                default_level_id=level.id,
                missing_price_policy="ERROR",
                fallback_level_id=None,
                purchase_plan_id=None,
                sale_unit_mode="EXPLICIT_ONLY",
                purchase_unit_mode="EXPLICIT_ONLY",
                **dates,
            )
            subject = await save(m.ItemPriceScope, item_id=ids["item"], subject_kind="SKU")
            numeric = await save(
                m.ItemPriceNumericRevision,
                **scope,
                price_decimal_places=4,
                price_increment=None,
                **dates,
            )
            series = await save(
                m.ItemPriceSeries,
                **scope,
                plan_id=plan.id,
                price_scope_id=subject.id,
                audience_kind="STANDARD",
            )
            terms = {
                **scope,
                **dates,
                "numeric_revision_id": numeric.id,
                "series_id": series.id,
                "price_method": "TIERS",
                "amount": None,
                "price_basis_quantity": Decimal(1),
            }
            draft = await save(m.ItemPriceDraft, **terms, status="PUBLISHED")
            price = await save(m.ItemPrice, **terms, source_draft_id=draft.id, supersedes_id=None)
            await save(
                m.ItemPriceTier,
                draft_id=None,
                price_id=price.id,
                min_quantity=Decimal(0),
                max_quantity=None,
                amount=Decimal(100),
                currency="INR",
            )
            purchase = await save(
                m.PricePlan,
                code="PURCHASE",
                name="Purchase",
                purpose="PURCHASE",
                price_level_id=None,
                currency="INR",
                tax_basis="EXCLUSIVE",
            )
            purchase_series = await save(
                m.ItemPriceSeries,
                **scope,
                plan_id=purchase.id,
                price_scope_id=subject.id,
                audience_kind="STANDARD",
            )
            purchase_draft = await save(
                m.ItemPriceDraft,
                **{
                    **terms,
                    "series_id": purchase_series.id,
                    "price_method": "FIXED",
                    "amount": Decimal(72),
                },
                status="DRAFT",
            )
            await save(
                m.PurchasePriceTerm,
                draft_id=purchase_draft.id,
                price_id=None,
                gross_amount=Decimal(80),
                discount_kind="PERCENT",
                discount_value=Decimal(10),
                currency="INR",
            )
            refs = {
                **scope,
                **dates,
                "numeric_revision_id": numeric.id,
                "amount": Decimal(80),
                "price_basis_quantity": Decimal(1),
                "source_reference": "Estimate",
                "tax_basis": "EXCLUSIVE",
            }
            await save(m.ItemReferenceCost, **refs, estimate_kind="STANDARD_ESTIMATE")
            await save(
                m.ItemMrp,
                **{**refs, "amount": Decimal(120), "tax_basis": "INCLUSIVE"},
                jurisdiction="IN",
            )
            formula_draft = await save(
                m.ItemPriceDraft, **{**terms, "price_method": "FORMULA"}, status="DRAFT"
            )
            await save(
                m.ItemPriceFormula,
                draft_id=formula_draft.id,
                price_id=None,
                recipe="REFERENCE_COST_PLUS_MARKUP",
                percentage=Decimal(25),
                estimate_kind="STANDARD_ESTIMATE",
                jurisdiction=None,
                rounding_mode="HALF_UP",
            )
            commercial = await save(
                m.CommercialPolicyScope,
                owner_kind="COMPANY",
                owner_id=company,
                group_id=None,
                family_id=None,
                item_id=None,
            )
            await save(
                m.CommercialGuardRule,
                **{**refs, "amount": Decimal(50)},
                rule_kind="FIXED_MIN",
                percentage=None,
                estimate_kind=None,
                severity="BLOCK",
            )
            await save(
                m.DiscountCeiling, scope_id=commercial.id, max_discount_pct=Decimal(10), **dates
            )
            await save(
                m.ItemCommercialPolicy, item_id=ids["item"], free_sale_allowed=False, **dates
            )
            ids["customer_party"] = uuid7()
            assignment_scope = await save(
                m.PriceLevelAssignmentScope,
                subject_kind="CUSTOMER",
                customer_ref=ids["customer_party"],
                pricing_type_ref=None,
            )
            await save(
                m.PriceLevelAssignment,
                scope_id=assignment_scope.id,
                price_level_id=level.id,
                **dates,
            )
    return company, ids

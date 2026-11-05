"""Synthetic reviewed tax definitions: never production rates or legal classifications."""

import datetime as dt
import uuid
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CatalogDefaultProfile,
    FamilyManufacturer,
    InventoryProfileTemplateRevision,
    Item,
    ItemGroup,
    ProductFamily,
    ProductType,
    ProductTypeRevision,
)
from catalog.models import pricing as pricing
from catalog.models import tax as m
from tests.inventory_factories import seed_template
from tests.pricing_storage_factories import seed_pricing
from tests.test_api import headers

DATE = dt.date(2090, 1, 1)
EVIDENCE = {
    "source_reference": "SYNTHETIC TEST ONLY; not a legal rate",
    "source_url": "https://cbic-gst.gov.in/pdf/press-release/Press-release-HSN-code-SAC-issue.pdf",
    "source_sha256": "ab" * 32,
}


def components(context: str, percentage: str = "5") -> list[dict[str, Any]]:
    from decimal import Decimal

    names = {
        "INTRA_STATE": ["CGST", "SGST"],
        "INTRA_UT": ["CGST", "UTGST"],
        "INTER_STATE": ["IGST"],
    }[context]
    return [
        {
            "component_key": name,
            "component": name,
            "kind": "PERCENT",
            "percentage": str(Decimal(percentage) / len(names)),
            "amount": None,
            "currency": None,
            "unit_id": None,
            "basis_quantity": None,
            "rounding_mode": "HALF_UP",
            "position": i,
        }
        for i, name in enumerate(names)
    ]


async def seed_tax(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    *,
    treatment: str = "TAXABLE",
    kind: str = "GOODS",
) -> tuple[str, dict[str, str], dict[str, uuid.UUID]]:
    company, ids = await seed_pricing(factory, tenant)
    _, template_id = await seed_template(factory, tenant, company)
    common = {"tenant_id": tenant, "company_id": company, "row_version": 1}
    dated = {"valid_from": DATE, "valid_to": None}
    with tenant_scope(tenant):
        async with factory.begin() as db:
            item = await db.get(Item, ids["item"])
            assert item is not None
            ids["unit_of_measure"] = item.base_unit_id
            template = await db.get(InventoryProfileTemplateRevision, template_id)
            defaults = await db.get(CatalogDefaultProfile, ids["catalog_default_profile"])
            assert template is not None and defaults is not None
            template.published_at = utcnow()
            defaults.inventory_template_revision_mode = "VALUE"
            defaults.inventory_template_revision_id = template_id
            ids["inventory_profile_template_revision"] = template_id
            if kind == "SERVICE":
                manufacturer = await db.get(FamilyManufacturer, ids["family_manufacturer"])
                assert manufacturer is not None
                await db.delete(manufacturer)
                group = await db.get(ItemGroup, ids["item_group"])
                assert group is not None
                group.allowed_kind = "BOTH"
                family = await db.get(ProductFamily, ids["product_family"])
                assert family is not None
                revision = await db.get(ProductTypeRevision, family.product_type_revision_id)
                assert revision is not None
                parent = await db.get(ProductType, revision.product_type_id)
                assert parent is not None
                parent.kind = revision.kind = family.kind = "SERVICE"
                revision.inventory_modes = ["NON_STOCK"]
                defaults.inventory_template_revision_mode = "CLEAR"
                defaults.inventory_template_revision_id = None

            async def save(model: type[Any], **values: Any) -> Any:
                value = model(**common, **values)
                db.add(value)
                await db.flush()
                ids.setdefault(model.__tablename__, value.id)
                return value

            category = await save(m.TaxCategory, code="TEST", name="Test category", is_active=True)
            rule = await save(
                m.TaxRule,
                code="TEST",
                name="Test goods",
                item_kind=kind,
                treatment=treatment,
                classification_scope="SPECIFIC",
                tax_category_id=category.id,
                tax_system="gst_in",
                jurisdiction="IN",
                is_active=True,
                **EVIDENCE,
            )
            classification = await save(
                m.TaxClassification,
                jurisdiction="IN",
                code_system="HSN" if kind == "GOODS" else "SAC",
                code="1234" if kind == "GOODS" else "991234",
                item_kind=kind,
                description="Synthetic classification",
                **dated,
                **EVIDENCE,
            )
            await save(
                m.TaxRuleApplicability,
                rule_id=rule.id,
                code_system=classification.code_system,
                code=classification.code,
                match_kind="EXACT",
            )
            release = await save(
                m.TaxRelease,
                change_reason="Synthetic fixture publication",
                business_date=DATE,
                input_digest="ab" * 32,
                change_count=1,
            )
            await save(
                m.TaxHistoryAction,
                resource="tax_classification",
                target_id=classification.id,
                action="PUBLISH",
                previous_id=None,
                previous_valid_to=None,
                release_id=release.id,
                reason="Synthetic fixture publication",
                business_date=DATE,
            )
            for context in ("INTRA_STATE", "INTRA_UT", "INTER_STATE"):
                series = await save(m.TaxRateSeries, rule_id=rule.id, applicability=context)
                ids["series_" + context] = series.id
                rate = await save(
                    m.TaxRate, series_id=series.id, supersedes_id=None, **dated, **EVIDENCE
                )
                ids["rate_" + context] = rate.id
                for entry in components(context, "0" if treatment == "NIL_RATED" else "5"):
                    await save(m.TaxRateComponent, rate_id=rate.id, **entry)
            scope = await save(
                m.CatalogTaxScope,
                owner_kind="COMPANY",
                owner_id=company,
                group_id=None,
                family_id=None,
                item_id=None,
            )
            for direction in ("SALE", "PURCHASE"):
                for bundle, values in (
                    ("CLASSIFICATION", {"classification_id": classification.id}),
                    (
                        "TREATMENT",
                        {
                            "treatment": treatment,
                            "tax_category_id": category.id,
                            "exemption_reason": "Test statutory exclusion"
                            if treatment in {"EXEMPT", "NON_GST"}
                            else None,
                        },
                    ),
                    ("RULE", {"rule_id": rule.id}),
                ):
                    binding = await save(
                        m.CatalogTaxBinding,
                        scope_id=scope.id,
                        jurisdiction="IN",
                        direction=direction,
                        bundle=bundle,
                        mode="OVERRIDE",
                        **dated,
                        **values,
                    )
                    ids[f"binding_{direction}_{bundle}"] = binding.id
            # Keep source data synthetic and explicit, including the existing pricing guard.
            mrp = await db.get(pricing.ItemMrp, ids["item_mrp"])
            assert mrp is not None
    return (
        f"/v1/companies/{company}",
        headers(
            company, tenant=tenant, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
        ),
        ids,
    )


def query(ids: dict[str, uuid.UUID], **extra: Any) -> dict[str, Any]:
    return {"item_id": str(ids["item"]), "as_of": str(DATE), "direction": "SALE", **extra}

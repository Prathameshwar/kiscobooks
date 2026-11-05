"""Company enrollment creates a minimal published configuration exactly once."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select

from catalog.models.configuration import (
    ProductConfigurationRevision,
    ProductEntryOptionPolicy,
    ProductPricingPolicy,
)
from catalog.models.pricing import CompanyPricingPolicy
from catalog.tasks.company_pricing_defaults import ensure_pricing_defaults
from catalog.tasks.company_product_defaults import ensure_product_defaults
from tests.test_unit_defaults import provision

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_minimal_configuration_is_published_once(factory, tenant_a):
    from catalog.tasks.company_configuration_defaults import ensure_configuration_defaults

    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
            await ensure_pricing_defaults(db, company)
            result = await ensure_configuration_defaults(db, company)
            assert result.status == "READY" and result.created_records > 0
        async with factory.begin() as db:
            revision = (await db.scalars(select(ProductConfigurationRevision))).one()
            pricing = (
                await db.scalars(
                    select(ProductPricingPolicy).where(
                        ProductPricingPolicy.revision_id == revision.id
                    )
                )
            ).one()
            assert pricing.sale_level_count == 1
            assert pricing.sale_price_mode == pricing.purchase_reference_mode == "OPTIONAL"
            assert pricing.mrp_mode == "DISABLED"
            assert pricing.unit_prices_mode == pricing.quantity_tiers_mode == "DISABLED"
            assert pricing.channel_prices_mode == pricing.additional_currencies_mode == "DISABLED"
            assert pricing.formula_prices_mode == "DISABLED"
            options = (
                await db.scalars(
                    select(ProductEntryOptionPolicy).where(
                        ProductEntryOptionPolicy.revision_id == revision.id
                    )
                )
            ).one()
            assert options.model_mode == options.brand_mode == "DISABLED"
            assert options.model_default is None
            assert (
                options.alternate_units_mode
                == options.compound_units_mode
                == options.measured_units_mode
                == "DISABLED"
            )
            assert (
                await db.scalars(select(CompanyPricingPolicy))
            ).one().missing_price_policy == "ERROR"
            assert (await ensure_configuration_defaults(db, company)).created_records == 0
            assert len(list(await db.scalars(select(ProductConfigurationRevision)))) == 1


@pytest.mark.parametrize("existing", ["scope", "authoring"])
async def test_authored_setup_is_preserved(factory, tenant_a, existing):
    from catalog.models.configuration import ProductConfigurationScope
    from catalog.models.product_authoring import CompanyProductAuthoringConfiguration
    from catalog.tasks.company_configuration_defaults import ensure_configuration_defaults

    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
            await ensure_pricing_defaults(db, company)
            common = {"tenant_id": tenant_a, "company_id": company}
            row = (
                ProductConfigurationScope(**common, scope_kind="COMPANY", owner_id=company)
                if existing == "scope"
                else CompanyProductAuthoringConfiguration(
                    **common, product_family_sku_enabled=True, change_reason="Existing choice"
                )
            )
            db.add(row)
            await db.flush()
            result = await ensure_configuration_defaults(db, company)
            assert result.status == "NEEDS_REVIEW" and result.created_records == 0
            assert not list(await db.scalars(select(ProductConfigurationRevision)))
            assert not list(await db.scalars(select(CompanyPricingPolicy)))


async def test_audit_failure_rolls_back_complete_starter_and_retry_succeeds(
    factory, tenant_a, monkeypatch
):
    from catalog.models import Outbox
    from catalog.models.configuration import ProductConfigurationScope
    from catalog.tasks import company_configuration_defaults as task

    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
            await ensure_pricing_defaults(db, company)
        real_emit = task.emit
        calls = 0

        def failing_emit(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 5:
                raise RuntimeError("audit unavailable")
            return real_emit(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(task, "emit", failing_emit)
            with pytest.raises(RuntimeError, match="audit unavailable"):
                async with factory.begin() as db:
                    await task.ensure_configuration_defaults(db, company)
        async with factory.begin() as db:
            assert not list(await db.scalars(select(ProductConfigurationScope)))
            assert not list(await db.scalars(select(CompanyPricingPolicy)))
            assert not [
                e
                for e in await db.scalars(select(Outbox))
                if e.payload.get("reason") == task.REASON
            ]
            assert (await task.ensure_configuration_defaults(db, company)).status == "READY"


async def test_two_companies_and_tenants_receive_independent_defaults(factory, tenant_a, tenant_b):
    from catalog.tasks.company_configuration_defaults import ensure_configuration_defaults

    for tenant, companies in ((tenant_a, [uuid7(), uuid7()]), (tenant_b, [uuid7()])):
        for company in companies:
            await provision(factory, tenant, company)
            with tenant_scope(tenant):
                async with factory.begin() as db:
                    await ensure_product_defaults(db, company)
                    await ensure_pricing_defaults(db, company)
                    assert (await ensure_configuration_defaults(db, company)).status == "READY"
        with tenant_scope(tenant):
            async with factory() as db:
                assert {
                    r.company_id for r in await db.scalars(select(ProductConfigurationRevision))
                } == set(companies)


async def test_starter_is_effective_and_can_publish_a_later_change(client, factory, tenant_a):
    from billing_platform.permissions import CATALOG_PERMISSIONS

    from catalog.models.configuration import ProductConfigurationScope
    from catalog.schemas.configuration import EntryOptions, PricingRequirements, ProfileDefaults
    from catalog.tasks.company_configuration_defaults import ensure_configuration_defaults
    from tests.configuration_factories import publish_configuration
    from tests.test_api import headers
    from tests.test_classification_api import setup_source

    company, user = uuid7(), uuid7()
    await setup_source(factory, tenant_a, company, user)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
            await ensure_pricing_defaults(db, company)
            assert (await ensure_configuration_defaults(db, company)).status == "READY"
            scope = (await db.scalars(select(ProductConfigurationScope))).one()
            revision = (await db.scalars(select(ProductConfigurationRevision))).one()
            scope_id, revision_id = str(scope.id), str(revision.id)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    detail = await client.get(
        root + "/product-configuration-revisions/" + revision_id, headers=auth
    )
    assert detail.status_code == 200, detail.text
    original = detail.json()
    for kind in ("GOODS", "SERVICE"):
        effective = await client.get(
            root + "/product-configuration/effective",
            headers=auth,
            params={"kind": kind, "as_of": "2026-01-01"},
        )
        assert effective.status_code == 200, effective.text
        assert effective.json()["pricing"]["quantity_tiers_mode"] == "DISABLED"
        assert effective.json()["options"]["barcode_mode"] == "DISABLED"
        assert [s["revision_id"] for s in effective.json()["sources"]] == [revision_id]
    body = {
        key: {field: original[key][field] for field in schema.model_fields}
        for key, schema in (
            ("options", EntryOptions),
            ("profiles", ProfileDefaults),
            ("pricing", PricingRequirements),
        )
    }
    body["pricing"]["quantity_tiers_mode"] = "ENABLED"
    _, newer = await publish_configuration(client, root, auth, scope_id=scope_id, **body)
    assert newer["revision"] == 2 and newer["pricing"]["quantity_tiers_mode"] == "ENABLED"
    retained = await client.get(
        root + "/product-configuration-revisions/" + revision_id, headers=auth
    )
    assert retained.json()["pricing"]["quantity_tiers_mode"] == "DISABLED"


async def test_incomplete_or_custom_starter_masters_require_review(factory, tenant_a):
    from catalog.models.commercial import ProductType, ProductTypeRevision
    from catalog.models.pricing import PricePlan
    from catalog.models.projections import CompanyProjection
    from catalog.tasks.company_configuration_defaults import ensure_configuration_defaults
    from tests.product_review_factories import changed

    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert (await ensure_configuration_defaults(db, company)).status == "NEEDS_REVIEW"
            await ensure_product_defaults(db, company)
            assert (await ensure_configuration_defaults(db, company)).status == "NEEDS_REVIEW"
            await ensure_pricing_defaults(db, company)
            owner = (await db.scalars(select(ProductType))).one()
            revision = (await db.scalars(select(ProductTypeRevision))).one()
            profile = (await db.scalars(select(CompanyProjection))).one()
            purchase = (
                await db.scalars(select(PricePlan).where(PricePlan.purpose == "PURCHASE"))
            ).one()
        for model, identifier, values, status in (
            (ProductType, owner.id, {"is_active": False}, "NEEDS_REVIEW"),
            (ProductTypeRevision, revision.id, {"require_brand": True}, "NEEDS_REVIEW"),
            (ProductTypeRevision, revision.id, {"published_at": None}, "NEEDS_REVIEW"),
            (PricePlan, purchase.id, {"currency": "USD"}, "NEEDS_REVIEW"),
            (CompanyProjection, profile.id, {"status": "inactive"}, "NOT_APPLICABLE"),
        ):
            async with changed(factory, tenant_a, model, identifier, **values):
                async with factory.begin() as db:
                    result = await ensure_configuration_defaults(db, company)
                    assert result.status == status and result.created_records == 0
                    assert not list(await db.scalars(select(ProductConfigurationRevision)))


async def test_existing_pricing_policy_is_never_replaced_by_starter(factory, tenant_a):
    import datetime as dt

    from catalog.models.pricing import PriceLevel
    from catalog.tasks.company_configuration_defaults import ensure_configuration_defaults

    company = uuid7()
    await provision(factory, tenant_a, company)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            await ensure_product_defaults(db, company)
            await ensure_pricing_defaults(db, company)
            level = (await db.scalars(select(PriceLevel))).one()
            retained = CompanyPricingPolicy(
                tenant_id=tenant_a,
                company_id=company,
                default_level_id=level.id,
                missing_price_policy="ERROR",
                sale_unit_mode="EXACT_BASE_DERIVATION",
                purchase_unit_mode="EXPLICIT_ONLY",
                valid_from=dt.date(2026, 1, 1),
            )
            db.add(retained)
            await db.flush()
            result = await ensure_configuration_defaults(db, company)
            assert result.status == "NEEDS_REVIEW" and result.created_records == 0
            assert not list(await db.scalars(select(ProductConfigurationRevision)))
            assert (await db.scalars(select(CompanyPricingPolicy))).one().id == retained.id
            assert retained.sale_unit_mode == "EXACT_BASE_DERIVATION"

"""Existing price capabilities obey company defaults and retained product pins."""

import pytest
from pydantic import ValidationError

from catalog.schemas.configuration import PricingRequirements

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize(
    "field",
    [
        "multiple_price_levels_mode",
        "unit_prices_mode",
        "quantity_tiers_mode",
        "channel_prices_mode",
        "additional_currencies_mode",
        "formula_prices_mode",
    ],
)
def test_dimension_modes_are_explicit_and_legacy_defaults_inherit(field):
    assert PricingRequirements().model_dump()[field] == "INHERIT"
    assert getattr(PricingRequirements(**{field: "DISABLED"}), field) == "DISABLED"
    assert getattr(PricingRequirements(**{field: "ENABLED"}), field) == "ENABLED"
    with pytest.raises(ValidationError):
        PricingRequirements(**{field: "OPTIONAL"})


async def test_disabled_tiers_block_new_prices_and_resolution_but_preserve_history(
    client, factory, tenant_a
):
    from billing_platform.permissions import CATALOG_PERMISSIONS

    from catalog.models.configuration import ProductPricingPolicy
    from tests.pricing_storage_factories import seed_pricing
    from tests.product_review_factories import changed
    from tests.test_api import headers
    from tests.test_commercial_api import command_headers
    from tests.test_pricing_resolution import query

    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    assert (
        await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
    ).status_code == 200
    async with changed(
        factory,
        tenant_a,
        ProductPricingPolicy,
        ids["product_pricing_policy"],
        quantity_tiers_mode="DISABLED",
    ):
        blocked = await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
        assert blocked.status_code == 409 and "Quantity-slab" in blocked.text
        assert (
            await client.get(root + f"/prices/{ids['item_price']}", headers=auth)
        ).status_code == 200
        body = {
            "series_id": str(ids["item_price_series"]),
            "numeric_revision_id": str(ids["item_price_numeric_revision"]),
            "valid_from": "2091-01-01",
            "price_basis_quantity": "1",
            "price_method": "TIERS",
            "tiers": [{"min_quantity": "0", "max_quantity": None, "amount": "90"}],
        }
        denied = await client.post(root + "/price-drafts", headers=command_headers(auth), json=body)
        assert denied.status_code == 409 and "Quantity-slab" in denied.text
        body.update(price_method="FIXED", amount="90", tiers=[])
        allowed = await client.post(
            root + "/price-drafts", headers=command_headers(auth), json=body
        )
        assert allowed.status_code == 201, allowed.text
    assert (
        await client.post(root + "/prices/resolve", headers=auth, json=query(ids))
    ).status_code == 200


async def test_formula_gate_precedes_source_calculation(client, factory, tenant_a):
    from billing_platform.permissions import CATALOG_PERMISSIONS

    from catalog.models.configuration import ProductPricingPolicy
    from tests.pricing_storage_factories import seed_pricing
    from tests.product_review_factories import changed
    from tests.test_api import headers
    from tests.test_commercial_api import command_headers

    company, ids = await seed_pricing(factory, tenant_a)
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    body = {
        "series_id": str(ids["item_price_series"]),
        "numeric_revision_id": str(ids["item_price_numeric_revision"]),
        "valid_from": "2091-01-01",
        "price_basis_quantity": "1",
        "price_method": "FORMULA",
        "formula": {
            "recipe": "REFERENCE_COST_PLUS_MARKUP",
            "estimate_kind": "STANDARD_ESTIMATE",
            "percentage": "10",
            "rounding_mode": "HALF_UP",
        },
    }
    async with changed(
        factory,
        tenant_a,
        ProductPricingPolicy,
        ids["product_pricing_policy"],
        formula_prices_mode="DISABLED",
    ):
        response = await client.post(
            f"/v1/companies/{company}/price-drafts", headers=command_headers(auth), json=body
        )
        assert response.status_code == 409 and "Formula prices" in response.text


async def test_company_revision_and_effective_fields_include_pricing_dimensions(
    client, factory, tenant_a
):
    from tests.configuration_factories import publish_configuration, setup_configuration

    company, _, auth, _ = await setup_configuration(factory, tenant_a)
    root = f"/v1/companies/{company}"
    fields = {
        "unit_prices_mode": "DISABLED",
        "quantity_tiers_mode": "DISABLED",
        "channel_prices_mode": "DISABLED",
        "additional_currencies_mode": "DISABLED",
        "formula_prices_mode": "DISABLED",
        "multiple_price_levels_mode": "DISABLED",
    }
    _, revision = await publish_configuration(client, root, auth, pricing=fields)
    assert all(revision["pricing"][key] == value for key, value in fields.items())
    for kind in ("GOODS", "SERVICE"):
        response = await client.get(
            root + "/product-configuration/effective",
            headers=auth,
            params={"as_of": "2090-01-01", "kind": kind},
        )
        assert response.status_code == 200, response.text
        assert all(response.json()["pricing"][key] == value for key, value in fields.items())


@pytest.mark.parametrize("field", ["additional_currencies_mode", "multiple_price_levels_mode"])
async def test_enable_requires_company_capability(client, factory, tenant_a, field):
    from tests.configuration_factories import setup_configuration
    from tests.test_commercial_api import command_headers

    company, _, auth, _ = await setup_configuration(factory, tenant_a)
    response = await client.post(
        f"/v1/companies/{company}/product-configurations/company",
        headers=command_headers(auth),
        json={
            "effective_from": "2090-01-01",
            "change_reason": "Enable prices",
            "pricing": {field: "ENABLED"},
        },
    )
    assert response.status_code == 409, response.text


@pytest.mark.parametrize(
    "field",
    [
        "unit_prices_mode",
        "channel_prices_mode",
        "additional_currencies_mode",
        "multiple_price_levels_mode",
    ],
)
async def test_disabled_dimensions_reject_valid_price_drafts(client, factory, tenant_a, field):
    import datetime as dt
    from contextlib import AsyncExitStack

    from billing_platform.db import tenant_scope
    from billing_platform.permissions import CATALOG_PERMISSIONS

    from catalog.domain.pricing_dimensions import PRICING_DIMENSIONS
    from catalog.models import pricing as m
    from catalog.models.configuration import ProductPricingPolicy
    from catalog.models.product_definitions import ItemUnitBinding, ItemUnitRevision
    from catalog.models.sales_channel import SalesChannel
    from tests.pricing_factories import pack_unit
    from tests.pricing_storage_factories import seed_pricing
    from tests.product_integrity_factories import features
    from tests.product_review_factories import changed
    from tests.test_api import headers
    from tests.test_commercial_api import command_headers
    from tests.test_pricing_resolution import query

    company, ids = await seed_pricing(factory, tenant_a)
    await features(
        factory, tenant_a, company, ids["actor_user"], {"multi_currency", "multi_price_levels"}
    )
    auth = headers(
        company, tenant=tenant_a, user=ids["actor_user"], permission=sorted(CATALOG_PERMISSIONS)
    )
    root = f"/v1/companies/{company}"
    changes = []
    unit_id = ids["item_unit_revision"]
    if field == "multiple_price_levels_mode":
        changes.append((m.PriceLevel, ids["price_level"], {"ordinal": 2}))
    elif field == "channel_prices_mode":
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                db.add(
                    SalesChannel(
                        tenant_id=tenant_a, company_id=company, code="ONLINE", name="Online"
                    )
                )
        changes.append((m.ItemPriceSeries, ids["item_price_series"], {"channel_code": "ONLINE"}))
    elif field == "unit_prices_mode":
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                pack = await pack_unit(db, tenant_a, company)
                binding = ItemUnitBinding(
                    tenant_id=tenant_a,
                    company_id=company,
                    item_id=ids["item"],
                    unit_id=pack.id,
                    code="CASE",
                    usage_role="PACK",
                )
                db.add(binding)
                await db.flush()
                revision = ItemUnitRevision(
                    tenant_id=tenant_a,
                    company_id=company,
                    binding_id=binding.id,
                    revision=1,
                    conversion_mode="FIXED",
                    numerator=12,
                    denominator=1,
                    quantity_decimal_places=0,
                    quantity_increment="1",
                    fractional_entry=False,
                    valid_from=dt.date(2090, 1, 1),
                )
                db.add(revision)
                await db.flush()
                unit_id = revision.id
    if field in {"unit_prices_mode", "additional_currencies_mode"}:
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                common = {"tenant_id": tenant_a, "company_id": company}
                code = "USD" if field == "additional_currencies_mode" else "INR"
                plan_id = ids["price_plan"]
                if code == "USD":
                    plan = m.PricePlan(
                        **common,
                        code="SALE_USD",
                        name="Dollar sales",
                        purpose="SALE",
                        price_level_id=ids["price_level"],
                        currency=code,
                        tax_basis="EXCLUSIVE",
                    )
                    db.add(plan)
                    await db.flush()
                    plan_id = plan.id
                scope = {"item_id": ids["item"], "unit_revision_id": unit_id, "currency": code}
                numeric = m.ItemPriceNumericRevision(
                    **common, **scope, price_decimal_places=4, valid_from=dt.date(2090, 1, 1)
                )
                series = m.ItemPriceSeries(
                    **common,
                    **scope,
                    plan_id=plan_id,
                    price_scope_id=ids["item_price_scope"],
                    audience_kind="STANDARD",
                )
                db.add_all([numeric, series])
                await db.flush()
                ids = {
                    **ids,
                    "item_price_numeric_revision": numeric.id,
                    "item_price_series": series.id,
                }
    body = {
        "series_id": str(ids["item_price_series"]),
        "numeric_revision_id": str(ids["item_price_numeric_revision"]),
        "valid_from": "2091-01-01",
        "price_basis_quantity": "1",
        "price_method": "FIXED",
        "amount": "90",
    }
    async with AsyncExitStack() as stack:
        for model, identity, values in changes:
            await stack.enter_async_context(changed(factory, tenant_a, model, identity, **values))
        allowed = await client.post(
            root + "/price-drafts", headers=command_headers(auth), json=body
        )
        assert allowed.status_code == 201, allowed.text
        async with changed(
            factory,
            tenant_a,
            ProductPricingPolicy,
            ids["product_pricing_policy"],
            **{field: "DISABLED"},
        ):
            denied = await client.post(
                root + "/price-drafts", headers=command_headers(auth), json=body
            )
            assert (
                denied.status_code == 409 and PRICING_DIMENSIONS[field] in denied.text
            ), denied.text
            # Publication preview must recheck an already saved draft too.
            preview = await client.get(
                root + "/price-drafts/" + allowed.json()["id"] + "/preview", headers=auth
            )
            assert (
                preview.status_code == 409 and PRICING_DIMENSIONS[field] in preview.text
            ), preview.text
            if field in {"channel_prices_mode", "additional_currencies_mode"}:
                selection = (
                    {"channel_code": "ONLINE"}
                    if field == "channel_prices_mode"
                    else {"currency": "USD"}
                )
                resolved = await client.post(
                    root + "/prices/resolve", headers=auth, json=query(ids, **selection)
                )
                assert resolved.status_code == 409 and PRICING_DIMENSIONS[field] in resolved.text


async def test_new_dimension_field_denial_is_enforced_on_draft_write(client, factory, tenant_a):
    from tests.configuration_factories import setup_configuration
    from tests.test_commercial_api import command_headers
    from tests.test_master_reference_policy import policy

    company, user, auth, _ = await setup_configuration(factory, tenant_a)
    await policy(
        factory,
        tenant_a,
        company,
        user,
        "catalog.product_pricing_policy",
        "quantity_tiers_mode",
        "write",
    )
    result = await client.post(
        f"/v1/companies/{company}/product-configurations/company",
        headers=command_headers(auth),
        json={
            "effective_from": "2090-01-01",
            "change_reason": "Protected option",
            "pricing": {"quantity_tiers_mode": "DISABLED"},
        },
    )
    assert result.status_code == 403, result.text

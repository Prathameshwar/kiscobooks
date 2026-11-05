import datetime as dt
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ItemGroupParent, ProductFamily
from catalog.models import tax as m
from tests.pricing_factories import create, guard
from tests.product_review_factories import changed
from tests.tax_factories import DATE, EVIDENCE, components, query, seed_tax
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.mark.parametrize("treatment", ["NIL_RATED", "EXEMPT", "NON_GST"])
async def test_explicit_non_taxable_definitions_have_distinct_semantics(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    treatment: str,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a, treatment=treatment)
    result = await client.post(root + "/tax-configurations/resolve", headers=auth, json=query(ids))
    assert result.status_code == 200 and result.json()["status"] == "COMPLETE", result.text
    assert result.json()["treatment"] == treatment
    assert bool(result.json()["rates"]) == (treatment == "NIL_RATED")
    if treatment != "NIL_RATED":
        result = await client.post(
            root + "/tax-rate-series",
            headers=command_headers(auth),
            json={"rule_id": str(ids["tax_rule"]), "applicability": "INTER_STATE"},
        )
        assert result.status_code == 422, result.text


async def test_invalid_selected_tax_data_never_falls_back(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    cases: list[tuple[type[Any], str, dict[str, Any], int]] = [
        (Item, "item", {"status": "DISCONTINUED"}, 409),
        (ProductFamily, "product_family", {"status": "DISCONTINUED"}, 409),
        (Item, "item", {"sellable": False}, 409),
        (m.TaxCategory, "tax_category", {"is_active": False}, 409),
        (m.TaxRule, "tax_rule", {"is_active": False}, 409),
        (m.TaxRule, "tax_rule", {"item_kind": "SERVICE"}, 409),
        (m.TaxRule, "tax_rule", {"treatment": "NIL_RATED"}, 409),
        (m.TaxClassification, "tax_classification", {"valid_from": dt.date(2091, 1, 1)}, 409),
        (m.TaxClassification, "tax_classification", {"valid_to": DATE}, 200),
        (
            m.CatalogTaxBinding,
            "binding_SALE_CLASSIFICATION",
            {"valid_from": dt.date(2091, 1, 1)},
            200,
        ),
        (
            m.CatalogTaxBinding,
            "binding_SALE_TREATMENT",
            {"mode": "INHERIT", "tax_category_id": None, "treatment": None},
            200,
        ),
        (ItemGroupParent, "item_group_parent", {"valid_from": dt.date(2091, 1, 1)}, 409),
    ]
    for model, key, updates, status in cases:
        async with changed(factory, tenant_a, model, ids[key], **updates):
            result = await client.post(
                root + "/tax-configurations/resolve", headers=auth, json=query(ids)
            )
            assert result.status_code == status, (key, updates, result.text)
    async with changed(factory, tenant_a, Item, ids["item"], purchasable=False):
        result = await client.post(
            root + "/tax-configurations/resolve",
            headers=auth,
            json=query(ids, direction="PURCHASE"),
        )
        assert result.status_code == 409, result.text
    async with changed(
        factory, tenant_a, m.TaxRateComponent, ids["tax_rate_component"], percentage="3"
    ):
        result = await client.post(
            root + "/tax-configurations/resolve", headers=auth, json=query(ids)
        )
        assert result.status_code == 409 and "correction" in result.text, result.text


async def test_scope_precedence_and_selected_classification_dates(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    for owner, field, identity in (
        ("GROUP", "group_id", "item_group"),
        ("FAMILY", "family_id", "product_family"),
        ("SKU", "item_id", "item"),
    ):
        scope = await create(
            client, root, auth, "/tax-scopes", {"owner_kind": owner, field: str(ids[identity])}
        )
        binding = {
            **guard(scope),
            "scope_id": scope["id"],
            "direction": "SALE",
            "bundle": "CLASSIFICATION",
            "mode": "OVERRIDE",
            "classification_id": str(ids["tax_classification"]),
            "valid_from": str(DATE),
        }
        async with changed(
            factory,
            tenant_a,
            m.TaxClassification,
            ids["tax_classification"],
            valid_from=dt.date(2091, 1, 1),
        ):
            invalid = await client.post(
                root + "/tax-bindings", headers=command_headers(auth), json=binding
            )
            assert invalid.status_code == 409, invalid.text
        if owner in {"FAMILY", "SKU"}:
            async with changed(
                factory,
                tenant_a,
                m.TaxClassification,
                ids["tax_classification"],
                code_system="SAC",
                item_kind="SERVICE",
                code="991234",
            ):
                wrong_kind = await client.post(
                    root + "/tax-bindings", headers=command_headers(auth), json=binding
                )
                assert wrong_kind.status_code == 422, wrong_kind.text
        await create(client, root, auth, "/tax-bindings", binding)
        result = await client.post(
            root + "/tax-configurations/resolve", headers=auth, json=query(ids)
        )
        assert result.status_code == 200, result.text
        assert result.json()["bundles"][0]["owner_kind"] == owner


async def test_fixed_cess_publication_preserves_exact_basis_and_rejects_currency(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    body: dict[str, Any] = {
        "expected_generation": 1,
        "expected_source_version": 2,
        **EVIDENCE,
        "series_id": str(ids["series_INTER_STATE"]),
        "valid_from": "2091-01-01",
        "supersedes_id": str(ids["rate_INTER_STATE"]),
        "expected_previous_version": 1,
        "components": [
            *components("INTER_STATE"),
            {
                "component_key": "CESS",
                "component": "CESS",
                "kind": "FIXED_PER_UNIT",
                "amount": "1.25",
                "currency": "USD",
                "basis_quantity": "1",
                "unit_id": str(ids["unit_of_measure"]),
                "rounding_mode": "HALF_UP",
                "position": 1,
            },
        ],
    }
    result = await client.post(root + "/tax-rate-previews", headers=auth, json=body)
    assert result.status_code == 422, result.text
    body["components"][-1]["currency"] = "INR"
    result = await client.post(root + "/tax-rate-previews", headers=auth, json=body)
    assert result.status_code == 409, result.text  # Compensation cess must agree in all contexts.
    body["expected_generation"] = 2
    result = await client.post(root + "/tax-rate-previews", headers=auth, json=body)
    assert result.status_code == 409, result.text

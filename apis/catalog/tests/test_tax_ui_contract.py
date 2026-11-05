import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.classification import CatalogPolicyState
from tests.tax_factories import seed_tax
from tests.test_api import headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_tax_administration_context_is_readonly_and_company_scoped(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, _ = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    with tenant_scope(tenant_a):
        async with factory() as db:
            before = await db.scalar(
                select(CatalogPolicyState.generation).where(
                    CatalogPolicyState.company_id == company
                )
            )
    response = await client.get(root + "/tax-administration", headers=auth)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["company_id"] == str(company)
    assert value["country_code"] == "IN" and value["policy_generation"] == (before or 1)
    assert value["source_version"] >= 1 and len(value["business_date"]) == 10
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert (
                await db.scalar(
                    select(CatalogPolicyState.generation).where(
                        CatalogPolicyState.company_id == company
                    )
                )
                == before
            )
    denied = await client.get(
        root + "/tax-administration",
        headers=headers(company, permission="item.read", tenant=tenant_a),
    )
    assert denied.status_code == 403
    wrong_company = await client.get(
        "/v1/companies/" + str(uuid.uuid4()) + "/tax-administration", headers=auth
    )
    assert wrong_company.status_code in {403, 404}
    assert (
        await client.get(root + "/tax-administration?unused=1", headers=auth)
    ).status_code == 422


@pytest.mark.parametrize(
    "entity,required",
    [
        ("tax_category", {"code", "name"}),
        (
            "tax_classification",
            {
                "code_system",
                "code",
                "description",
                "source_reference",
                "source_url",
                "source_sha256",
                "valid_from",
            },
        ),
        (
            "tax_rule",
            {"code", "name", "item_kind", "treatment", "tax_category_id", "classification_scope"},
        ),
        ("tax_rate_series", {"rule_id", "applicability"}),
        (
            "tax_rate",
            {"series_id", "valid_from", "source_reference", "source_url", "source_sha256"},
        ),
        (
            "tax_rate_component",
            {
                "component_key",
                "component",
                "kind",
                "percentage",
                "amount",
                "unit_id",
                "basis_quantity",
                "rounding_mode",
                "position",
            },
        ),
    ],
)
async def test_tax_native_form_controls_and_immutable_update_fields(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    entity: str,
    required: set[str],
) -> None:
    root, auth, _ = await seed_tax(factory, tenant_a)
    path = root + "/entities/catalog." + entity + "/field-set"
    response = await client.get(path + "?operation=create", headers=auth)
    assert response.status_code == 200, response.text
    fields = {item["key"]: item for item in response.json()["fields"]}
    assert required <= fields.keys()
    assert all(fields[key]["control"] is not None for key in required)
    updated = await client.get(path + "?operation=update", headers=auth)
    assert updated.status_code == 200, updated.text
    fields = {item["key"]: item for item in updated.json()["fields"]}
    editable = {"name", "is_active"} if entity in {"tax_category", "tax_rule"} else set()
    assert not any(
        item["writable"]
        for key, item in fields.items()
        if item["source"] == "native" and key not in editable
    )


async def test_tax_active_status_filter_is_supported_and_resource_specific(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, _ = await seed_tax(factory, tenant_a)
    assert (
        await client.get(root + "/tax-categories?is_active=true", headers=auth)
    ).status_code == 200
    assert (await client.get(root + "/tax-rules?is_active=false", headers=auth)).json()[
        "items"
    ] == []
    assert (await client.get(root + "/tax-rates?is_active=true", headers=auth)).status_code == 422
    rates = await client.get(root + "/tax-rates", headers=auth)
    assert rates.status_code == 200, rates.text
    assert all(
        row["rule_code"] == "TEST" and row["rule_name"] == "Test goods"
        for row in rates.json()["items"]
    )
    assert {row["applicability"] for row in rates.json()["items"]} == {
        "INTRA_STATE",
        "INTRA_UT",
        "INTER_STATE",
    }

"""Configuration editors receive typed controls and scoped published reference choices."""

import uuid

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ProductTypeRevision
from tests.configuration_factories import setup_configuration
from tests.test_api import headers
from tests.test_master_reference_policy import policy

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_revision_choice_parent_remains_under_current_field_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, user, auth, product = await setup_configuration(factory, tenant_a)
    path = f"/v1/companies/{company}/product-configuration/options/product-type-revisions"
    with tenant_scope(tenant_a):
        async with factory() as db:
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(product["product_type_revision_id"])
            )
            assert revision is not None
            parent = str(revision.product_type_id)
    available = await client.get(
        path, headers=auth, params={"value": product["product_type_revision_id"]}
    )
    assert available.status_code == 200, available.text
    assert available.json()["items"][0]["parent_id"] == parent
    await policy(
        factory, tenant_a, company, user, "catalog.product_type_revision", "product_type_id", "read"
    )
    denied = await client.get(
        path, headers=auth, params={"value": product["product_type_revision_id"]}
    )
    assert denied.status_code == 403, denied.text
    assert parent not in denied.text


async def test_configuration_metadata_exposes_typed_choices_and_immutable_revisions(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, _ = await setup_configuration(factory, tenant_a)
    base = f"/v1/companies/{company}/entities/"
    response = await client.get(
        base + "catalog.product_entry_option_policy/field-set", headers=auth
    )
    assert response.status_code == 200, response.text
    fields = {row["key"]: row for row in response.json()["fields"]}
    assert response.json()["configuration_complete"] is True
    mode = fields["barcode_mode"]["control"]
    assert mode["kind"] == "select"
    assert {row["value"] for row in mode["choices"]} == {
        "INHERIT",
        "DISABLED",
        "OPTIONAL",
        "REQUIRED",
    }
    assert (
        next(row for row in mode["choices"] if row["value"] == "INHERIT")["label"]
        == "Use system default"
    )
    scope = await client.get(base + "catalog.product_configuration_scope/field-set", headers=auth)
    assert scope.status_code == 200, scope.text
    ownership = {row["key"]: row for row in scope.json()["fields"]}
    assert ownership["scope_kind"]["control"]["choices"] == [
        {"value": "COMPANY", "label": "Company"}
    ]
    assert all(
        ownership[key].get("control") is None
        for key in ("product_type_id", "group_id", "family_id", "item_id")
    )
    for source in ("product-types", "groups", "families"):
        removed = await client.get(
            f"/v1/companies/{company}/product-configuration/options/{source}", headers=auth
        )
        assert removed.status_code == 422, removed.text
    assert fields["barcode_default"]["control"]["depends_on"] == "barcode_mode"
    revision = await client.get(
        base + "catalog.product_configuration_revision/field-set", headers=auth
    )
    assert revision.status_code == 200
    assert all(not field["writable"] for field in revision.json()["fields"])
    prices = await client.get(base + "catalog.product_pricing_policy/field-set", headers=auth)
    assert prices.status_code == 200, prices.text
    from catalog.domain.pricing_dimensions import PRICING_DIMENSIONS

    price_fields = {row["key"]: row for row in prices.json()["fields"]}
    for key in PRICING_DIMENSIONS:
        field = price_fields[key]
        assert field["help_text"]
        expected = {"INHERIT", "DISABLED"}
        if key not in {"additional_currencies_mode", "multiple_price_levels_mode"}:
            expected.add("ENABLED")
        assert {c["value"] for c in field["control"]["choices"]} == expected
    numeric = await client.get(base + "catalog.product_numeric_default/field-set", headers=auth)
    assert numeric.status_code == 200
    dimension = next(row for row in numeric.json()["fields"] if row["key"] == "dimension")
    assert {row["value"] for row in dimension["control"]["choices"]} == {
        "COUNT",
        "MASS",
        "VOLUME",
        "LENGTH",
        "AREA",
        "TIME",
        "JOB",
    }


async def test_configuration_revision_picker_is_searchable_and_filters_published_kind(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, _, auth, product = await setup_configuration(factory, tenant_a)
    path = f"/v1/companies/{company}/product-configuration/options/product-type-revisions"
    response = await client.get(path, headers=auth, params={"q": "General", "kind": "GOODS"})
    assert response.status_code == 200, response.text
    assert [row["value"] for row in response.json()["items"]] == [
        product["product_type_revision_id"]
    ]
    assert "General" in response.json()["items"][0]["label"]
    service = await client.get(path, headers=auth, params={"kind": "SERVICE"})
    assert service.status_code == 200 and service.json()["items"] == []
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            revision = await db.get(
                ProductTypeRevision, uuid.UUID(product["product_type_revision_id"])
            )
            assert revision is not None
            revision.published_at = None
    unavailable = await client.get(path, headers=auth)
    assert unavailable.status_code == 200 and unavailable.json()["items"] == []


@pytest.mark.parametrize(
    "authority,status", [("anonymous", 401), ("reader_only", 403), ("other_company", 403)]
)
async def test_configuration_picker_requires_underlying_and_company_authority(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    authority: str,
    status: int,
) -> None:
    company, user, auth, _ = await setup_configuration(factory, tenant_a)
    if authority == "anonymous":
        auth = {}
    elif authority == "reader_only":
        auth = headers(company, tenant=tenant_a, user=user, permission="product_configuration.read")
    else:
        other, other_user, _, _ = await setup_configuration(factory, tenant_a)
        auth = headers(
            other,
            tenant=tenant_a,
            user=other_user,
            permission=["product_configuration.read", "product_type.read"],
        )
    response = await client.get(
        f"/v1/companies/{company}/product-configuration/options/product-type-revisions",
        headers=auth,
    )
    assert response.status_code == status, response.text


async def test_configuration_metadata_marks_masked_aggregates_incomplete(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, auth, _ = await setup_configuration(factory, tenant_a)
    entity = "catalog.product_entry_option_policy"
    await policy(factory, tenant_a, company, user, entity, "barcode_default", "read")
    response = await client.get(
        f"/v1/companies/{company}/entities/{entity}/field-set?operation=update", headers=auth
    )
    assert response.status_code == 200, response.text
    assert response.json()["configuration_complete"] is False
    assert "barcode_default" not in {row["key"] for row in response.json()["fields"]}


async def test_configuration_picker_hydrates_exact_selection_and_rejects_bad_queries(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, _, auth, product = await setup_configuration(factory, tenant_a)
    other, _, other_auth, foreign = await setup_configuration(factory, tenant_b)
    path = f"/v1/companies/{company}/product-configuration/options/product-type-revisions"
    result = await client.get(
        path, headers=auth, params={"value": product["product_type_revision_id"], "limit": 1}
    )
    assert result.status_code == 200, result.text
    assert [row["value"] for row in result.json()["items"]] == [product["product_type_revision_id"]]
    absent = await client.get(
        path, headers=auth, params={"value": foreign["product_type_revision_id"]}
    )
    assert absent.status_code == 200 and absent.json()["items"] == []
    denied = await client.get(path, headers=other_auth)
    assert denied.status_code == 403
    for query in ("value=bad", "limit=1&limit=2", "fields=secret", "sort=published_at"):
        response = await client.get(path + "?" + query, headers=auth)
        assert response.status_code == 422, response.text
    assert other != company

import base64
import json
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.import_contracts import CONTROLS, FileFormat
from billing_platform.import_files import document
from billing_platform.permissions import CATALOG_PERMISSIONS
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import Item, ProductFamily
from catalog.models.pricing import ItemPrice, PriceLevel
from catalog.models.projections import CustomFieldDefinitionProjection
from catalog.tasks.projections import fact_values
from tests.pricing_factories import foundation, setup_pricing
from tests.product_factories import setup_product
from tests.source_factories import all_facts
from tests.test_api import headers
from tests.test_unit_api import seed_context

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def command(
    client: httpx.AsyncClient,
    root: str,
    auth: dict[str, str],
    path: str,
    body: dict[str, Any],
    status: int = 200,
) -> dict[str, Any]:
    result = await client.post(
        root + path, json=body, headers=auth | {"Idempotency-Key": str(uuid7())}
    )
    assert result.status_code == status, result.text
    return dict(result.json())


def source(
    resource: str, data: dict[str, Any], file_format: FileFormat = "CSV", action: str = "CREATE"
) -> dict[str, str]:
    raw = document(
        file_format,
        [
            (
                "Records",
                [*CONTROLS, "_payload"],
                [
                    [
                        "record",
                        "aggregate",
                        resource,
                        action,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        json.dumps(data),
                    ]
                ],
            )
        ],
    )
    return {
        "filename": "input." + file_format.lower(),
        "format": file_format,
        "content_base64": base64.b64encode(raw).decode(),
    }


@pytest.mark.parametrize(
    "kind,file_format", [("GOODS", "CSV"), ("SERVICE", "TSV"), ("GOODS", "XLSX")]
)
async def test_goods_and_service_imports_reuse_native_family_command(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    kind: str,
    file_format: FileFormat,
) -> None:
    company, user, _, body = await setup_product(factory, tenant_a, kind=kind)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    template = await command(
        client,
        root,
        auth,
        "/import-templates",
        {"definition": "products", "parameters": {"resource": "product_family", "kind": kind}},
        201,
    )
    assert "product_family:CREATE" in template["snapshot"]["schemas"]
    file_template = await client.get(
        root + "/import-templates/" + template["id"],
        params={"resource": "product_family", "format": file_format},
        headers=auth,
    )
    assert file_template.status_code == 200, file_template.text
    job = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {"template_id": template["id"], "files": [source("product_family", body, file_format)]},
        201,
    )
    path = "/import-jobs/" + job["id"]
    reviewed = await command(client, root, auth, path + "/validate", {"expected_version": 1})
    assert reviewed["state"] == "READY", reviewed
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 0
            assert await db.scalar(select(func.count(Item.id))) == 0
    applied = await command(
        client,
        root,
        auth,
        path + "/commit",
        {"expected_version": reviewed["row_version"], "review_digest": reviewed["review_digest"]},
    )
    assert applied["state"] == "SUCCEEDED", applied
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ProductFamily.id))) == 1
            assert await db.scalar(select(func.count(Item.id))) == 1


async def test_price_import_and_tenant_authority(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, _ = await setup_product(factory, tenant_a)
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    root = f"/v1/companies/{company}"
    template = await command(
        client,
        root,
        auth,
        "/import-templates",
        {"definition": "prices", "parameters": {"resource": "price_level"}},
        201,
    )
    job = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {"template_id": template["id"], "files": [source("price_level", {}, action="BOOTSTRAP")]},
        201,
    )
    path = "/import-jobs/" + job["id"]
    reviewed = await command(client, root, auth, path + "/validate", {"expected_version": 1})
    assert reviewed["state"] == "READY", reviewed
    applied = await command(
        client,
        root,
        auth,
        path + "/commit",
        {"expected_version": reviewed["row_version"], "review_digest": reviewed["review_digest"]},
    )
    assert applied["state"] == "SUCCEEDED", applied
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(PriceLevel.id))) == 1
    unauthorized = await client.get(
        root + path, headers=headers(company, tenant=tenant_a, user=user, permission="item.read")
    )
    assert unauthorized.status_code == 403
    wrong_company = uuid7()
    await seed_context(factory, tenant_a, wrong_company, user)
    rejected = await client.get(
        f"/v1/companies/{wrong_company}" + path,
        headers=headers(
            wrong_company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS)
        ),
    )
    assert rejected.status_code == 403, rejected.text


async def test_import_fixed_price_draft_and_publish_in_one_aggregate(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    template = await command(client, root, auth, "/import-templates", {"definition": "prices"}, 201)
    data = {
        "series_id": setup["series"]["id"],
        "numeric_revision_id": setup["numeric"]["id"],
        "valid_from": "2090-01-01",
        "price_method": "FIXED",
        "amount": "123.4500",
        "price_basis_quantity": "1",
    }
    raw = document(
        "TSV",
        [
            (
                "Records",
                [*CONTROLS, "_payload"],
                [
                    [
                        "draft",
                        "price",
                        "item_price_draft",
                        "CREATE",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        json.dumps(data),
                    ],
                    [
                        "publish",
                        "price",
                        "item_price_draft",
                        "PUBLISH",
                        "",
                        "",
                        "draft",
                        "id",
                        "",
                        "",
                        "{}",
                    ],
                ],
            )
        ],
    )
    file = {
        "filename": "prices.tsv",
        "format": "TSV",
        "content_base64": base64.b64encode(raw).decode(),
    }
    job = await command(
        client, root, auth, "/import-jobs", {"template_id": template["id"], "files": [file]}, 201
    )
    path = "/import-jobs/" + job["id"]
    reviewed = await command(client, root, auth, path + "/validate", {"expected_version": 1})
    assert reviewed["state"] == "READY", reviewed
    applied = await command(
        client,
        root,
        auth,
        path + "/commit",
        {"expected_version": reviewed["row_version"], "review_digest": reviewed["review_digest"]},
    )
    assert applied["state"] == "SUCCEEDED", applied
    with tenant_scope(tenant_a):
        async with factory() as db:
            price = await db.scalar(
                select(ItemPrice).where(ItemPrice.company_id == uuid.UUID(root.rsplit("/", 1)[-1]))
            )
            assert price is not None and str(price.amount) == "123.4500"


async def test_template_includes_serializable_effective_custom_configuration(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, user, _, _ = await setup_product(factory, tenant_a)
    definition = next(row for row in all_facts(company, user) if row.kind == "custom_definition")
    values = fact_values(definition)
    values["entity_type"] = "catalog.product_family"
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            db.add(
                CustomFieldDefinitionProjection(
                    tenant_id=tenant_a,
                    company_id=company,
                    source_id=definition.id,
                    source_version=2,
                    **values,
                )
            )
    auth = headers(company, tenant=tenant_a, user=user, permission=sorted(CATALOG_PERMISSIONS))
    template = await command(
        client,
        f"/v1/companies/{company}",
        auth,
        "/import-templates",
        {"definition": "products", "parameters": {"resource": "product_family"}},
        201,
    )
    assert any(
        field.get("key") == "cf_note" for field in template["snapshot"]["fields"]["product_family"]
    )

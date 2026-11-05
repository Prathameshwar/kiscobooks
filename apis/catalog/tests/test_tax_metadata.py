import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.tax import ACTIVATION_MODELS, TAX_MODELS
from tests.tax_factories import seed_tax
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_tax_metadata_and_activation_evidence_are_native_and_readonly(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, _ = await seed_tax(factory, tenant_a)
    for model in (*TAX_MODELS, *ACTIVATION_MODELS):
        result = await client.get(
            root + "/entities/catalog." + model.__tablename__ + "/field-set", headers=auth
        )
        assert result.status_code == 200, result.text
        fields = {entry["key"]: entry for entry in result.json()["fields"]}
        assert fields and fields["row_version"]["writable"] is False
        if model in ACTIVATION_MODELS:
            assert not any(entry["writable"] for entry in fields.values())
        if model.__tablename__ == "catalog_tax_scope":
            assert fields["owner_id"]["writable"] is False


async def test_tax_and_activation_writes_are_rate_limited_per_actor(
    app: FastAPI,
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    company = uuid.UUID(root.rsplit("/", 1)[1])
    for kind, limit in (("tax", 120), ("activate", 30)):
        key = kind + ":" + tenant_a.hex + company.hex + ids["actor_user"].hex
        for _ in range(limit):
            assert app.state.pricing_limiter.allow(key, limit=limit)
    result = await client.post(
        root + "/tax-categories", headers=command_headers(auth), json={"code": "NEW", "name": "New"}
    )
    assert result.status_code == 429, result.text
    result = await client.post(
        root + "/items/" + str(ids["item"]) + "/activate",
        headers=command_headers(auth),
        json={
            "as_of": "2090-01-01",
            "expected_version": 1,
            "expected_family_version": 1,
            "preview_token": "unverified",
        },
    )
    assert result.status_code == 429, result.text

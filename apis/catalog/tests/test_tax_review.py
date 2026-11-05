import datetime as dt
import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    FamilyAttribute,
    FamilyGroupAssignment,
    Item,
    ItemVariantKey,
    ProductFamily,
)
from catalog.models.tax import CatalogTaxBinding, TaxRateSeries
from catalog.tasks import activation, tax_resolution
from catalog.tasks.configuration_access import ConfigurationAccess
from catalog.tasks.tax_commands import jurisdiction
from tests.product_review_factories import changed
from tests.tax_factories import DATE, query, seed_tax
from tests.test_commercial_api import command_headers

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_simple_default_sku_can_activate(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            family = await db.get(ProductFamily, ids["product_family"])
            attribute = await db.get(FamilyAttribute, ids["family_attribute"])
            key = await db.get(ItemVariantKey, ids["item_variant_key"])
            assert family is not None and attribute is not None and key is not None
            family.structure_mode = "SIMPLE"
            attribute.is_axis = False
            await db.delete(key)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    route = root + "/items/" + str(ids["item"])
    preview = await client.post(
        route + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
    )
    assert preview.status_code == 200 and preview.json()["eligible"], preview.text
    body = {
        key: preview.json()[key]
        for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
    }
    result = await client.post(route + "/activate", headers=command_headers(auth), json=body)
    assert result.status_code == 200, result.text


async def test_tax_adapter_rejects_an_unsupported_company_jurisdiction() -> None:
    access = cast(
        ConfigurationAccess,
        SimpleNamespace(
            context=AsyncMock(
                return_value=SimpleNamespace(company=SimpleNamespace(country_code="US"))
            )
        ),
    )
    with pytest.raises(ConflictError, match="Indian"):
        await jurisdiction(access)


async def test_tax_ancestry_and_legacy_series_bounds_fail_closed(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    path = root + "/tax-configurations/resolve"
    async with changed(
        factory,
        tenant_a,
        FamilyGroupAssignment,
        ids["family_group_assignment"],
        valid_from=dt.date(2091, 1, 1),
    ):
        result = await client.post(path, headers=auth, json=query(ids))
        assert result.status_code == 200 and result.json()["status"] == "COMPLETE", result.text
    with monkeypatch.context() as patch:
        patch.setattr(tax_resolution, "MAX_DEPTH", 0)
        result = await client.post(path, headers=auth, json=query(ids))
        assert result.status_code == 409 and "depth" in result.text, result.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            # Simulate a corrupt/legacy persisted context; normal writes retain their CHECK.
            await db.execute(text("PRAGMA ignore_check_constraints=ON"))
            db.add(
                TaxRateSeries(
                    tenant_id=tenant_a,
                    company_id=uuid.UUID(root.rsplit("/", 1)[1]),
                    rule_id=ids["tax_rule"],
                    applicability="LEGACY",
                    row_version=1,
                )
            )
            await db.flush()
            await db.execute(text("PRAGMA ignore_check_constraints=OFF"))
    result = await client.post(path, headers=auth, json=query(ids))
    assert result.status_code == 409 and "contexts" in result.text, result.text


async def test_activation_missing_tax_and_family_version_exhaustion_roll_back(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    route = root + "/items/" + str(ids["item"])
    cases: list[tuple[type[Any], str, dict[str, Any], str]] = [
        (
            CatalogTaxBinding,
            "binding_SALE_RULE",
            {"mode": "REQUIRE_EXPLICIT", "rule_id": None},
            "missing",
        ),
        (ProductFamily, "product_family", {"row_version": 2**31 - 1}, "exhausted"),
    ]
    for model, key, values, message in cases:
        async with changed(factory, tenant_a, model, ids[key], **values):
            preview = await client.post(
                route + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
            )
            assert preview.status_code == 200, preview.text
            body = {
                key: preview.json()[key]
                for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
            }
            result = await client.post(
                route + "/activate", headers=command_headers(auth), json=body
            )
            assert result.status_code == 409 and message in result.text, result.text


async def test_activation_accepts_an_active_family_and_skips_unused_directions(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 1, 12, tzinfo=dt.UTC))
    route = root + "/items/" + str(ids["item"])
    async with changed(factory, tenant_a, Item, ids["item"], sellable=False, purchasable=False):
        result = await client.post(
            route + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
        )
        assert result.status_code == 200 and result.json()["eligible"], result.text
        assert not any(
            x["entity_type"].startswith("catalog.tax_") for x in result.json()["sources"]
        )
    async with changed(factory, tenant_a, ProductFamily, ids["product_family"], status="ACTIVE"):
        preview = await client.post(
            route + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
        )
        assert preview.status_code == 200 and preview.json()["eligible"], preview.text
        body = {
            key: preview.json()[key]
            for key in ("as_of", "expected_version", "expected_family_version", "preview_token")
        }
        result = await client.post(route + "/activate", headers=command_headers(auth), json=body)
        assert result.status_code == 200 and result.json()["family_version"] == 1, result.text
        repeated = await client.post(
            route + "/activation-preview", headers=auth, json={"as_of": str(DATE)}
        )
        assert repeated.status_code == 409, repeated.text

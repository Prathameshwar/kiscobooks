"""Publication and activation must agree with known regular-price restrictions."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from billing_platform.db import tenant_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import ProductPricingPolicy
from catalog.models.pricing import CommercialGuardRule, ItemMrp, ItemPrice, ItemPriceDraft
from catalog.tasks import activation
from tests.bulk_factories import post, run
from tests.pricing_factories import create, foundation, guard, publish_price, setup_pricing
from tests.tax_factories import DATE, seed_tax
from tests.test_commercial_api import command_headers
from tests.test_pricing_resolution import reference

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


def draft_body(setup: dict[str, Any], **values: Any) -> dict[str, Any]:
    return {
        "series_id": setup["series"]["id"],
        "numeric_revision_id": setup["numeric"]["id"],
        "valid_from": "2090-01-01",
        "price_method": "FIXED",
        "amount": "100",
        "price_basis_quantity": "1",
        **values,
    }


@pytest.mark.parametrize("kind", ["floor", "mrp", "tiers", "mixed_tax"])
async def test_preview_and_publication_reject_known_blocking_prices(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    kind: str,
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(
        client, root, auth, ids, tax_basis="INCLUSIVE" if kind == "mrp" else "EXCLUSIVE"
    )
    if kind == "mrp":
        token = await create(
            client,
            root,
            auth,
            "/product-mrps",
            reference(ids, setup, setup["series"], amount="80", jurisdiction="IN"),
        )
    else:
        token = await create(
            client,
            root,
            auth,
            "/commercial-guard-rules",
            reference(ids, setup, setup["series"], amount="90", rule_kind="FIXED_MIN"),
        )
    if kind == "mixed_tax":
        await create(
            client,
            root,
            auth,
            "/product-mrps",
            reference(ids, setup, token, amount="120", jurisdiction="IN"),
        )
    values: dict[str, Any] = {"amount": "100" if kind == "mrp" else "80"}
    if kind == "tiers":
        values = {
            "price_method": "TIERS",
            "amount": None,
            "tiers": [
                {"min_quantity": "0", "max_quantity": "10", "amount": "100"},
                {"min_quantity": "10", "amount": "80"},
            ],
        }
    draft = await create(client, root, auth, "/price-drafts", draft_body(setup, **values))
    preview = await client.get(root + "/price-drafts/" + draft["id"] + "/preview", headers=auth)
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid"] is False, preview.text
    assert preview.json()["issues"], preview.text
    result = await client.post(
        root + "/price-drafts/" + draft["id"] + "/publish",
        headers=command_headers(auth),
        json={**guard(preview.json()), "expected_version": 1},
    )
    assert result.status_code == 409, result.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemPrice.id))) == 0
            saved = await db.get(ItemPriceDraft, uuid.UUID(draft["id"]))
            assert saved is not None and saved.status == "DRAFT" and saved.row_version == 1


async def test_preview_distinguishes_tax_context_and_approval_rules(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    minimum = await create(
        client,
        root,
        auth,
        "/commercial-guard-rules",
        reference(
            ids,
            setup,
            setup["series"],
            amount="110",
            rule_kind="FIXED_MIN",
            severity="REQUIRE_APPROVAL",
        ),
    )
    await create(
        client,
        root,
        auth,
        "/product-mrps",
        reference(ids, setup, minimum, amount="120", jurisdiction="IN"),
    )
    draft, _ = await publish_price(client, root, auth, setup)
    preview = await client.get(root + "/price-drafts/" + draft["id"] + "/preview", headers=auth)
    assert preview.status_code == 200 and preview.json()["valid"], preview.text
    assert preview.json()["transaction_requirements"] == ["TAX_CONTEXT"]
    assert preview.json()["approval_guard_ids"] == [minimum["id"]]
    assert preview.json()["final_guard_validation_required"] is True


async def test_bulk_guard_failure_leaves_published_price_and_history_unchanged(
    client: httpx.AsyncClient, factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    root, auth, ids = await setup_pricing(factory, tenant_a)
    setup = await foundation(client, root, auth, ids)
    _, old = await publish_price(client, root, auth, setup)
    await create(
        client,
        root,
        auth,
        "/commercial-guard-rules",
        reference(ids, setup, old, amount="90", rule_kind="FIXED_MIN"),
    )
    bulk = root + "/bulk-jobs"
    job = await post(
        client,
        bulk,
        auth,
        "",
        {
            "format": "JSON",
            "mode": "UPDATE_ONLY",
            "records": [
                {
                    "key": "price",
                    "change_set": "sku",
                    "resource": "item_price",
                    "action": "ADJUST",
                    "target": {"id": old["id"]},
                    "data": {
                        "method": "SET",
                        "value": "80",
                        "rounding_mode": "HALF_UP",
                        "currency": "INR",
                        "unit_revision_id": str(ids["item_unit_revision"]),
                        "price_level_id": setup["level"]["id"],
                        "price_basis_quantity": "1",
                        "numeric_revision_id": setup["numeric"]["id"],
                        "valid_from": "2091-01-01",
                    },
                }
            ],
        },
    )
    await post(
        client, bulk, auth, f"/{job['id']}/validate", {"expected_version": job["row_version"]}
    )
    state = await run(
        factory, tenant_a, uuid.UUID(root.rsplit("/", 1)[1]), ids["actor_user"], job["id"]
    )
    assert state != "READY"
    records = await client.get(bulk + "/" + job["id"] + "/records", headers=auth)
    assert records.json()["items"][0]["error_code"] == "review_conflict", records.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemPrice.id))) == 1
            price = await db.get(ItemPrice, uuid.UUID(old["id"]))
            assert price is not None and price.valid_to is None and price.row_version == 1


async def test_required_price_activation_reports_commercial_blockers(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, auth, ids = await seed_tax(factory, tenant_a)
    monkeypatch.setattr(activation, "utcnow", lambda: dt.datetime(2090, 1, 2, 12, tzinfo=dt.UTC))
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            mrp = await db.get(ItemMrp, ids["item_mrp"])
            rule = await db.get(CommercialGuardRule, ids["commercial_guard_rule"])
            pricing = await db.get(ProductPricingPolicy, ids["product_pricing_policy"])
            assert mrp is not None and rule is not None and pricing is not None
            mrp.valid_to, rule.amount, pricing.sale_price_mode = DATE, Decimal(150), "REQUIRED"
    preview = await client.post(
        root + f"/items/{ids['item']}/activation-preview",
        headers=auth,
        json={"as_of": "2090-01-02"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["eligible"] is False and preview.json()["missing"], preview.text
    assert "catalog.commercial_guard_rule" in {
        source["entity_type"] for source in preview.json()["sources"]
    }

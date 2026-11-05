"""Configured selling levels reach native publication through Simple creation."""

from decimal import Decimal
from uuid import UUID

import pytest
from billing_platform.company_context import sign_company_context, verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy import select

from catalog.models.configuration import ProductPricingPolicy
from catalog.models.pricing import ItemPrice, ItemPriceSeries, PriceLevel, PricePlan
from catalog.models.products import Item
from tests.conftest import ACTOR_SECRET
from tests.source_factories import all_facts
from tests.test_simple_product_creation import starter
from tests.test_simple_product_import import fresh_company_context
from tests.test_unit_defaults import provision

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


@pytest.fixture(autouse=True)
def fresh_context(client):
    client.event_hooks["request"].append(fresh_company_context)


async def multi_source(factory, tenant, facts, *, deny=None):
    policies = []
    if deny:
        source = next(
            row for row in all_facts(facts.company_id, facts.user_id) if row.kind == "field_policy"
        )
        policies.append(
            SnapshotRecord(
                kind="field_policy",
                id=uuid7(),
                data={
                    **source.data,
                    "entity_type": "catalog.item_price_draft",
                    "subject_type": "user",
                    "subject_id": str(facts.user_id),
                    "field_key": "amount",
                    "access": deny,
                },
            )
        )
    await provision(
        factory,
        tenant,
        facts.company_id,
        user=facts.user_id,
        inventory=False,
        version=4 if deny else 3,
        policies=(
            SnapshotRecord(
                kind="feature",
                id=uuid7(),
                data={
                    "company_id": str(facts.company_id),
                    "feature_key": "multi_price_levels",
                    "is_enabled": True,
                    "locked_at": None,
                },
            ),
            *policies,
        ),
    )


async def multi_starter(factory, tenant, *, required=True):
    root, auth, unit = await starter(factory, tenant)
    facts = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    await multi_source(factory, tenant, facts)
    token, signature = sign_company_context(
        facts.model_copy(update={"features": frozenset({"multi_price_levels"})}),
        ACTOR_SECRET.encode(),
    )
    auth |= {"x-company-context": token, "x-company-signature": signature}
    with tenant_scope(tenant):
        async with factory.begin() as db:
            config = await db.scalar(
                select(ProductPricingPolicy).where(ProductPricingPolicy.revision_id.is_not(None))
            )
            config.multiple_price_levels_mode = "ENABLED"
            config.sale_price_mode = "REQUIRED" if required else "OPTIONAL"
            config.sale_level_count = 3
            first = await db.scalar(select(PriceLevel))
            first.name = "Retail"
            levels = [first.id]
            for ordinal, name in [(2, "Wholesale"), (3, "Distributor")]:
                identity = uuid7()
                db.add(
                    PriceLevel(
                        id=identity,
                        tenant_id=tenant,
                        company_id=facts.company_id,
                        code=f"PRICE{ordinal}",
                        name=name,
                        ordinal=ordinal,
                        is_active=True,
                    )
                )
                await db.flush()
                db.add(
                    PricePlan(
                        id=uuid7(),
                        tenant_id=tenant,
                        company_id=facts.company_id,
                        code=f"SALE{ordinal}",
                        name=name,
                        purpose="SALE",
                        price_level_id=identity,
                        currency="INR",
                        tax_basis="EXCLUSIVE",
                    )
                )
                levels.append(identity)
    return root, auth, unit, levels


async def test_options_and_four_initial_prices_are_published_once(client, factory, tenant_a):
    root, auth, unit, levels = await multi_starter(factory, tenant_a)
    response = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert response.status_code == 200, response.text
    options = response.json()
    assert [row["name"] for row in options["sale_price_levels"]] == [
        "Retail",
        "Wholesale",
        "Distributor",
    ]
    assert all(row["required"] for row in options["sale_price_levels"])
    assert "sale_price" not in {field["key"] for field in options["fields"]}
    body = {
        "name": "Multiple rates",
        "base_unit_id": unit,
        "purchase_price": "1.2500",
        "sale_prices": [
            {"price_level_id": str(level), "amount": amount}
            for level, amount in zip(levels, ["20.1234", "18.2500", "15.0000"], strict=False)
        ],
    }
    signed = auth | {"Idempotency-Key": str(uuid7())}
    started = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert started.status_code == 201, started.text
    for _ in range(24):
        done = await client.post(
            root + "/simple-product-creations/" + started.json()["id"] + "/advance", headers=auth
        )
        assert done.status_code == 200, f"Advance {_}: {done.text}"
        if done.json()["status"] == "COMPLETE":
            break
    assert done.json()["status"] == "COMPLETE"
    replay = await client.post(root + "/simple-product-creations", headers=signed, json=body)
    assert replay.status_code == 201 and replay.json()["id"] == started.json()["id"]
    with tenant_scope(tenant_a):
        async with factory() as db:
            prices = list(await db.scalars(select(ItemPrice)))
            assert len(prices) == 4
            sales = dict(
                (
                    await db.execute(
                        select(PricePlan.price_level_id, ItemPrice.amount)
                        .join(ItemPriceSeries, ItemPrice.series_id == ItemPriceSeries.id)
                        .join(PricePlan, ItemPriceSeries.plan_id == PricePlan.id)
                        .where(PricePlan.purpose == "SALE")
                    )
                ).all()
            )
            assert sales == dict(
                zip(levels, map(Decimal, ["20.1234", "18.2500", "15"]), strict=False)
            )


async def test_missing_unknown_disabled_and_duplicate_levels_are_rejected(
    client, factory, tenant_a
):
    root, auth, unit, levels = await multi_starter(factory, tenant_a)
    base = {"name": "Check rates", "base_unit_id": unit}

    async def send(rows):
        return await client.post(
            root + "/simple-product-creations",
            headers=auth | {"Idempotency-Key": str(uuid7())},
            json=base | {"sale_prices": rows},
        )

    missing = await send([{"price_level_id": str(levels[0]), "amount": "10"}])
    assert missing.status_code == 422, missing.text
    assert "sale_prices." + str(levels[1]) in missing.json()["error"]["fields"]
    unknown = await send([{"price_level_id": str(uuid7()), "amount": "10"}])
    assert unknown.status_code == 404, unknown.text
    duplicate = await send([{"price_level_id": str(levels[0]), "amount": "10"}] * 2)
    assert duplicate.status_code == 422, duplicate.text
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            config = await db.scalar(
                select(ProductPricingPolicy).where(ProductPricingPolicy.revision_id.is_not(None))
            )
            config.multiple_price_levels_mode = "DISABLED"
            config.sale_level_count = 1
    disabled = await send([{"price_level_id": str(levels[1]), "amount": "10"}])
    assert disabled.status_code == 422, disabled.text


async def test_required_coverage_optional_levels_and_missing_books(client, factory, tenant_a):
    root, auth, _, levels = await multi_starter(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            config = await db.scalar(
                select(ProductPricingPolicy).where(ProductPricingPolicy.revision_id.is_not(None))
            )
            config.sale_level_count = 2
    options = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert [row["required"] for row in options.json()["sale_price_levels"]] == [True, True, False]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            plan = await db.scalar(select(PricePlan).where(PricePlan.price_level_id == levels[1]))
            await db.delete(plan)
    missing = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert missing.status_code == 409 and "price book" in missing.text


async def test_cross_company_level_is_denied_and_price_metadata_is_protected(
    client, factory, tenant_a
):
    root, auth, unit, _ = await multi_starter(factory, tenant_a)
    other_root, _, _ = await starter(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory() as db:
            foreign = await db.scalar(
                select(PriceLevel.id).where(
                    PriceLevel.company_id == UUID(other_root.rsplit("/", 1)[1])
                )
            )
    denied = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={
            "name": "Wrong company",
            "base_unit_id": unit,
            "sale_prices": [{"price_level_id": str(foreign), "amount": "10"}],
        },
    )
    assert denied.status_code == 403, denied.text
    facts = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    await multi_source(factory, tenant_a, facts, deny="read")
    template_response = await client.post(
        root + "/import-templates",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={
            "definition": "simple_products",
            "parameters": {"resource": "simple_product_create", "kind": "GOODS"},
        },
    )
    assert template_response.status_code == 403, template_response.text


async def test_named_prices_cannot_bypass_amount_write_denial(client, factory, tenant_a):
    root, auth, unit, levels = await multi_starter(factory, tenant_a)
    facts = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    await multi_source(factory, tenant_a, facts, deny="write")
    options = await client.get(root + "/simple-product-creations/options", headers=auth)
    assert options.status_code == 200, options.text
    fields = [
        field for field in options.json()["fields"] if field["key"].startswith("sale_prices.")
    ]
    assert len(fields) == 3 and all(not field["writable"] for field in fields)
    started = await client.post(
        root + "/simple-product-creations",
        headers=auth | {"Idempotency-Key": str(uuid7())},
        json={
            "name": "Denied rates",
            "base_unit_id": unit,
            "sale_prices": [{"price_level_id": str(level), "amount": "10"} for level in levels],
        },
    )
    assert started.status_code == 201, started.text
    denied = await client.post(
        root + "/simple-product-creations/" + started.json()["id"] + "/advance", headers=auth
    )
    assert denied.status_code == 403, denied.text
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(Item.id)) is None
            assert await db.scalar(select(ItemPrice.id)) is None


def test_legacy_command_hash_shape_and_initial_price_bound():
    from pydantic import ValidationError

    from catalog.schemas.product_initial import InitialProductSetup
    from catalog.schemas.simple_product_creation import SimpleCreationInput
    from catalog.tasks.simple_product_creation import creation_request

    body = SimpleCreationInput(name="Legacy", base_unit_id=uuid7(), sale_price="10")
    request = creation_request(body)
    assert "sale_prices" not in request and "barcode" not in request
    common = {
        "effective_from": "2026-11-04",
        "expected_generation": 1,
        "expected_source_version": 1,
    }
    prices = [
        {
            "plan_id": str(uuid7()),
            "amount": "10",
            "price_basis_quantity": "1",
            "price_decimal_places": 4,
        }
        for _ in range(65)
    ]
    assert len(InitialProductSetup.model_validate(common | {"prices": prices}).prices) == 65
    with pytest.raises(ValidationError):
        InitialProductSetup.model_validate(common | {"prices": [*prices, prices[0]]})

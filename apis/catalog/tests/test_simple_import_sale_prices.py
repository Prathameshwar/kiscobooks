"""Named sale columns retain exact values through validation and native import."""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.import_models import ImportJobRevision
from sqlalchemy import func, select

from catalog.models.pricing import ItemPrice, PriceLevel
from catalog.models.products import Item
from tests.conftest import ACTOR_SECRET
from tests.test_master_imports import command
from tests.test_simple_product_import import commit, report, simple_source, template, validate
from tests.test_simple_sale_prices import multi_source, multi_starter

pytestmark = pytest.mark.usefixtures("stable_product_source_clock")


async def test_activation_review_cannot_be_reused_outside_its_command_transaction():
    from catalog.tasks.bulk_registry import reviewed_product_call

    runtime = SimpleNamespace(
        factory=object(),
        db=object(),
        company=uuid.uuid4(),
        actor=SimpleNamespace(tenant_id=uuid.uuid4(), user_id=uuid.uuid4()),
    )
    handler = reviewed_product_call(activate=True, reuse_locked_review=True)
    with pytest.raises(RuntimeError, match="same command transaction"):
        await handler(runtime, None, uuid.uuid4(), "review")


@pytest.mark.parametrize("kind,file_format", [("GOODS", "CSV"), ("SERVICE", "XLSX")])
async def test_named_sale_columns_import_activate_report_and_protect_retained_values(
    client, factory, tenant_a, kind, file_format
):
    root, auth, _, _ = await multi_starter(factory, tenant_a)
    facts = verify_company_context(
        auth["x-company-context"], auth["x-company-signature"], ACTOR_SECRET.encode()
    )
    configured = await template(client, root, auth, kind)
    schema = configured["snapshot"]["schemas"]["simple_product_create:CREATE"]
    assert "sale_price" not in schema["properties"]
    assert schema["properties"]["sale_price_2"]["title"] == "Wholesale selling price"
    assert {"sale_price_1", "sale_price_2", "sale_price_3"} <= set(schema["required"])
    staged = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {
            "template_id": configured["id"],
            "files": [
                simple_source(
                    [
                        {
                            "name": "Named prices import",
                            "base_unit": "HOUR",
                            "purchase_price": "1.2500",
                            "sale_price_1": "20.1234",
                            "sale_price_2": "18.2500",
                            "sale_price_3": "15.0000",
                        }
                    ],
                    file_format,
                )
            ],
        },
        201,
    )
    ready = await validate(client, root, auth, staged)
    assert ready["state"] == "READY", await report(client, root, auth, staged["id"], "RESULT")
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert await db.scalar(select(func.count(ItemPrice.id))) == 0
    await commit(client, root, auth, ready)
    path = root + "/simple-product-imports/" + staged["id"]
    for _ in range(30):
        response = await client.post(path + "/advance", headers=auth, json={})
        assert response.status_code == 200, response.text
        if response.json()["job"]["state"] == "SUCCEEDED":
            break
    assert response.json()["job"]["state"] == "SUCCEEDED", response.text
    replay = await client.post(path + "/advance", headers=auth, json={})
    assert replay.status_code == 200 and replay.json()["pending_count"] == 0
    result = await report(client, root, auth, staged["id"], "RESULT")
    assert all(value in result for value in [b"sale_price_2", b"20.1234", b"18.2500", b"15.0000"])
    history = await client.get(
        root + "/import-jobs/" + staged["id"] + "/history/attempts", headers=auth
    )
    assert history.status_code == 200 and history.json()["items"]
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert (await db.scalars(select(Item))).one().status == "ACTIVE"
            assert set(await db.scalars(select(ItemPrice.amount))) == set(
                map(Decimal, ["1.25", "20.1234", "18.25", "15"])
            )
            stored = await db.scalar(
                select(ImportJobRevision).where(ImportJobRevision.job_id == uuid.UUID(staged["id"]))
            )
            stored.batch = None
    await multi_source(factory, tenant_a, facts, deny="read")
    denied = await client.get(path + "/progress", headers=auth)
    assert denied.status_code == 403 and "20.1234" not in denied.text


async def test_named_price_template_rejects_missing_invalid_values_and_stale_level_names(
    client, factory, tenant_a
):
    root, auth, _, _ = await multi_starter(factory, tenant_a)
    configured = await template(client, root, auth)
    staged = await command(
        client,
        root,
        auth,
        "/import-jobs",
        {
            "template_id": configured["id"],
            "files": [
                simple_source(
                    [
                        {
                            "name": "Missing wholesale",
                            "base_unit": "HOUR",
                            "sale_price_1": "10",
                            "sale_price_3": "8",
                        },
                        {
                            "name": "Negative wholesale",
                            "base_unit": "HOUR",
                            "sale_price_1": "10",
                            "sale_price_2": "-1",
                            "sale_price_3": "8",
                        },
                        {
                            "name": "Free price without permission",
                            "base_unit": "HOUR",
                            "sale_price_1": "0",
                            "sale_price_2": "9",
                            "sale_price_3": "8",
                        },
                    ]
                )
            ],
        },
        201,
    )
    invalid = await validate(client, root, auth, staged)
    assert invalid["state"] == "INVALID"
    corrections = await report(client, root, auth, staged["id"], "CORRECTION")
    assert b"sale_price_2" in corrections
    # Correction files contain rejected source rows, without diagnostic columns.
    assert b"Free price without permission" in corrections
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            assert await db.scalar(select(func.count(Item.id))) == 0
            level = await db.scalar(select(PriceLevel).where(PriceLevel.ordinal == 2))
            level.name = "Trade"
    stale = await client.post(
        root + "/import-templates",
        headers=auth | {"Idempotency-Key": str(uuid.uuid4())},
        json={"definition": "simple_products", "parameters": configured["snapshot"]["parameters"]},
    )
    assert stale.status_code == 409 and "configuration changed" in stale.text.lower()
